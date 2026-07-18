"""Tests for slp650_sdk.templates and slp650_sdk.codes."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from PIL import Image

from slp650_sdk.codes import code128_image, qr_image
from slp650_sdk.config import media_pixels
from slp650_sdk.templates import (
    Template,
    get_template,
    list_templates,
    register_template,
    render_template,
    unregister_template,
)


def test_builtin_templates_are_registered() -> None:
    names = [template.name for template in list_templates()]
    assert names == ["address", "shipping", "visitor-badge"]


def test_get_unknown_template_raises_lookup_error() -> None:
    with pytest.raises(LookupError, match="Unknown template"):
        get_template("bogus")


@pytest.mark.parametrize(
    ("name", "fields"),
    [
        ("address", {"address": "Diego Garzaro\nRua Exemplo 123\nCuritiba PR"}),
        ("visitor-badge", {"name": "Diego Garzaro"}),
        (
            "visitor-badge",
            {"name": "Diego", "company": "ACME Corp", "qr_data": "https://example.com/v/42"},
        ),
        ("shipping", {"to": "Diego Garzaro\nRua Exemplo 123"}),
        (
            "shipping",
            {"to": "Diego", "from": "ACME Warehouse", "barcode_data": "PKG-0042"},
        ),
    ],
)
def test_templates_render_canvas_sized_bitmaps(name: str, fields: dict[str, str]) -> None:
    template = get_template(name)
    image = render_template(name, fields)
    assert image.mode == "1"
    assert image.size == media_pixels(template.default_media)
    # Something was actually drawn.
    assert image.getextrema() == (0, 255)


def test_render_template_missing_required_field() -> None:
    with pytest.raises(ValueError, match="missing required fields: name"):
        render_template("visitor-badge", {"company": "ACME"})


def test_render_template_blank_required_field() -> None:
    with pytest.raises(ValueError, match="missing required fields"):
        render_template("address", {"address": "   "})


def test_render_template_media_override() -> None:
    image = render_template("address", {"address": "Hi"}, media="AddressLarge")
    assert image.size == media_pixels("AddressLarge")


def test_render_template_rejects_unknown_media() -> None:
    with pytest.raises(ValueError, match="Unsupported media"):
        render_template("address", {"address": "Hi"}, media="Bogus")


@pytest.fixture
def custom_template() -> Iterator[Template]:
    def renderer(fields: dict[str, str], canvas: tuple[int, int]) -> Image.Image:
        image = Image.new("1", canvas, 255)
        image.putpixel((0, 0), 0)
        return image

    template = Template(
        name="test-custom",
        description="test",
        default_media="Return",
        required_fields=("value",),
        optional_fields=(),
        renderer=renderer,
    )
    register_template(template)
    yield template
    unregister_template("test-custom")


def test_custom_template_registration(custom_template: Template) -> None:
    image = render_template("test-custom", {"value": "x"})
    assert image.size == media_pixels("Return")
    assert image.getpixel((0, 0)) == 0


def test_register_duplicate_requires_replace(custom_template: Template) -> None:
    with pytest.raises(ValueError, match="already registered"):
        register_template(custom_template)
    register_template(custom_template, replace=True)  # no error


def test_qr_image_size_and_content() -> None:
    image = qr_image("https://example.com", 200)
    assert image.mode == "1"
    assert image.size == (200, 200)
    assert image.getextrema() == (0, 255)


def test_code128_image_size_and_content() -> None:
    image = code128_image("PKG-0042", width=600, height=120)
    assert image.mode == "1"
    assert image.size == (600, 120)
    assert image.getextrema() == (0, 255)
