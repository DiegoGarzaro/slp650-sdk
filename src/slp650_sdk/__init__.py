"""SDK for the Seiko SLP650/SLP650SE label printer.

The SDK is split along the project architecture (see docs/01_ARCHITECTURE.md):

- ``rendering``: label content -> monochrome bitmap
- ``encoder``: bitmap/document -> printer-native SLP byte stream
- ``transport``: SLP byte stream -> printer device
"""

from __future__ import annotations

from slp650_sdk.config import DPI, MEDIA_POINTS, PRINTHEAD_DOTS, SLPConfig, media_pixels
from slp650_sdk.encoder import build_native_stream
from slp650_sdk.errors import SLPError
from slp650_sdk.native_encoder import encode_image
from slp650_sdk.transport import print_file, send_native_stream

__version__ = "0.2.0"

__all__ = [
    "DPI",
    "MEDIA_POINTS",
    "PRINTHEAD_DOTS",
    "SLPConfig",
    "SLPError",
    "__version__",
    "build_native_stream",
    "encode_image",
    "media_pixels",
    "print_file",
    "send_native_stream",
]
