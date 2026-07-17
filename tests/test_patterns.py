"""Tests for slp650_sdk.patterns."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from slp650_sdk.patterns import (
    PATTERNS,
    PIXEL_POSITION,
    generate_pattern,
    main,
    write_patterns,
)

WIDTH, HEIGHT = 64, 48


@pytest.mark.parametrize("name", sorted(PATTERNS))
def test_patterns_have_correct_size_and_mode(name: str) -> None:
    image = generate_pattern(name, WIDTH, HEIGHT)
    assert image.size == (WIDTH, HEIGHT)
    assert image.mode == "1"


def test_white_is_all_white() -> None:
    assert generate_pattern("white", WIDTH, HEIGHT).getextrema() == (255, 255)


def test_black_is_all_black() -> None:
    assert generate_pattern("black", WIDTH, HEIGHT).getextrema() == (0, 0)


def test_pixel_has_exactly_one_black_dot() -> None:
    image = generate_pattern("pixel", WIDTH, HEIGHT)
    assert image.getpixel(PIXEL_POSITION) == 0
    black_count = image.histogram()[0]
    assert black_count == 1


def test_hline_is_one_row() -> None:
    image = generate_pattern("hline", WIDTH, HEIGHT)
    y = HEIGHT // 2
    assert image.getpixel((0, y)) == 0
    assert image.getpixel((WIDTH - 1, y)) == 0
    assert image.getpixel((0, y - 2)) == 255
    assert image.histogram()[0] == WIDTH


def test_vline_is_one_column() -> None:
    image = generate_pattern("vline", WIDTH, HEIGHT)
    x = WIDTH // 2
    assert image.getpixel((x, 0)) == 0
    assert image.getpixel((x, HEIGHT - 1)) == 0
    assert image.histogram()[0] == HEIGHT


def test_checkerboard_has_both_colors() -> None:
    image = generate_pattern("checkerboard", WIDTH, HEIGHT)
    assert image.getextrema() == (0, 255)
    # Cell (0,0) is white, its right neighbor cell is black.
    assert image.getpixel((0, 0)) == 255
    assert image.getpixel((8, 0)) == 0


def test_border_avoids_dead_row_zero() -> None:
    # Image row 0 maps to a printhead dot that does not exist; the border's
    # top edge must sit at row 1 to actually print.
    image = generate_pattern("border", WIDTH, HEIGHT)
    assert image.getpixel((WIDTH // 2, 0)) == 255
    assert image.getpixel((WIDTH // 2, 1)) == 0
    assert image.getpixel((WIDTH // 2, HEIGHT - 1)) == 0
    assert image.getpixel((0, HEIGHT // 2)) == 0
    assert image.getpixel((WIDTH - 1, HEIGHT // 2)) == 0


def test_edges_probes_four_distinct_rows() -> None:
    image = generate_pattern("edges", WIDTH, HEIGHT)
    # Row 0 full width, row 1 three quarters, row h-2 half, row h-1 quarter.
    assert image.getpixel((WIDTH - 1, 0)) == 0
    assert image.getpixel((int(WIDTH * 0.75) - 1, 1)) == 0
    assert image.getpixel((int(WIDTH * 0.75), 1)) == 255
    assert image.getpixel((WIDTH // 2 - 1, HEIGHT - 2)) == 0
    assert image.getpixel((WIDTH // 2, HEIGHT - 2)) == 255
    assert image.getpixel((WIDTH // 4 - 1, HEIGHT - 1)) == 0
    assert image.getpixel((WIDTH // 4, HEIGHT - 1)) == 255
    expected_black = WIDTH + int(WIDTH * 0.75) + WIDTH // 2 + WIDTH // 4
    assert image.histogram()[0] == expected_black


def test_unknown_pattern_raises() -> None:
    with pytest.raises(ValueError, match="Unknown pattern"):
        generate_pattern("bogus", WIDTH, HEIGHT)


def test_write_patterns_creates_all_files(tmp_path: Path) -> None:
    written = write_patterns(tmp_path, WIDTH, HEIGHT)
    assert len(written) == len(PATTERNS)
    for path in written:
        assert path.is_file()
        with Image.open(path) as image:
            assert image.format == "PNG"
            assert image.size == (WIDTH, HEIGHT)


def test_cli_with_media(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["--media", "Return", "--out", str(tmp_path)])
    assert exit_code == 0
    output = capsys.readouterr().out
    assert "pattern_white_510x187.png" in output
    assert len(list(tmp_path.glob("*.png"))) == len(PATTERNS)


def test_cli_rejects_unknown_media(tmp_path: Path) -> None:
    assert main(["--media", "Bogus", "--out", str(tmp_path)]) == 1
