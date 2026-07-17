"""Tests for slp650_sdk.config."""

from __future__ import annotations

from pathlib import Path

import pytest

from slp650_sdk.config import DPI, MEDIA_POINTS, SLPConfig, media_pixels


def test_media_pixels_address_small() -> None:
    width, height = media_pixels("AddressSmall")
    assert width == 984  # 236.16 pt * 300 dpi / 72
    assert height == 285  # 68.40 pt * 300 dpi / 72


def test_media_pixels_all_media_are_positive() -> None:
    for media in MEDIA_POINTS:
        width, height = media_pixels(media)
        assert width > 0
        assert height > 0


def test_media_pixels_media_badge() -> None:
    # SLP-NWB/NB/NR name badges. CUPS truncates 136.224 pt = 567.6 dots to
    # 567 (capture-validated 2026-07-16), so the canvas must too.
    assert media_pixels("MediaBadge") == (750, 567)


def test_media_pixels_truncates_half_dots() -> None:
    # Return is 45 pt = 187.5 dots: truncated, not rounded.
    assert media_pixels("Return") == (510, 187)


def test_media_pixels_exact_sizes_survive_float_error() -> None:
    # 98.64 pt * 300 / 72 evaluates to 410.99999... in floats; must be 411.
    assert media_pixels("AddressLarge") == (984, 411)


def test_media_pixels_unknown_media_raises() -> None:
    with pytest.raises(ValueError, match="Unsupported media"):
        media_pixels("Bogus")


def test_filter_options_string() -> None:
    config = SLPConfig(media="Shipping", density="HighQuality", fine_print=True)
    assert config.filter_options == (
        "PageSize=Shipping Density=HighQuality FinePrint Resolution=300dpi"
    )


def test_filter_options_uses_cups_boolean_style_for_fine_print_off() -> None:
    # The Seiko filter greps for the literal "noFinePrint"; "FinePrint=False"
    # would silently leave fine mode enabled.
    config = SLPConfig(fine_print=False)
    assert "noFinePrint" in config.filter_options
    assert "FinePrint=" not in config.filter_options


def test_from_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SLP650_DEVICE", "/dev/usb/lp3")
    monkeypatch.setenv("SLP650_PPD", "/tmp/test.ppd")
    config = SLPConfig.from_env(media="Return")
    assert config.device_path == Path("/dev/usb/lp3")
    assert config.ppd_path == Path("/tmp/test.ppd")
    assert config.media == "Return"
    # Untouched values keep their defaults.
    assert config.filter_path == SLPConfig.filter_path


def test_dpi_constant() -> None:
    assert DPI == 300
