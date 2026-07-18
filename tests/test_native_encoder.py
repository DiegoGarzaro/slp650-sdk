"""Byte-for-byte parity tests for the pure-Python native encoder.

Every ``.slp`` file in ``fixtures/`` and ``fixtures-badge/`` was captured on
real SLP650 hardware through the CUPS + GPL-filter pipeline. The native
encoder (in ``cups_compat`` mode) must reproduce each stream exactly.

Note: the AddressSmall fixtures predate the fine-print fix, so they were
generated with fine mode stuck on (``Speed 0x02``) — hence
``fine_print=True`` for those. The badge fixtures are post-fix
(``Speed 0x00``).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from slp650_sdk.native_encoder import DENSITY_BYTES, encode_image
from slp650_sdk.patterns import generate_pattern
from slp650_sdk.protocol import Command, tokenize

FIXTURES = Path(__file__).parent.parent / "fixtures"
BADGE_FIXTURES = Path(__file__).parent.parent / "fixtures-badge"

ADDRESS_SMALL_PATTERNS = (
    "white",
    "black",
    "pixel",
    "hline",
    "vline",
    "border",
    "checkerboard",
)


@pytest.mark.parametrize("pattern", ADDRESS_SMALL_PATTERNS)
def test_parity_address_small_patterns(pattern: str) -> None:
    # The stored PNGs are the exact inputs used on hardware (the border
    # pattern has changed since; its stored PNG preserves the old shape).
    with Image.open(FIXTURES / f"pattern_{pattern}_984x285.png") as image:
        encoded = encode_image(image, fine_print=True)
    expected = (FIXTURES / f"pattern_{pattern}_984x285.slp").read_bytes()
    assert encoded == expected


@pytest.mark.parametrize(
    ("fixture", "density"),
    [
        ("white_density-low", "LowQuality"),
        ("white_density-high", "HighQuality"),
    ],
)
def test_parity_density_variants(fixture: str, density: str) -> None:
    with Image.open(FIXTURES / "pattern_white_984x285.png") as image:
        encoded = encode_image(image, density=density, fine_print=True)
    expected = (FIXTURES / f"{fixture}.slp").read_bytes()
    assert encoded == expected


def test_parity_badge_white() -> None:
    image = Image.new("1", (750, 567), 255)
    encoded = encode_image(image)
    expected = (BADGE_FIXTURES / "white.slp").read_bytes()
    assert encoded == expected


@pytest.mark.skipif(
    not (BADGE_FIXTURES / "edges.slp").is_file(),
    reason="edges.slp capture not copied from the Pi yet",
)
def test_parity_badge_edges() -> None:
    # The edges capture was made from a regenerated 750x567 pattern on the
    # Pi; the pattern generator is deterministic, so regenerate it here.
    image = generate_pattern("edges", 750, 567)
    encoded = encode_image(image)
    expected = (BADGE_FIXTURES / "edges.slp").read_bytes()
    assert encoded == expected


def test_clean_mode_prints_row_zero() -> None:
    # A single line on image row 0: discarded in cups_compat mode, printed
    # (at the far dot) in clean mode.
    image = Image.new("1", (10, 32), 255)
    for x in range(10):
        image.putpixel((x, 0), 0)
    compat_prints = [
        token
        for token in tokenize(encode_image(image, cups_compat=True))
        if isinstance(token, Command) and token.byte in (0x04, 0x05)
    ]
    clean_prints = [
        token
        for token in tokenize(encode_image(image, cups_compat=False))
        if isinstance(token, Command) and token.byte in (0x04, 0x05)
    ]
    assert compat_prints == []
    assert len(clean_prints) == 10


def test_clean_mode_bottom_row_hits_single_dot() -> None:
    # Bottom row: cups_compat double-strikes dots 0-1; clean mode hits dot 0.
    image = Image.new("1", (1, 32), 255)
    image.putpixel((0, 31), 0)
    compat = encode_image(image, cups_compat=True)
    clean = encode_image(image, cups_compat=False)
    assert bytes((0x04, 0x01, 0xC0)) in compat
    assert bytes((0x04, 0x01, 0x80)) in clean


def test_rejects_images_taller_than_printhead() -> None:
    with pytest.raises(ValueError, match="printhead"):
        encode_image(Image.new("1", (10, 577), 255))


def test_rejects_unknown_density() -> None:
    with pytest.raises(ValueError, match="density"):
        encode_image(Image.new("1", (10, 32), 255), density="Bogus")


def test_cli_native_capture_matches_encoder(tmp_path: Path) -> None:
    from slp650_sdk.cli import main as cli_main

    source = tmp_path / "label.png"
    generate_pattern("border", 200, 96).save(source, format="PNG")
    capture = tmp_path / "label.slp"
    exit_code = cli_main(
        [str(source), "--native", "--dry-run", "--capture", str(capture)]
    )
    assert exit_code == 0
    assert capture.read_bytes() == encode_image(generate_pattern("border", 200, 96))


def test_density_bytes_match_protocol_doc() -> None:
    assert DENSITY_BYTES == {
        "LowQuality": 0xF9,
        "MediumQuality": 0x00,
        "HighQuality": 0x06,
    }
