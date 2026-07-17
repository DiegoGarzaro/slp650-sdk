"""Test-pattern label images for protocol reverse engineering.

Each pattern isolates one visual variable. Capturing the native streams of two
patterns that differ in a single feature (via ``slp650 --dry-run --capture``)
and diffing them (via ``slp650-dump a.slp b.slp``) locates the bytes that
encode that feature. See docs/03_NATIVE_PROTOCOL.md.

Images are 1-bit, white background, black marks — exactly what the renderer
would hand to the encoder.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from PIL import Image, ImageDraw

from slp650_sdk.config import media_pixels

#: Known coordinate of the single black dot in the ``pixel`` pattern.
PIXEL_POSITION = (16, 16)

#: Cell edge of the ``checkerboard`` pattern, in pixels.
CHECKERBOARD_CELL = 8


def _white(width: int, height: int) -> Image.Image:
    return Image.new("1", (width, height), 255)


def _black(width: int, height: int) -> Image.Image:
    return Image.new("1", (width, height), 0)


def _pixel(width: int, height: int) -> Image.Image:
    image = _white(width, height)
    image.putpixel(PIXEL_POSITION, 0)
    return image


def _hline(width: int, height: int) -> Image.Image:
    image = _white(width, height)
    draw = ImageDraw.Draw(image)
    y = height // 2
    draw.line([(0, y), (width - 1, y)], fill=0, width=1)
    return image


def _vline(width: int, height: int) -> Image.Image:
    image = _white(width, height)
    draw = ImageDraw.Draw(image)
    x = width // 2
    draw.line([(x, 0), (x, height - 1)], fill=0, width=1)
    return image


def _border(width: int, height: int) -> Image.Image:
    image = _white(width, height)
    draw = ImageDraw.Draw(image)
    draw.rectangle([(0, 0), (width - 1, height - 1)], outline=0, width=1)
    return image


def _checkerboard(width: int, height: int) -> Image.Image:
    image = _white(width, height)
    pixels = image.load()
    for y in range(height):
        for x in range(width):
            if ((x // CHECKERBOARD_CELL) + (y // CHECKERBOARD_CELL)) % 2:
                pixels[x, y] = 0
    return image


#: Pattern name -> factory taking ``(width, height)``.
PATTERNS: dict[str, Callable[[int, int], Image.Image]] = {
    "white": _white,
    "black": _black,
    "pixel": _pixel,
    "hline": _hline,
    "vline": _vline,
    "border": _border,
    "checkerboard": _checkerboard,
}


def generate_pattern(name: str, width: int, height: int) -> Image.Image:
    """Generate a named test pattern.

    Args:
        name (str): Pattern name, one of ``PATTERNS``.
        width (int): Canvas width in pixels.
        height (int): Canvas height in pixels.

    Returns:
        Image.Image: 1-bit image of the pattern.

    Raises:
        ValueError: If ``name`` is not a known pattern.
    """
    try:
        factory = PATTERNS[name]
    except KeyError:
        raise ValueError(f"Unknown pattern {name!r}; use one of {sorted(PATTERNS)}") from None
    return factory(width, height)


def write_patterns(output_dir: Path, width: int, height: int) -> list[Path]:
    """Write every test pattern as a PNG into a directory.

    Args:
        output_dir (Path): Destination directory (created if missing).
        width (int): Canvas width in pixels.
        height (int): Canvas height in pixels.

    Returns:
        list[Path]: Paths of the written PNG files.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name in PATTERNS:
        destination = output_dir / f"pattern_{name}_{width}x{height}.png"
        generate_pattern(name, width, height).save(destination, format="PNG")
        written.append(destination)
    return written


def _parse_size(value: str) -> tuple[int, int]:
    """Parse a ``WIDTHxHEIGHT`` string.

    Args:
        value (str): Size specification, e.g. ``576x300``.

    Returns:
        tuple[int, int]: Width and height in pixels.

    Raises:
        argparse.ArgumentTypeError: If the value is malformed.
    """
    try:
        width_text, height_text = value.lower().split("x")
        width, height = int(width_text), int(height_text)
        if width < 1 or height < 1:
            raise ValueError
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"invalid size {value!r}; expected WIDTHxHEIGHT, e.g. 576x300"
        ) from None
    return width, height


def main(argv: list[str] | None = None) -> int:
    """Run the pattern generator CLI.

    Args:
        argv (list[str] | None): Arguments to parse; defaults to ``sys.argv``.

    Returns:
        int: Process exit code.
    """
    parser = argparse.ArgumentParser(
        prog="slp650-patterns",
        description="Generate 1-bit test-pattern PNGs for protocol reverse engineering.",
    )
    canvas = parser.add_mutually_exclusive_group()
    canvas.add_argument("--media", help="Size the canvas for a media name, e.g. AddressSmall")
    canvas.add_argument(
        "--size",
        type=_parse_size,
        default=(576, 300),
        help="Explicit canvas WIDTHxHEIGHT in pixels (default: 576x300)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("fixtures"),
        help="Output directory (default: ./fixtures)",
    )
    args = parser.parse_args(argv)

    if args.media is not None:
        try:
            width, height = media_pixels(args.media)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
    else:
        width, height = args.size

    for path in write_patterns(args.out, width, height):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
