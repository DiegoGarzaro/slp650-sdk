"""Tests for slp650_sdk.rendering."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from slp650_sdk.config import media_pixels
from slp650_sdk.rendering import load_font, render_text_label, wrap_text


def test_wrap_text_wraps_long_lines() -> None:
    image = Image.new("L", (200, 100), 255)
    draw = ImageDraw.Draw(image)
    font = load_font(20)
    wrapped = wrap_text(draw, "one two three four five six seven eight", font, 100)
    assert "\n" in wrapped
    assert wrapped.replace("\n", " ") == "one two three four five six seven eight"


def test_wrap_text_preserves_blank_lines() -> None:
    image = Image.new("L", (200, 100), 255)
    draw = ImageDraw.Draw(image)
    font = load_font(20)
    assert wrap_text(draw, "a\n\nb", font, 1000) == "a\n\nb"


def test_render_text_label_creates_one_bit_png(tmp_path: Path) -> None:
    destination = tmp_path / "label.png"
    render_text_label("Hello SLP650", "AddressSmall", destination)
    with Image.open(destination) as image:
        assert image.format == "PNG"
        assert image.mode == "1"
        assert image.size == media_pixels("AddressSmall")


def test_render_text_label_rotation_swaps_dimensions(tmp_path: Path) -> None:
    destination = tmp_path / "label.png"
    render_text_label("Hello", "AddressSmall", destination, rotate=90)
    width, height = media_pixels("AddressSmall")
    with Image.open(destination) as image:
        assert image.size == (height, width)


def test_render_text_label_rejects_invalid_rotation(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="rotate"):
        render_text_label("Hello", "AddressSmall", tmp_path / "label.png", rotate=45)


def test_render_text_label_rejects_unknown_media(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unsupported media"):
        render_text_label("Hello", "Bogus", tmp_path / "label.png")
