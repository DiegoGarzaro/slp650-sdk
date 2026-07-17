"""Inspect and diff captured printer-native ``.slp`` streams.

This is the reverse-engineering companion to docs/03_NATIVE_PROTOCOL.md. The
tokenizer knows the command bytes observed in the open-source driver; argument
encodings are still being discovered, so tokenization is **heuristic**: a byte
inside an undecoded payload that happens to match a command value is labeled
as a command. Every time an argument length is confirmed on real captures, add
it to ``ARG_LENGTHS`` and the dumps become more accurate.

Console script: ``slp650-dump FILE [FILE2]`` (one file: annotated dump; two
files: diff).
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

#: Command bytes observed in the open-source Seiko driver.
COMMANDS: dict[int, str] = {
    0x00: "NOP",
    0x01: "Status",
    0x02: "Version",
    0x04: "PrintRaster",
    0x05: "PrintRLERaster",
    0x06: "Margin",
    0x07: "Repeat",
    0x0A: "LineFeed",
    0x0C: "FormFeed",
    0x0D: "Speed",
    0x0E: "Density",
    0x0F: "Reset",
    0x12: "Model",
    0x16: "Indent",
    0x17: "FineMode",
}

#: Confirmed argument byte counts per command. Intentionally empty until each
#: encoding is verified against real captures — record the evidence in
#: docs/03_NATIVE_PROTOCOL.md before adding an entry here.
ARG_LENGTHS: dict[int, int] = {}


@dataclass(frozen=True)
class Command:
    """A recognized command byte, with arguments when their length is known.

    Attributes:
        offset (int): Byte offset in the stream.
        byte (int): Command byte value.
        name (str): Human-readable command name.
        args (bytes): Argument bytes (empty while the length is unknown).
    """

    offset: int
    byte: int
    name: str
    args: bytes = b""


@dataclass(frozen=True)
class DataRun:
    """A run of bytes not recognized as commands.

    Attributes:
        offset (int): Byte offset in the stream.
        data (bytes): The raw bytes.
    """

    offset: int
    data: bytes


def tokenize(stream: bytes) -> list[Command | DataRun]:
    """Split a native stream into recognized commands and data runs.

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


def _hex(data: bytes) -> str:
    return " ".join(f"{byte:02x}" for byte in data)


def _summarize_data(data: bytes, max_bytes: int) -> str:
    unique = set(data)
    if len(unique) == 1:
        return f"{len(data)} bytes, all 0x{data[0]:02x}"
    shown = _hex(data[:max_bytes])
    suffix = " ..." if len(data) > max_bytes else ""
    return f"{len(data)} bytes: {shown}{suffix}"


def format_tokens(tokens: list[Command | DataRun], max_data_bytes: int = 16) -> str:
    """Render tokens as an annotated, run-collapsed dump.

    Consecutive identical argument-less commands (e.g. ``NOP`` padding) are
    collapsed into a single line with a repeat count.

    Args:
        tokens (list[Command | DataRun]): Tokens from ``tokenize``.
        max_data_bytes (int): Hex bytes shown per data run before truncating.

    Returns:
        str: Human-readable dump, one token (or collapsed run) per line.
    """
    lines: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if isinstance(token, DataRun):
            summary = _summarize_data(token.data, max_data_bytes)
            lines.append(f"{token.offset:#08x}  data  {summary}")
            index += 1
            continue

        repeat = 1
        while (
            not token.args
            and index + repeat < len(tokens)
            and isinstance(tokens[index + repeat], Command)
            and tokens[index + repeat].byte == token.byte
            and not tokens[index + repeat].args
        ):
            repeat += 1
        line = f"{token.offset:#08x}  0x{token.byte:02x} {token.name}"
        if token.args:
            line += f"  args: {_hex(token.args)}"
        if repeat > 1:
            line += f"  x{repeat}"
        lines.append(line)
        index += repeat
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
        int: Process exit code.
    """
    parser = argparse.ArgumentParser(
        prog="slp650-dump",
        description=(
            "Annotated dump of a captured .slp stream, or a diff of two. "
            "Tokenization is heuristic until command argument lengths are confirmed."
        ),
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
