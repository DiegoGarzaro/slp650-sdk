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


def test_media_pixels_unknown_media_raises() -> None:
    with pytest.raises(ValueError, match="Unsupported media"):
        media_pixels("Bogus")


def test_filter_options_string() -> None:
    config = SLPConfig(media="Shipping", density="HighQuality", fine_print=True)
    assert config.filter_options == (
        "PageSize=Shipping Density=HighQuality FinePrint=True Resolution=300dpi"
    )


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
