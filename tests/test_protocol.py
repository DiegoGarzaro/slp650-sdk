"""Tests for slp650_sdk.protocol."""

from __future__ import annotations

from pathlib import Path

import pytest

from slp650_sdk import protocol
from slp650_sdk.protocol import (
    Command,
    DataRun,
    diff_streams,
    format_diff,
    format_tokens,
    main,
    tokenize,
)


def test_tokenize_recognizes_commands_and_data() -> None:
    tokens = tokenize(b"\xff\xfe\x0a\x0e\xff")
    assert tokens == [
        DataRun(0, b"\xff\xfe"),
        Command(2, 0x0A, "LineFeed"),
        Command(3, 0x0E, "Density"),
        DataRun(4, b"\xff"),
    ]


def test_tokenize_empty_stream() -> None:
    assert tokenize(b"") == []


def test_tokenize_uses_confirmed_arg_lengths(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(protocol.ARG_LENGTHS, 0x0E, 1)
    tokens = tokenize(b"\x0e\xff\x0a")
    assert tokens == [
        Command(0, 0x0E, "Density", b"\xff"),
        Command(2, 0x0A, "LineFeed"),
    ]


def test_format_tokens_collapses_repeated_commands() -> None:
    output = format_tokens(tokenize(b"\x00\x00\x00\x0c"))
    lines = output.splitlines()
    assert len(lines) == 2
    assert "NOP" in lines[0]
    assert "x3" in lines[0]
    assert "FormFeed" in lines[1]


def test_format_tokens_summarizes_uniform_data() -> None:
    output = format_tokens([DataRun(0, b"\xff" * 500)])
    assert "500 bytes, all 0xff" in output


def test_format_tokens_truncates_mixed_data() -> None:
    data = bytes(range(0x80, 0x80 + 40))
    output = format_tokens([DataRun(0, data)], max_data_bytes=8)
    assert "40 bytes:" in output
    assert output.endswith("...")


def test_format_tokens_shows_args(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(protocol.ARG_LENGTHS, 0x0E, 1)
    output = format_tokens(tokenize(b"\x0e\x42"))
    assert "Density" in output
    assert "args: 42" in output


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
    stream.write_bytes(b"\x0e\x0d\xff\xff")
    assert main([str(stream)]) == 0
    output = capsys.readouterr().out
    assert "Density" in output
    assert "Speed" in output


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
