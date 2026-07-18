"""Pure-Python encoder for the SLP650 native protocol.

Implements docs/03_NATIVE_PROTOCOL.md directly — no CUPS, no GPL filter —
and is verified byte-for-byte against hardware-captured golden fixtures
(``tests/test_native_encoder.py``). The line-compression logic mirrors the
driver's ``CompressRun``/``ProcessLine`` control flow exactly, because parity
depends on its quirks (tab thresholds, 7-dot literals that borrow following
dots, strict smaller-of-raw-or-RLE selection).

Input is a PIL image in reading orientation, as produced by
``slp650_sdk.rendering`` and ``slp650_sdk.patterns``: the x axis is the feed
direction, the y axis spans the printhead.
"""

from __future__ import annotations

from PIL import Image

from slp650_sdk.config import PRINTHEAD_DOTS

#: Density command arguments (SLP650), from the driver and capture-validated.
DENSITY_BYTES: dict[str, int] = {
    "LowQuality": 0xF9,   # 65%
    "MediumQuality": 0x00,  # 100%
    "HighQuality": 0x06,  # 130%
}

#: Dots per millimeter at 300 dpi, as used by the driver's margin math.
_DOTS_PER_MM = 23.622

_CMD_PRINT = 0x04
_CMD_PRINT_RLE = 0x05
_CMD_MARGIN = 0x06
_CMD_TAB = 0x09
_CMD_LINEFEED = 0x0A
_CMD_VERTTAB = 0x0B
_CMD_FORMFEED = 0x0C
_CMD_SPEED = 0x0D
_CMD_DENSITY = 0x0E
_CMD_INDENT = 0x16


def _header(line_dots: int, density: str, fine_print: bool) -> bytearray:
    """Build the page-start command sequence.

    Args:
        line_dots (int): Raster line width in dots (across the printhead).
        density (str): Density name, one of ``DENSITY_BYTES``.
        fine_print (bool): Fine mode (``Speed 0x02``) vs normal (``0x00``).

    Returns:
        bytearray: Margin, Density, Speed, and Indent commands.

    Raises:
        ValueError: If the density name is unknown.
    """
    try:
        density_byte = DENSITY_BYTES[density]
    except KeyError:
        raise ValueError(
            f"Unsupported density {density!r}; use one of {sorted(DENSITY_BYTES)}"
        ) from None

    out = bytearray()
    margin_mm = int((PRINTHEAD_DOTS - line_dots + 7) / _DOTS_PER_MM)
    out += bytes((_CMD_MARGIN, max(margin_mm, 0)))
    out += bytes((_CMD_DENSITY, density_byte))
    out += bytes((_CMD_SPEED, 0x02 if fine_print else 0x00))

    indent = max((PRINTHEAD_DOTS - line_dots) // 2, 0)
    if indent <= 255:
        out += bytes((_CMD_INDENT, indent))
    else:
        out += bytes((_CMD_MARGIN, (indent * 100 + 590) // 1181))
    return out


def _advance(out: bytearray, lines: int) -> None:
    """Append blank-line advance commands.

    Args:
        out (bytearray): Output stream to append to.
        lines (int): Number of blank lines to advance.
    """
    while lines > 0:
        if lines == 1:
            out.append(_CMD_LINEFEED)
            lines = 0
        elif lines > 255:
            out += bytes((_CMD_VERTTAB, 255))
            lines -= 255
        else:
            out += bytes((_CMD_VERTTAB, lines))
            lines = 0


def _rle_line(bits: bytes, byte_count: int) -> bytes:
    """Compress one raster line, mirroring the driver's ``CompressRun``.

    Args:
        bits (bytes): Packed line bitmap, MSB first.
        byte_count (int): Bytes of ``bits`` that belong to the line.

    Returns:
        bytes: Optional Tab command followed by the PrintRLERaster command.
    """
    buffer = bytearray()
    length_index = 0
    first_run = True
    byte_index = 0
    bit_index = 1

    def compress_run(run_count: int, run_is_black: bool, stream: bool) -> None:
        nonlocal byte_index, bit_index, first_run, length_index
        while run_count > 0:
            print_count = run_count
            if first_run:
                # A long leading white run is cheaper as a Tab command.
                if not run_is_black and run_count > 126:
                    print_count = min(print_count, 255)
                    buffer.extend((_CMD_TAB, print_count))
                    run_count -= print_count
                buffer.append(_CMD_PRINT_RLE)
                length_index = len(buffer)
                buffer.append(0)  # patched after trailing-white stripping
                first_run = False
            else:
                remaining_bits = (byte_count - 1 - byte_index) * 8 + 8 - bit_index
                if print_count < 8 and stream and remaining_bits + print_count >= 7:
                    # Short run: emit a 7-dot literal, borrowing the dots
                    # that follow the run from the input stream.
                    value = ((0xFF << (7 - print_count)) & 0xFF) if run_is_black else 0x80
                    for bit_count in range(print_count + 1, 8):
                        if bits[byte_index] & (1 << (7 - bit_index)):
                            value |= 1 << (7 - bit_count)
                        bit_index += 1
                        if bit_index == 8:
                            byte_index += 1
                            bit_index = 0
                    buffer.append(value)
                else:
                    print_count = min(print_count, 63)
                    buffer.append((0x40 + print_count) if run_is_black else print_count)
                run_count -= print_count

    run_is_black = bool(bits[0] & 0x80)
    run_count = 1
    while (
        not (byte_index + 1 == byte_count and bit_index == 8)
        and byte_index < byte_count
    ):
        if bit_index == 8:
            byte_index += 1
            bit_index = 0
        bit_is_black = bool(bits[byte_index] & (1 << (7 - bit_index)))
        if bit_is_black == run_is_black:
            run_count += 1
        else:
            compress_run(run_count, run_is_black, stream=True)
            if byte_index < byte_count:
                run_is_black = bool(bits[byte_index] & (1 << (7 - bit_index)))
                run_count = 1
            else:
                run_count = 0
        bit_index += 1

    # Trailing white is never encoded; only a trailing black run is flushed.
    if run_is_black and run_count:
        compress_run(run_count, run_is_black, stream=False)

    while len(buffer) > 3 and not (buffer[-1] & 0xC0):
        buffer.pop()

    buffer[length_index] = len(buffer) - length_index - 1
    return bytes(buffer)


def _raw_line(bits: bytes, byte_count: int) -> bytes:
    """Build the uncompressed PrintRaster command for one line.

    Args:
        bits (bytes): Packed line bitmap, MSB first.
        byte_count (int): Bytes of ``bits`` that belong to the line.

    Returns:
        bytes: PrintRaster command with trailing zero bytes stripped.
    """
    while byte_count > 0 and bits[byte_count - 1] == 0:
        byte_count -= 1
    return bytes((_CMD_PRINT, byte_count)) + bits[:byte_count]


def _pack_line(
    pixels: object, x: int, height: int, cups_compat: bool
) -> bytearray:
    """Pack one feed line (an image column) into printhead-dot order.

    Args:
        pixels (object): PIL pixel access object of a mode-"1" image.
        x (int): Feed line index (image column).
        height (int): Image height, equal to the raster line width in dots.
        cups_compat (bool): Reproduce the CUPS row mapping (row y → dot
            ``height - y``: row 0 is discarded and the bottom row bleeds onto
            dot 0). When False, the clean flip ``dot = height - 1 - y`` is
            used and every row prints.

    Returns:
        bytearray: Packed line bitmap, MSB first.
    """
    line = bytearray((height + 7) // 8)

    def set_dot(dot: int) -> None:
        line[dot >> 3] |= 0x80 >> (dot & 7)

    if cups_compat:
        if pixels[x, height - 1] == 0:
            set_dot(0)
        for dot in range(1, height):
            if pixels[x, height - dot] == 0:
                set_dot(dot)
    else:
        for dot in range(height):
            if pixels[x, height - 1 - dot] == 0:
                set_dot(dot)
    return line


def encode_image(
    image: Image.Image,
    *,
    density: str = "MediumQuality",
    fine_print: bool = False,
    cups_compat: bool = True,
) -> bytes:
    """Encode a label image into the printer-native SLP byte stream.

    Args:
        image (Image.Image): Label in reading orientation (x = feed
            direction, y = across the printhead). Converted to 1-bit if
            needed; the height must not exceed the printhead (576 dots).
        density (str): Density name, one of ``DENSITY_BYTES``.
        fine_print (bool): Fine mode (``Speed 0x02``).
        cups_compat (bool): Reproduce the CUPS raster path's row mapping
            (see ``_pack_line``); required for byte parity with streams
            captured through the CUPS pipeline.

    Returns:
        bytes: Complete native stream for one label, ending in FormFeed.

    Raises:
        ValueError: If the image is taller than the printhead or the density
            name is unknown.
    """
    if image.height > PRINTHEAD_DOTS:
        raise ValueError(
            f"Image height {image.height} exceeds the {PRINTHEAD_DOTS}-dot printhead"
        )
    if image.mode != "1":
        image = image.convert("1")

    height = image.height
    byte_count = (height + 7) // 8
    pixels = image.load()

    out = _header(height, density, fine_print)
    lines_to_advance = 0
    for x in range(image.width):
        line = _pack_line(pixels, x, height, cups_compat)
        if not any(line):
            lines_to_advance += 1
            continue
        _advance(out, lines_to_advance)
        lines_to_advance = 0
        compressed = _rle_line(bytes(line), byte_count)
        raw = _raw_line(bytes(line), byte_count)
        out += compressed if len(compressed) < len(raw) else raw

    out.append(_CMD_FORMFEED)
    return bytes(out)
