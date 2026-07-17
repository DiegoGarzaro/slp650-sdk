"""Parse, inspect, and diff printer-native ``.slp`` streams.

The protocol was decoded on 2026-07-16 from captured streams cross-checked
against the GPL driver source (``SeikoSLPCommands.h``, ``RasterToSIISLP.cxx``,
``SIISLPProcessBitmap.cxx``). Full specification and evidence:
docs/03_NATIVE_PROTOCOL.md.

Console script: ``slp650-dump FILE [FILE2]`` (one file: annotated dump; two
files: diff).
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

#: Command bytes, from the driver's SeikoSLPCommands.h.
COMMANDS: dict[int, str] = {
    0x00: "NOP",
    0x01: "Status",
    0x02: "Version",
    0x03: "BaudRate",
    0x04: "PrintRaster",
    0x05: "PrintRLERaster",
    0x06: "Margin",
    0x07: "Repeat",
    0x09: "Tab",
    0x0A: "LineFeed",
    0x0B: "VertTab",
    0x0C: "FormFeed",
    0x0D: "Speed",
    0x0E: "Density",
    0x0F: "Reset",
    0x12: "Model",
    0x16: "Indent",
    0x17: "FineMode",
    0x1B: "SetSerialNumber",
    0xA5: "Check",
}

#: Confirmed 1-byte-argument commands (driver ``SendPrinterCommand(cmd, arg)``
#: call sites plus capture evidence; see docs/03_NATIVE_PROTOCOL.md).
ARG_LENGTHS: dict[int, int] = {
    0x06: 1,  # Margin: value in mm (23.622 dots/mm at 300 dpi)
    0x09: 1,  # Tab: leading white dots within the current line
    0x0B: 1,  # VertTab: blank lines to advance
    0x0D: 1,  # Speed: 0x02 = fine mode, 0x00 = normal (SLP650)
    0x0E: 1,  # Density: signed; 0xF9 = 65%, 0x00 = 100%, 0x06 = 130%
    0x16: 1,  # Indent: left margin in dots
    0x17: 1,  # FineMode: used on older models instead of Speed
}

#: Commands followed by ``<length byte> <payload>``.
LENGTH_PREFIXED: frozenset[int] = frozenset({0x04, 0x05})


@dataclass(frozen=True)
class Command:
    """A parsed command.

    Attributes:
        offset (int): Byte offset in the stream.
        byte (int): Command byte value.
        name (str): Human-readable command name.
        args (bytes): Argument bytes (for length-prefixed commands, the
            payload without the length byte).
    """

    offset: int
    byte: int
    name: str
    args: bytes = b""

    def key(self) -> tuple[int, bytes]:
        """Identity of the command ignoring its stream offset.

        Returns:
            tuple[int, bytes]: Command byte and arguments.
        """
        return (self.byte, self.args)


@dataclass(frozen=True)
class DataRun:
    """A run of bytes not recognized as commands.

    Attributes:
        offset (int): Byte offset in the stream.
        data (bytes): The raw bytes.
    """

    offset: int
    data: bytes

    def key(self) -> tuple[str, bytes]:
        """Identity of the run ignoring its stream offset.

        Returns:
            tuple[str, bytes]: Marker and raw bytes.
        """
        return ("data", self.data)


def tokenize(stream: bytes) -> list[Command | DataRun]:
    """Split a native stream into commands and unrecognized data runs.

    Args:
        stream (bytes): Captured printer-native byte stream.

    Returns:
        list[Command | DataRun]: Tokens in stream order.
    """
    tokens: list[Command | DataRun] = []
    data_start: int | None = None
    position = 0

    def flush_data(end: int) -> None:
        nonlocal data_start
        if data_start is not None:
            tokens.append(DataRun(data_start, stream[data_start:end]))
            data_start = None

    while position < len(stream):
        byte = stream[position]
        if byte in COMMANDS:
            flush_data(position)
            if byte in LENGTH_PREFIXED and position + 1 < len(stream):
                length = stream[position + 1]
                args = stream[position + 2 : position + 2 + length]
                tokens.append(Command(position, byte, COMMANDS[byte], args))
                position += 2 + length
            else:
                length = ARG_LENGTHS.get(byte, 0)
                args = stream[position + 1 : position + 1 + length]
                tokens.append(Command(position, byte, COMMANDS[byte], args))
                position += 1 + length
        else:
            if data_start is None:
                data_start = position
            position += 1
    flush_data(len(stream))
    return tokens


def decode_rle(payload: bytes) -> list[tuple[bool, int]]:
    """Decode a PrintRLERaster (0x05) payload into dot runs.

    Encoding (from the driver's ``CompressRun``):

    - ``0x00``-``0x3F``: white run of N dots
    - ``0x40``-``0x7F``: black run of N - 64 dots
    - ``0x80``-``0xFF``: literal chunk; bits 6..0 are 7 dots, MSB first

    Args:
        payload (bytes): RLE bytes (without command and length bytes).

    Returns:
        list[tuple[bool, int]]: Runs as ``(is_black, dot_count)``, with
            adjacent same-color runs merged; zero-length runs dropped.
    """
    runs: list[tuple[bool, int]] = []

    def append(is_black: bool, count: int) -> None:
        if count <= 0:
            return
        if runs and runs[-1][0] == is_black:
            runs[-1] = (is_black, runs[-1][1] + count)
        else:
            runs.append((is_black, count))

    for value in payload:
        if value < 0x40:
            append(False, value)
        elif value < 0x80:
            append(True, value - 0x40)
        else:
            for bit in range(6, -1, -1):
                append(bool(value & (1 << bit)), 1)
    return runs


def decode_raster(payload: bytes) -> list[tuple[bool, int]]:
    """Decode a PrintRaster (0x04) bitmap payload into dot runs.

    Args:
        payload (bytes): Raw bitmap bytes (without command and length bytes),
            one dot per bit, MSB first.

    Returns:
        list[tuple[bool, int]]: Runs as ``(is_black, dot_count)``.
    """
    runs: list[tuple[bool, int]] = []
    for value in payload:
        for bit in range(7, -1, -1):
            is_black = bool(value & (1 << bit))
            if runs and runs[-1][0] == is_black:
                runs[-1] = (is_black, runs[-1][1] + 1)
            else:
                runs.append((is_black, 1))
    return runs


def _format_runs(runs: list[tuple[bool, int]]) -> str:
    total = sum(count for _, count in runs)
    parts = ", ".join(
        f"{'black' if is_black else 'white'} {count}" for is_black, count in runs
    )
    return f"{total} dots: {parts}" if runs else "0 dots"


def _hex(data: bytes) -> str:
    return " ".join(f"{byte:02x}" for byte in data)


def _summarize_data(data: bytes, max_bytes: int) -> str:
    unique = set(data)
    if len(unique) == 1:
        return f"{len(data)} bytes, all 0x{data[0]:02x}"
    shown = _hex(data[:max_bytes])
    suffix = " ..." if len(data) > max_bytes else ""
    return f"{len(data)} bytes: {shown}{suffix}"


def _format_token(token: Command | DataRun, max_data_bytes: int) -> str:
    if isinstance(token, DataRun):
        return f"data  {_summarize_data(token.data, max_data_bytes)}"
    line = f"0x{token.byte:02x} {token.name}"
    if token.byte == 0x05:
        line += f"  {len(token.args)} bytes -> {_format_runs(decode_rle(token.args))}"
    elif token.byte == 0x04:
        line += f"  {len(token.args)} bytes -> {_format_runs(decode_raster(token.args))}"
    elif token.args:
        line += f"  args: {_hex(token.args)}"
    return line


@dataclass
class _Block:
    """A repeating group of tokens found by ``_collapse``."""

    tokens: list[Command | DataRun]
    repeat: int = 1
    period: int = field(default=1)


def _collapse(tokens: list[Command | DataRun], max_period: int = 4) -> list[_Block]:
    """Group consecutive repeats of short token sequences.

    Args:
        tokens (list[Command | DataRun]): Tokens in stream order.
        max_period (int): Longest repeating sequence to detect.

    Returns:
        list[_Block]: Blocks in stream order; ``repeat`` > 1 marks a
            collapsed repetition of ``period`` tokens.
    """
    blocks: list[_Block] = []
    index = 0
    keys = [token.key() for token in tokens]
    while index < len(tokens):
        best_period = 0
        best_repeat = 1
        for period in range(1, max_period + 1):
            repeat = 1
            while (
                index + (repeat + 1) * period <= len(tokens)
                and keys[index + repeat * period : index + (repeat + 1) * period]
                == keys[index : index + period]
            ):
                repeat += 1
            if repeat > 1 and repeat * period > best_repeat * best_period:
                best_period, best_repeat = period, repeat
        if best_repeat > 1:
            blocks.append(
                _Block(tokens[index : index + best_period], best_repeat, best_period)
            )
            index += best_repeat * best_period
        else:
            blocks.append(_Block([tokens[index]]))
            index += 1
    return blocks


def format_tokens(tokens: list[Command | DataRun], max_data_bytes: int = 16) -> str:
    """Render tokens as an annotated dump with repeated sequences collapsed.

    Args:
        tokens (list[Command | DataRun]): Tokens from ``tokenize``.
        max_data_bytes (int): Hex bytes shown per data run before truncating.

    Returns:
        str: Human-readable dump.
    """
    lines: list[str] = []
    for block in _collapse(tokens):
        first = block.tokens[0]
        if block.repeat == 1:
            lines.append(f"{first.offset:#08x}  {_format_token(first, max_data_bytes)}")
        elif block.period == 1:
            lines.append(
                f"{first.offset:#08x}  {_format_token(first, max_data_bytes)}"
                f"  x{block.repeat}"
            )
        else:
            lines.append(
                f"{first.offset:#08x}  [{block.repeat} repeats of "
                f"{block.period} commands]"
            )
            for token in block.tokens:
                lines.append(f"            {_format_token(token, max_data_bytes)}")
    return "\n".join(lines)


@dataclass(frozen=True)
class StreamDiff:
    """Result of comparing two byte streams.

    Attributes:
        a_length (int): Length of the first stream.
        b_length (int): Length of the second stream.
        prefix_length (int): Bytes identical from the start.
        suffix_length (int): Bytes identical from the end (outside the prefix).
    """

    a_length: int
    b_length: int
    prefix_length: int
    suffix_length: int

    @property
    def identical(self) -> bool:
        """Whether the two streams are byte-for-byte equal.

        Returns:
            bool: True if both streams match entirely.
        """
        return self.a_length == self.b_length == self.prefix_length


def diff_streams(a: bytes, b: bytes) -> StreamDiff:
    """Locate where two native streams diverge.

    Args:
        a (bytes): First stream.
        b (bytes): Second stream.

    Returns:
        StreamDiff: Common prefix/suffix lengths and stream sizes.
    """
    limit = min(len(a), len(b))
    prefix = 0
    while prefix < limit and a[prefix] == b[prefix]:
        prefix += 1

    suffix = 0
    while suffix < limit - prefix and a[len(a) - 1 - suffix] == b[len(b) - 1 - suffix]:
        suffix += 1

    return StreamDiff(len(a), len(b), prefix, suffix)


def format_diff(a: bytes, b: bytes, result: StreamDiff, context: int = 16) -> str:
    """Render a diff result with hex context around the first divergence.

    Args:
        a (bytes): First stream.
        b (bytes): Second stream.
        result (StreamDiff): Output of ``diff_streams``.
        context (int): Bytes of context shown on each side of the divergence.

    Returns:
        str: Human-readable diff report.
    """
    if result.identical:
        return f"streams are identical ({result.a_length} bytes)"

    lines = [
        f"a: {result.a_length} bytes, b: {result.b_length} bytes",
        f"common prefix: {result.prefix_length} bytes, common suffix: {result.suffix_length} bytes",
        f"first divergence at offset {result.prefix_length:#x}",
    ]
    start = max(0, result.prefix_length - context)
    end = result.prefix_length + context
    lines.append(f"a[{start:#x}:]: {_hex(a[start:end])}")
    lines.append(f"b[{start:#x}:]: {_hex(b[start:end])}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Run the stream inspector CLI.

    Args:
        argv (list[str] | None): Arguments to parse; defaults to ``sys.argv``.

    Returns:
        int: Process exit code (diff mode: 2 when streams differ).
    """
    parser = argparse.ArgumentParser(
        prog="slp650-dump",
        description="Annotated dump of a captured .slp stream, or a diff of two.",
    )
    parser.add_argument("file", type=Path, help="Captured .slp stream")
    parser.add_argument("file2", type=Path, nargs="?", help="Second stream to diff against")
    parser.add_argument(
        "--context",
        type=int,
        default=16,
        help="Hex context bytes around a divergence (diff mode, default: 16)",
    )
    args = parser.parse_args(argv)

    try:
        a = args.file.read_bytes()
        b = args.file2.read_bytes() if args.file2 is not None else None
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if b is None:
        print(format_tokens(tokenize(a)))
        return 0

    result = diff_streams(a, b)
    print(format_diff(a, b, result, context=args.context))
    return 0 if result.identical else 2


if __name__ == "__main__":
    raise SystemExit(main())
