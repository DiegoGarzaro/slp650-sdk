"""Tests for slp650_sdk.protocol.

The byte vectors marked "captured" are real fragments from SLP650 streams
captured on hardware on 2026-07-16 (see docs/03_NATIVE_PROTOCOL.md).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from slp650_sdk import protocol
from slp650_sdk.protocol import (
    Command,
    DataRun,
    decode_raster,
    decode_rle,
    diff_streams,
    format_diff,
    format_tokens,
    main,
    tokenize,
)

# Captured: complete stream of an all-white AddressSmall label.
WHITE_LABEL = bytes.fromhex("060c0e000d0216910c")

# Captured: one hline raster line (Tab 143, then RLE with a single black dot).
HLINE_LINE = bytes.fromhex("098f0501c0")


def test_tokenize_white_label_header() -> None:
    assert tokenize(WHITE_LABEL) == [
        Command(0, 0x06, "Margin", b"\x0c"),
        Command(2, 0x0E, "Density", b"\x00"),
        Command(4, 0x0D, "Speed", b"\x02"),
        Command(6, 0x16, "Indent", b"\x91"),
        Command(8, 0x0C, "FormFeed"),
    ]


def test_tokenize_length_prefixed_print_commands() -> None:
    tokens = tokenize(HLINE_LINE)
    assert tokens == [
        Command(0, 0x09, "Tab", b"\x8f"),
        Command(2, 0x05, "PrintRLERaster", b"\xc0"),
    ]


def test_tokenize_empty_stream() -> None:
    assert tokenize(b"") == []


def test_tokenize_unknown_bytes_become_data() -> None:
    tokens = tokenize(b"\xfe\xfd\x0a")
    assert tokens == [
        DataRun(0, b"\xfe\xfd"),
        Command(2, 0x0A, "LineFeed"),
    ]


def test_tokenize_uses_added_arg_lengths(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(protocol.ARG_LENGTHS, 0x12, 1)
    assert tokenize(b"\x12\xfe") == [Command(0, 0x12, "Model", b"\xfe")]


def test_decode_rle_solid_black_line() -> None:
    # Captured: full-black 285-dot line (black pattern, AddressSmall).
    assert decode_rle(bytes.fromhex("7f7f7f7f61")) == [(True, 285)]


def test_decode_rle_single_dot_with_literal() -> None:
    # Captured: pixel pattern line after Tab 255: white 14 dots, then a
    # literal chunk 0xC0 = 1 black dot + 6 white dots.
    assert decode_rle(bytes.fromhex("0ec0")) == [(False, 14), (True, 1), (False, 6)]


def test_decode_rle_black_run_offset() -> None:
    # 0x40-0x7F are black runs of (value - 64) dots.
    assert decode_rle(b"\x41") == [(True, 1)]
    assert decode_rle(b"\x7f") == [(True, 63)]


def test_decode_rle_merges_adjacent_runs_and_drops_empty() -> None:
    # 0x40 is a zero-length black run and must disappear.
    assert decode_rle(b"\x7f\x40\x7f") == [(True, 126)]


def test_decode_raster_runs() -> None:
    # Captured: border middle line, raw bitmap 0xC0 = 2 black then 6 white.
    assert decode_raster(b"\xc0") == [(True, 2), (False, 6)]
    # Captured: checkerboard bitmap fragment.
    assert decode_raster(b"\xfc\x03") == [(True, 6), (False, 8), (True, 2)]


def test_format_tokens_decodes_rle_lines() -> None:
    output = format_tokens(tokenize(b"\x05\x05\x7f\x7f\x7f\x7f\x61"))
    assert "PrintRLERaster" in output
    assert "285 dots: black 285" in output


def test_format_tokens_collapses_repeated_commands() -> None:
    output = format_tokens(tokenize(b"\x00\x00\x00\x0c"))
    lines = output.splitlines()
    assert len(lines) == 2
    assert "NOP" in lines[0]
    assert "x3" in lines[0]
    assert "FormFeed" in lines[1]


def test_format_tokens_collapses_repeated_sequences() -> None:
    # hline is 984 repetitions of (Tab 143, PrintRLE one-dot line).
    output = format_tokens(tokenize(HLINE_LINE * 984))
    assert "[984 repeats of 2 commands]" in output
    assert len(output.splitlines()) == 3


def test_format_tokens_summarizes_uniform_data() -> None:
    output = format_tokens([DataRun(0, b"\xff" * 500)])
    assert "500 bytes, all 0xff" in output


def test_format_tokens_truncates_mixed_data() -> None:
    data = bytes(range(0x80, 0x80 + 40))
    output = format_tokens([DataRun(0, data)], max_data_bytes=8)
    assert "40 bytes:" in output
    assert output.endswith("...")


def test_diff_identical_streams() -> None:
    result = diff_streams(b"abc", b"abc")
    assert result.identical
    assert "identical" in format_diff(b"abc", b"abc", result)


def test_diff_locates_divergence() -> None:
    a = b"\x01\x02\x03\x04"
    b = b"\x01\x02\xff\x04"
    result = diff_streams(a, b)
    assert not result.identical
    assert result.prefix_length == 2
    assert result.suffix_length == 1
    report = format_diff(a, b, result)
    assert "offset 0x2" in report


def test_diff_handles_different_lengths() -> None:
    result = diff_streams(b"\x01\x02", b"\x01\x02\x03")
    assert not result.identical
    assert result.prefix_length == 2


def test_cli_dump(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    stream = tmp_path / "a.slp"
    stream.write_bytes(WHITE_LABEL)
    assert main([str(stream)]) == 0
    output = capsys.readouterr().out
    for name in ("Margin", "Density", "Speed", "Indent", "FormFeed"):
        assert name in output


def test_cli_diff_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    a = tmp_path / "a.slp"
    b = tmp_path / "b.slp"
    a.write_bytes(b"\x01\x02\x03")
    b.write_bytes(b"\x01\xff\x03")
    assert main([str(a), str(a)]) == 0
    assert main([str(a), str(b)]) == 2
    assert "divergence" in capsys.readouterr().out


def test_cli_missing_file(tmp_path: Path) -> None:
    assert main([str(tmp_path / "missing.slp")]) == 1
