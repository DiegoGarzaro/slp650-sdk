"""Declarative label templates: template name + field values -> label image.

Built-in templates cover common labels (address, shipping, visitor badge);
applications register their own with ``register_template()`` — see
docs/11_INTEGRATION_GUIDE.md for a walkthrough. A template's renderer
receives validated fields and a canvas size and returns a 1-bit image, which
the caller feeds to ``slp650_sdk.native_encoder.encode_image``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from PIL import Image, ImageDraw

from slp650_sdk.codes import code128_image, qr_image
from slp650_sdk.config import media_pixels
from slp650_sdk.rendering import load_font, wrap_text

#: A renderer takes (fields, (width, height)) and returns a 1-bit image.
TemplateRenderer = Callable[[Mapping[str, str], tuple[int, int]], Image.Image]


@dataclass(frozen=True)
class Template:
    """A registered label template.

    Attributes:
        name (str): Registry key, kebab-case.
        description (str): One-line human-readable summary.
        default_media (str): Media used when the caller does not pick one.
        required_fields (tuple[str, ...]): Fields that must be provided.
        optional_fields (tuple[str, ...]): Fields the renderer understands
            but does not require.
        renderer (TemplateRenderer): Drawing function.
    """

    name: str
    description: str
    default_media: str
    required_fields: tuple[str, ...]
    optional_fields: tuple[str, ...]
    renderer: TemplateRenderer


_REGISTRY: dict[str, Template] = {}


def register_template(template: Template, *, replace: bool = False) -> None:
    """Add a template to the registry.

    Args:
        template (Template): Template to register.
        replace (bool): Allow overwriting an existing name.

    Raises:
        ValueError: If the name is already registered and ``replace`` is
            False.
    """
    if template.name in _REGISTRY and not replace:
        raise ValueError(f"Template {template.name!r} is already registered")
    _REGISTRY[template.name] = template


def unregister_template(name: str) -> None:
    """Remove a template from the registry (no-op if absent).

    Args:
        name (str): Template name.
    """
    _REGISTRY.pop(name, None)


def get_template(name: str) -> Template:
    """Look up a registered template.

    Args:
        name (str): Template name.

    Returns:
        Template: The registered template.

    Raises:
        LookupError: If no template with that name is registered.
    """
    try:
        return _REGISTRY[name]
    except KeyError:
        raise LookupError(
            f"Unknown template {name!r}; available: {sorted(_REGISTRY)}"
        ) from None


def list_templates() -> list[Template]:
    """List registered templates.

    Returns:
        list[Template]: Templates sorted by name.
    """
    return [_REGISTRY[name] for name in sorted(_REGISTRY)]


def render_template(
    name: str, fields: Mapping[str, str], media: str | None = None
) -> Image.Image:
    """Render a template to a 1-bit label image.

    Args:
        name (str): Registered template name.
        fields (Mapping[str, str]): Field values; unknown fields are ignored.
        media (str | None): Media name; defaults to the template's
            ``default_media``.

    Returns:
        Image.Image: 1-bit label image sized for the media canvas.

    Raises:
        LookupError: If the template is unknown.
        ValueError: If required fields are missing/blank or the media name is
            invalid.
    """
    template = get_template(name)
    missing = [
        field
        for field in template.required_fields
        if not str(fields.get(field, "")).strip()
    ]
    if missing:
        raise ValueError(
            f"Template {name!r} is missing required fields: {', '.join(missing)}"
        )
    canvas = media_pixels(media or template.default_media)
    return template.renderer(fields, canvas)


def draw_fitted_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    box: tuple[int, int, int, int],
    *,
    max_font_size: int,
    min_font_size: int = 14,
    bold: bool = False,
    align: str = "left",
    valign: str = "top",
    spacing: int = 6,
) -> None:
    """Draw word-wrapped text auto-sized to fit a box.

    Font size steps down from ``max_font_size`` until the wrapped text fits;
    at ``min_font_size`` the text is drawn regardless (it may clip).

    Args:
        draw (ImageDraw.ImageDraw): Draw context of the label image.
        text (str): Text to draw; newlines are preserved.
        box (tuple[int, int, int, int]): Bounding box ``(x0, y0, x1, y1)``.
        max_font_size (int): Largest font size to try, in pixels.
        min_font_size (int): Smallest font size to fall back to.
        bold (bool): Use a bold face when available.
        align (str): Horizontal alignment: ``left`` or ``center``.
        valign (str): Vertical alignment: ``top`` or ``middle``.
        spacing (int): Line spacing in pixels.
    """
    x0, y0, x1, y1 = box
    box_width = max(1, x1 - x0)
    box_height = max(1, y1 - y0)

    size = max(max_font_size, min_font_size)
    while True:
        font = load_font(size, bold=bold)
        wrapped = wrap_text(draw, text, font, box_width)
        bbox = draw.multiline_textbbox((0, 0), wrapped, font=font, spacing=spacing, align=align)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        if (text_width <= box_width and text_height <= box_height) or size <= min_font_size:
            break
        size = max(size - 4, min_font_size)

    x = x0 if align == "left" else x0 + (box_width - text_width) // 2
    y = y0 if valign == "top" else y0 + (box_height - text_height) // 2
    draw.multiline_text(
        (x - bbox[0], y - bbox[1]), wrapped, fill=0, font=font, spacing=spacing, align=align
    )


def _blank_canvas(canvas: tuple[int, int]) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("L", canvas, 255)
    return image, ImageDraw.Draw(image)


def _finish(image: Image.Image) -> Image.Image:
    # Content is already black/white; skip dithering so codes stay crisp.
    return image.convert("1", dither=Image.Dither.NONE)


def _render_address(fields: Mapping[str, str], canvas: tuple[int, int]) -> Image.Image:
    width, height = canvas
    image, draw = _blank_canvas(canvas)
    margin = max(16, height // 12)
    draw_fitted_text(
        draw,
        str(fields["address"]),
        (margin, margin, width - margin, height - margin),
        max_font_size=height // 4,
        align="left",
        valign="middle",
    )
    return _finish(image)


def _render_visitor_badge(fields: Mapping[str, str], canvas: tuple[int, int]) -> Image.Image:
    width, height = canvas
    image, draw = _blank_canvas(canvas)
    margin = max(24, height // 16)
    text_right = width - margin

    qr_data = str(fields.get("qr_data", "")).strip()
    if qr_data:
        qr_size = min(height - 2 * margin, width // 3)
        qr = qr_image(qr_data, qr_size)
        image.paste(qr.convert("L"), (width - margin - qr_size, (height - qr_size) // 2))
        text_right = width - 2 * margin - qr_size

    name_bottom = margin + int((height - 2 * margin) * 0.55)
    draw_fitted_text(
        draw,
        str(fields["name"]),
        (margin, margin, text_right, name_bottom),
        max_font_size=height // 4,
        bold=True,
        align="left",
        valign="middle",
    )
    company = str(fields.get("company", "")).strip()
    if company:
        draw_fitted_text(
            draw,
            company,
            (margin, name_bottom + margin // 2, text_right, height - margin),
            max_font_size=height // 8,
            align="left",
            valign="top",
        )
    return _finish(image)


def _render_shipping(fields: Mapping[str, str], canvas: tuple[int, int]) -> Image.Image:
    width, height = canvas
    image, draw = _blank_canvas(canvas)
    margin = max(24, height // 16)
    content_bottom = height - margin

    barcode_data = str(fields.get("barcode_data", "")).strip()
    if barcode_data:
        bar_height = height // 4
        bar = code128_image(barcode_data, width=width - 2 * margin, height=bar_height)
        image.paste(bar.convert("L"), (margin, height - margin - bar_height))
        content_bottom = height - 2 * margin - bar_height

    to_top = margin
    sender = str(fields.get("from", "")).strip()
    if sender:
        from_bottom = margin + (content_bottom - margin) // 4
        draw_fitted_text(
            draw,
            sender,
            (margin, margin, width - margin, from_bottom),
            max_font_size=height // 14,
            min_font_size=12,
            align="left",
            valign="top",
        )
        to_top = from_bottom + margin // 2

    draw_fitted_text(
        draw,
        str(fields["to"]),
        (margin, to_top, width - margin, content_bottom),
        max_font_size=height // 5,
        bold=True,
        align="left",
        valign="middle",
    )
    return _finish(image)


register_template(
    Template(
        name="address",
        description="Multi-line address block, vertically centered",
        default_media="AddressSmall",
        required_fields=("address",),
        optional_fields=(),
        renderer=_render_address,
    )
)
register_template(
    Template(
        name="visitor-badge",
        description="Name badge with optional company line and QR code",
        default_media="MediaBadge",
        required_fields=("name",),
        optional_fields=("company", "qr_data"),
        renderer=_render_visitor_badge,
    )
)
register_template(
    Template(
        name="shipping",
        description="Shipping label with optional sender block and Code 128 barcode",
        default_media="Shipping",
        required_fields=("to",),
        optional_fields=("from", "barcode_data"),
        renderer=_render_shipping,
    )
)
