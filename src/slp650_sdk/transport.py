"""Send native SLP byte streams to a printer device.

This is the Linux usblp transport. Other transports (embedded USB hosts,
network print agents) consume the same byte stream; see
docs/09_EMBEDDED_TRANSPORT.md.
"""

from __future__ import annotations

import fcntl
import os
from pathlib import Path

from slp650_sdk.config import SLPConfig
from slp650_sdk.encoder import build_native_stream
from slp650_sdk.errors import SLPError

MAX_COPIES = 100


def write_all(fd: int, data: bytes) -> None:
    """Write the whole buffer to a file descriptor.

    Args:
        fd (int): Open file descriptor of the printer device.
        data (bytes): Native SLP byte stream.

    Raises:
        SLPError: If the device stops accepting bytes.
    """
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise SLPError("The printer device accepted zero bytes.")
        view = view[written:]


def send_native_stream(data: bytes, config: SLPConfig, copies: int = 1) -> None:
    """Send a native SLP stream to the printer device.

    Access is serialized with an exclusive file lock so concurrent jobs
    cannot interleave bytes on the device.

    Args:
        data (bytes): Native SLP byte stream for one copy.
        config (SLPConfig): Printer configuration.
        copies (int): Number of copies, between 1 and ``MAX_COPIES``.

    Raises:
        SLPError: If ``copies`` is out of range or the device is missing.
    """
    if copies < 1 or copies > MAX_COPIES:
        raise SLPError(f"copies must be between 1 and {MAX_COPIES}")
    if not config.device_path.exists():
        raise SLPError(
            f"Printer device not found: {config.device_path}. "
            "Check lsusb, dmesg, and the usblp kernel module."
        )

    config.lock_path.parent.mkdir(parents=True, exist_ok=True)
    with config.lock_path.open("a+b") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        fd = os.open(config.device_path, os.O_WRONLY)
        try:
            for _ in range(copies):
                write_all(fd, data)
        finally:
            os.close(fd)
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def print_file(
    input_path: Path,
    config: SLPConfig,
    copies: int = 1,
    capture_path: Path | None = None,
    dry_run: bool = False,
) -> int:
    """Encode an input document and send it to the printer.

    Args:
        input_path (Path): PNG, JPEG, PDF, or other CUPS-supported input.
        config (SLPConfig): Printer configuration.
        copies (int): Number of copies to print.
        capture_path (Path | None): Also save the native bytes to this file.
        dry_run (bool): Encode (and capture) without touching the device.

    Returns:
        int: Size of the native stream in bytes, per copy.

    Raises:
        SLPError: If encoding or sending fails.
    """
    data = build_native_stream(input_path, config)
    if capture_path is not None:
        capture_path.parent.mkdir(parents=True, exist_ok=True)
        capture_path.write_bytes(data)
    if not dry_run:
        send_native_stream(data, config, copies=copies)
    return len(data)
