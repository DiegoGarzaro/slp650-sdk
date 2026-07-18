"""FastAPI print agent for the Seiko SLP650/SLP650SE.

Run with:

    SLP650_API_KEY=... uvicorn slp650_sdk.api:app --host 0.0.0.0 --port 8787

The API refuses all requests until ``SLP650_API_KEY`` is configured; the
service binds to all interfaces, so running without authentication would
expose the printer to the whole network.
"""

from __future__ import annotations

import asyncio
import hmac
import io
import os
import shutil
import tempfile
import threading
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field

from slp650_sdk.config import SLPConfig, media_pixels
from slp650_sdk.errors import SLPError
from slp650_sdk.native_encoder import encode_image
from slp650_sdk.rendering import fit_image_to_media, render_text_image
from slp650_sdk.templates import list_templates, render_template
from slp650_sdk.transport import print_file, send_native_stream

MAX_UPLOAD_BYTES = 20 * 1024 * 1024

app = FastAPI(title="SLP650 Print Agent", version="0.2.0")
PRINT_LOCK = threading.Lock()


def verify_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Validate the ``X-API-Key`` header against ``SLP650_API_KEY``.

    Args:
        x_api_key (str | None): Value of the ``X-API-Key`` request header.

    Raises:
        HTTPException: 503 if no key is configured on the server, 401 if the
            provided key does not match.
    """
    configured = os.getenv("SLP650_API_KEY", "")
    if not configured:
        raise HTTPException(
            status_code=503,
            detail="SLP650_API_KEY is not configured on the server; refusing requests.",
        )
    if x_api_key is None or not hmac.compare_digest(configured, x_api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")


class TextLabel(BaseModel):
    """Request body for ``POST /print/text``."""

    text: str = Field(min_length=1, max_length=2000)
    media: str = "AddressSmall"
    density: str = "MediumQuality"
    fine_print: bool = False
    copies: int = Field(default=1, ge=1, le=100)
    font_size: int = Field(default=42, ge=8, le=180)
    margin: int = Field(default=24, ge=0, le=200)
    rotate: Literal[0, 90, 180, 270] = 0


class TemplateLabel(BaseModel):
    """Request body for ``POST /print/template``."""

    template: str = Field(min_length=1)
    fields: dict[str, str] = Field(default_factory=dict)
    media: str | None = None
    density: str = "MediumQuality"
    fine_print: bool = False
    copies: int = Field(default=1, ge=1, le=100)


async def execute_print(path: Path, config: SLPConfig, copies: int) -> int:
    """Encode via the CUPS pipeline and print, without blocking the loop.

    Used only for inputs the native encoder cannot read (e.g. PDFs).

    Args:
        path (Path): Input document to print.
        config (SLPConfig): Printer configuration.
        copies (int): Number of copies.

    Returns:
        int: Native stream size in bytes, per copy.

    Raises:
        HTTPException: 503 if encoding or printing fails.
    """
    def run() -> int:
        with PRINT_LOCK:
            return print_file(path, config, copies=copies)

    try:
        return await asyncio.to_thread(run)
    except SLPError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


async def execute_native_print(
    image: Image.Image, config: SLPConfig, copies: int
) -> int:
    """Encode a label image with the native encoder and print it.

    Args:
        image (Image.Image): 1-bit label image in reading orientation.
        config (SLPConfig): Printer configuration (density/fine mode used by
            the encoder, device used by the transport).
        copies (int): Number of copies.

    Returns:
        int: Native stream size in bytes, per copy.

    Raises:
        HTTPException: 422 for encoding parameter errors, 503 if the printer
            is unavailable.
    """
    def run() -> int:
        data = encode_image(
            image,
            density=config.density,
            fine_print=config.fine_print,
            cups_compat=False,
        )
        with PRINT_LOCK:
            send_native_stream(data, config, copies=copies)
        return len(data)

    try:
        return await asyncio.to_thread(run)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SLPError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _read_upload(payload: bytes, what: str) -> None:
    """Validate an uploaded payload.

    Args:
        payload (bytes): Raw uploaded bytes.
        what (str): Human-readable name used in error messages.

    Raises:
        HTTPException: 422 if empty, 413 if larger than ``MAX_UPLOAD_BYTES``.
    """
    if not payload:
        raise HTTPException(status_code=422, detail=f"Uploaded {what} is empty")
    if len(payload) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Maximum upload size is 20 MiB")


@app.get("/health")
def health(_: None = Depends(verify_api_key)) -> dict[str, object]:
    """Report printer availability and optional CUPS (PDF) support.

    Text and image printing use the built-in native encoder and only need
    the device; the CUPS toolchain is required solely for PDF uploads.
    """
    config = SLPConfig.from_env()
    pdf_support = (
        config.ppd_path.is_file()
        and config.filter_path.is_file()
        and shutil.which("cupsfilter") is not None
    )
    return {
        "ok": config.device_path.exists(),
        "device": str(config.device_path),
        "device_present": config.device_path.exists(),
        "pdf_support": pdf_support,
        "ppd_present": config.ppd_path.is_file(),
        "filter_present": config.filter_path.is_file(),
        "cupsfilter_present": shutil.which("cupsfilter") is not None,
    }


@app.post("/print/text")
async def print_text(request: TextLabel, _: None = Depends(verify_api_key)) -> dict[str, object]:
    """Render a text label and print it via the native encoder."""
    config = SLPConfig.from_env(request.media, request.density, request.fine_print)
    try:
        image = render_text_image(
            request.text,
            request.media,
            font_size=request.font_size,
            margin=request.margin,
            rotate=request.rotate,
        )
        if image.size != media_pixels(request.media):
            # 90/270 rotation swaps dimensions; refit onto the media canvas.
            image = fit_image_to_media(image, request.media)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    count = await execute_native_print(image, config, request.copies)
    return {
        "status": "printed",
        "engine": "native",
        "native_bytes_per_copy": count,
        "copies": request.copies,
    }


@app.get("/templates")
def templates_index(_: None = Depends(verify_api_key)) -> list[dict[str, object]]:
    """List registered templates with their fields and default media."""
    return [
        {
            "name": template.name,
            "description": template.description,
            "default_media": template.default_media,
            "required_fields": list(template.required_fields),
            "optional_fields": list(template.optional_fields),
        }
        for template in list_templates()
    ]


@app.post("/print/template")
async def print_template(
    request: TemplateLabel, _: None = Depends(verify_api_key)
) -> dict[str, object]:
    """Render a registered template and print it via the native encoder."""
    try:
        image = render_template(request.template, request.fields, media=request.media)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    config = SLPConfig.from_env(density=request.density, fine_print=request.fine_print)
    count = await execute_native_print(image, config, request.copies)
    return {
        "status": "printed",
        "engine": "native",
        "template": request.template,
        "native_bytes_per_copy": count,
        "copies": request.copies,
    }


@app.post("/print/image")
async def print_image(
    file: UploadFile = File(...),
    media: str = Form("AddressSmall"),
    density: str = Form("MediumQuality"),
    fine_print: bool = Form(False),
    copies: int = Form(1, ge=1, le=100),
    _: None = Depends(verify_api_key),
) -> dict[str, object]:
    """Print an uploaded image (native encoder) or PDF (CUPS fallback)."""
    payload = await file.read()
    _read_upload(payload, "file")
    config = SLPConfig.from_env(media, density, fine_print)

    try:
        with Image.open(io.BytesIO(payload)) as source_image:
            source_image.load()
            try:
                image = fit_image_to_media(source_image, media)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
    except UnidentifiedImageError:
        # Not an image PIL can read (e.g. PDF): fall back to the CUPS path.
        suffix = Path(file.filename or "label.bin").suffix or ".bin"
        with tempfile.TemporaryDirectory(prefix="slp650-api-") as temp_dir:
            source = Path(temp_dir) / f"upload{suffix}"
            source.write_bytes(payload)
            count = await execute_print(source, config, copies)
        return {
            "status": "printed",
            "engine": "cups",
            "native_bytes_per_copy": count,
            "copies": copies,
        }

    count = await execute_native_print(image, config, copies)
    return {
        "status": "printed",
        "engine": "native",
        "native_bytes_per_copy": count,
        "copies": copies,
    }


@app.post("/print/raw")
async def print_raw(
    file: UploadFile = File(...),
    copies: int = Form(1, ge=1, le=100),
    _: None = Depends(verify_api_key),
) -> dict[str, object]:
    """Send a previously captured native ``.slp`` stream to the printer."""
    payload = await file.read()
    _read_upload(payload, "native stream")

    config = SLPConfig.from_env()
    try:
        await asyncio.to_thread(send_native_stream, payload, config, copies)
    except SLPError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"status": "printed", "native_bytes_per_copy": len(payload), "copies": copies}
