"""Encode documents into the printer-native SLP byte stream.

The current encoder shells out to the open-source Seiko CUPS raster filter:

    input image/PDF -> CUPS raster -> native Seiko SLP byte stream

This keeps the encoder correct-by-construction while the native protocol is
reverse engineered. A pure-Python encoder that removes the CUPS dependency is
the next roadmap milestone (see ROADMAP.md).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from collections.abc import Iterable
from pathlib import Path

from slp650_sdk.config import SLPConfig
from slp650_sdk.errors import SLPError


def _run(
    command: Iterable[str],
    *,
    env: dict[str, str] | None = None,
    stdout_file: Path | None = None,
) -> None:
    """Run a command, optionally redirecting stdout to a file.

    Args:
        command (Iterable[str]): Command and arguments.
        env (dict[str, str] | None): Environment for the child process.
        stdout_file (Path | None): File that receives stdout, if given.

    Raises:
        SLPError: If the command exits with a non-zero status.
    """
    command_list = [str(item) for item in command]
    stdout_handle = None
    try:
        if stdout_file is not None:
            stdout_handle = stdout_file.open("wb")
        completed = subprocess.run(
            command_list,
            env=env,
            stdout=stdout_handle if stdout_handle is not None else subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    finally:
        if stdout_handle is not None:
            stdout_handle.close()

    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace")
        stdout = ""
        if stdout_file is None and isinstance(completed.stdout, bytes):
            stdout = completed.stdout.decode("utf-8", errors="replace")
        raise SLPError(
            f"Command failed ({completed.returncode}): {' '.join(command_list)}\n"
            f"stdout: {stdout}\nstderr: {stderr}"
        )


def validate_environment(config: SLPConfig) -> None:
    """Check that the CUPS tools and Seiko filter are available.

    Args:
        config (SLPConfig): Printer configuration to validate.

    Raises:
        SLPError: If cupsfilter, the PPD, or the filter binary is missing.
    """
    if shutil.which("cupsfilter") is None:
        raise SLPError("cupsfilter was not found. Install cups and cups-filters.")
    if not config.ppd_path.is_file():
        raise SLPError(f"PPD not found: {config.ppd_path}")
    if not config.filter_path.is_file():
        raise SLPError(f"Seiko raster filter not found: {config.filter_path}")
    if not os.access(config.filter_path, os.X_OK):
        raise SLPError(f"Seiko raster filter is not executable: {config.filter_path}")


def input_to_cups_raster(input_path: Path, raster_path: Path, config: SLPConfig) -> None:
    """Convert a supported document/image to 1-bit, 300-dpi CUPS raster.

    Args:
        input_path (Path): PNG, JPEG, PDF, or other CUPS-supported input.
        raster_path (Path): Destination for the CUPS raster data.
        config (SLPConfig): Printer configuration (PPD and media).

    Raises:
        SLPError: If cupsfilter fails.
    """
    _run(
        [
            "cupsfilter",
            "-p", str(config.ppd_path),
            "-m", "application/vnd.cups-raster",
            "-o", f"PageSize={config.media}",
            "-o", "Resolution=300dpi",
            "-o", "ColorModel=Gray",
            str(input_path),
        ],
        stdout_file=raster_path,
    )


def cups_raster_to_native(raster_path: Path, raw_path: Path, config: SLPConfig) -> None:
    """Convert CUPS raster to the native SLP command stream.

    Args:
        raster_path (Path): CUPS raster input file.
        raw_path (Path): Destination for the native SLP byte stream.
        config (SLPConfig): Printer configuration (filter and options).

    Raises:
        SLPError: If the Seiko filter fails.
    """
    env = os.environ.copy()
    env["PPD"] = str(config.ppd_path)
    _run(
        [
            str(config.filter_path),
            "1",                 # CUPS job id
            os.environ.get("USER", "slp650"),
            raster_path.stem,    # title
            "1",                 # copies; repeated by the transport instead
            config.filter_options,
            str(raster_path),
        ],
        env=env,
        stdout_file=raw_path,
    )


def build_native_stream(input_path: Path, config: SLPConfig) -> bytes:
    """Encode an input document into the printer-native SLP byte stream.

    Args:
        input_path (Path): PNG, JPEG, PDF, or other CUPS-supported input.
        config (SLPConfig): Printer configuration.

    Returns:
        bytes: Native SLP command stream for one copy.

    Raises:
        SLPError: If the environment is incomplete or a conversion fails.
    """
    validate_environment(config)
    if not input_path.is_file():
        raise SLPError(f"Input file not found: {input_path}")

    with tempfile.TemporaryDirectory(prefix="slp650-") as temp_dir:
        temp = Path(temp_dir)
        raster = temp / "label.raster"
        native = temp / "label.slp"
        input_to_cups_raster(input_path, raster, config)
        cups_raster_to_native(raster, native, config)
        data = native.read_bytes()
        if not data:
            raise SLPError("The Seiko filter produced an empty native stream.")
        return data
