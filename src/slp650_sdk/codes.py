"""QR code and barcode rendering for labels.

Per the rendering rules (docs/05_RENDERING.md), codes are always rendered
host-side to 1-bit images and composited onto the label bitmap; the printer
never receives barcode commands.
"""

from __future__ import annotations

import io

import barcode as barcode_lib
import qrcode
from barcode.writer import ImageWriter
from PIL import Image


def qr_image(data: str, size: int, *, border_modules: int = 2) -> Image.Image:
    """Render a QR code as a square 1-bit image.

    Args:
        data (str): Payload to encode (URL, vCard, plain text, ...).
        size (int): Output edge length in pixels. The QR is scaled with
            nearest-neighbor so modules stay crisp; the actual module grid is
            padded by the quiet zone.
        border_modules (int): Quiet-zone width in modules (the QR spec
            recommends 4; 2 is usually fine on high-contrast thermal paper).

    Returns:
        Image.Image: 1-bit image of ``size`` x ``size`` pixels.
    """
    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=border_modules,
    )
    qr.add_data(data)
    qr.make(fit=True)
    image = qr.make_image().get_image().convert("L")
    return image.resize((size, size), Image.Resampling.NEAREST).convert(
        "1", dither=Image.Dither.NONE
    )


def code128_image(data: str, *, width: int, height: int) -> Image.Image:
    """Render a Code 128 barcode as a 1-bit image.

    The barcode is generated at its natural module size and then scaled with
    nearest-neighbor to the requested box, which can distort narrow bars
    slightly — verify scannability on a printed label before relying on it.

    Args:
        data (str): Payload to encode.
        width (int): Output width in pixels.
        height (int): Output height in pixels.

    Returns:
        Image.Image: 1-bit image of ``width`` x ``height`` pixels.
    """
    code = barcode_lib.Code128(data, writer=ImageWriter())
    buffer = io.BytesIO()
    code.write(
        buffer,
        options={
            "write_text": False,
            "quiet_zone": 2.0,
            "module_height": 10.0,
        },
    )
    buffer.seek(0)
    with Image.open(buffer) as rendered:
        image = rendered.convert("L")
    return image.resize((width, height), Image.Resampling.NEAREST).convert(
        "1", dither=Image.Dither.NONE
    )
