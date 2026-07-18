"""Command-line interface: encode, capture, and print labels directly.

The CLI does not require a configured CUPS printer queue. It is also the main
tool for capturing printer-native ``.slp`` streams for embedded transports.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from slp650_sdk.config import SLPConfig
from slp650_sdk.errors import SLPError
from slp650_sdk.transport import print_file, send_native_stream


def _print_native(args: argparse.Namespace, config: SLPConfig) -> int:
    """Encode with the pure-Python encoder and optionally print.

    Args:
        args (argparse.Namespace): Parsed CLI arguments.
        config (SLPConfig): Printer configuration.

    Returns:
        int: Size of the native stream in bytes, per copy.

    Raises:
        SLPError: If the input cannot be read or encoded, or sending fails.
    """
    from PIL import Image, UnidentifiedImageError

    from slp650_sdk.native_encoder import encode_image

    try:
        with Image.open(args.input) as image:
            data = encode_image(
                image, density=args.density, fine_print=args.fine_print
            )
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise SLPError(f"Cannot encode {args.input}: {exc}") from exc

    if args.capture is not None:
        args.capture.parent.mkdir(parents=True, exist_ok=True)
        args.capture.write_bytes(data)
    if not args.dry_run:
        send_native_stream(data, config, copies=args.copies)
    return len(data)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv (list[str] | None): Arguments to parse; defaults to ``sys.argv``.

    Returns:
        argparse.Namespace: Parsed arguments.
    """
    parser = argparse.ArgumentParser(
        prog="slp650",
        description="Encode and print labels on a Seiko SLP650/SLP650SE without a CUPS queue.",
    )
    parser.add_argument("input", type=Path, help="PNG, JPEG, PDF, or other CUPS-supported input")
    parser.add_argument("--ppd", type=Path, default=SLPConfig.ppd_path)
    parser.add_argument("--filter", dest="filter_path", type=Path, default=SLPConfig.filter_path)
    parser.add_argument("--device", type=Path, default=SLPConfig.device_path)
    parser.add_argument("--media", default="AddressSmall")
    parser.add_argument(
        "--density",
        choices=("LowQuality", "MediumQuality", "HighQuality"),
        default="MediumQuality",
    )
    parser.add_argument("--fine-print", action="store_true")
    parser.add_argument(
        "--native",
        action="store_true",
        help=(
            "Encode with the pure-Python encoder instead of the CUPS pipeline. "
            "Works on any OS; input must be an image no taller than 576 px."
        ),
    )
    parser.add_argument("--copies", type=int, default=1)
    parser.add_argument("--capture", type=Path, help="Save native printer bytes to this file")
    parser.add_argument("--dry-run", action="store_true", help="Generate/capture but do not print")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the CLI.

    Args:
        argv (list[str] | None): Arguments to parse; defaults to ``sys.argv``.

    Returns:
        int: Process exit code.
    """
    args = parse_args(argv)
    config = SLPConfig(
        ppd_path=args.ppd,
        filter_path=args.filter_path,
        device_path=args.device,
        media=args.media,
        density=args.density,
        fine_print=args.fine_print,
    )
    try:
        if args.native:
            byte_count = _print_native(args, config)
        else:
            byte_count = print_file(
                args.input,
                config,
                copies=args.copies,
                capture_path=args.capture,
                dry_run=args.dry_run,
            )
    except SLPError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    action = "generated" if args.dry_run else "sent"
    print(f"{action} {byte_count} native SLP bytes")
    if args.capture:
        print(f"capture: {args.capture}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
