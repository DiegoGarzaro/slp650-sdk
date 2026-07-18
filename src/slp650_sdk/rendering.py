"""Render label content to monochrome bitmaps.

Everything is rendered host-side to a 1-bit image; the printer never receives
text, fonts, or barcode commands (see docs/05_RENDERING.md).
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from slp650_sdk.config import media_pixels

FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
)

BOLD_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    "/System/Library/Fonts/HelveticaNeue.ttc",
)


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load the first available TrueType font, falling back to PIL's default.

    Args:
        size (int): Font size in pixels.
        bold (bool): Prefer a bold face (falls back to regular, then to
            PIL's built-in font).

    Returns:
        ImageFont.FreeTypeFont | ImageFont.ImageFont: Loaded font object.
    """
    candidates = (*BOLD_FONT_CANDIDATES, *FONT_CANDIDATES) if bold else FONT_CANDIDATES
    for candidate in candidates:
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
) -> str:
    """Word-wrap text so each line fits within a pixel width.

    Args:
        draw (ImageDraw.ImageDraw): Draw context used to measure text.
        text (str): Input text; existing newlines are preserved.
        font (ImageFont.FreeTypeFont | ImageFont.ImageFont): Font used for
            measuring.
        max_width (int): Maximum line width in pixels.

    Returns:
        str: Text with newlines inserted at wrap points.
    """
    output: list[str] = []
    for paragraph in text.splitlines() or [text]:
        words = paragraph.split()
        if not words:
            output.append("")
            continue
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            box = draw.textbbox((0, 0), candidate, font=font)
            if box[2] - box[0] <= max_width:
                current = candidate
            else:
                output.append(current)
                current = word
        output.append(current)
    return "\n".join(output)


def render_text_image(
    text: str,
    media: str,
    *,
    font_size: int = 42,
    margin: int = 24,
    rotate: int = 0,
) -> Image.Image:
    """Render centered, word-wrapped text to a 1-bit label image.

    Args:
        text (str): Text to render; newlines are preserved.
        media (str): Label media name (see ``config.MEDIA_POINTS``).
        font_size (int): Font size in pixels.
        margin (int): Margin around the text in pixels.
        rotate (int): Rotation in degrees: 0, 90, 180, or 270. Note that 90
            and 270 swap the canvas dimensions.

    Returns:
        Image.Image: 1-bit label image.

    Raises:
        ValueError: If ``media`` or ``rotate`` is invalid.
    """
    if rotate not in (0, 90, 180, 270):
        raise ValueError("rotate must be 0, 90, 180, or 270")

    width, height = media_pixels(media)
    image = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(image)
    font = load_font(font_size)
    wrapped = wrap_text(draw, text, font, max(1, width - margin * 2))
    box = draw.multiline_textbbox((0, 0), wrapped, font=font, spacing=6, align="center")
    text_width = box[2] - box[0]
    text_height = box[3] - box[1]
    x = max(margin, (width - text_width) // 2)
    y = max(margin, (height - text_height) // 2)
    draw.multiline_text((x, y), wrapped, fill=0, font=font, spacing=6, align="center")

    if rotate:
        image = image.rotate(rotate, expand=True, fillcolor=255)
    return ImageOps.autocontrast(image).convert("1", dither=Image.Dither.FLOYDSTEINBERG)


def render_text_label(
    text: str,
    media: str,
    destination: Path,
    *,
    font_size: int = 42,
    margin: int = 24,
    rotate: int = 0,
) -> None:
    """Render centered, word-wrapped text to a 1-bit PNG label file.

    Args:
        text (str): Text to render; newlines are preserved.
        media (str): Label media name (see ``config.MEDIA_POINTS``).
        destination (Path): Output PNG path.
        font_size (int): Font size in pixels.
        margin (int): Margin around the text in pixels.
        rotate (int): Rotation in degrees: 0, 90, 180, or 270.

    Raises:
        ValueError: If ``media`` or ``rotate`` is invalid.
    """
    render_text_image(
        text, media, font_size=font_size, margin=margin, rotate=rotate
    ).save(destination, format="PNG")


def fit_image_to_media(image: Image.Image, media: str) -> Image.Image:
    """Fit an arbitrary image onto a media canvas as a 1-bit label.

    Args:
        image (Image.Image): Source image, any mode or size.
        media (str): Label media name (see ``config.MEDIA_POINTS``).

    Returns:
        Image.Image: 1-bit image exactly the size of the media canvas.

    Raises:
        ValueError: If ``media`` is not a known media name.
    """
    return fit_image_to_canvas(image, media_pixels(media))


def fit_image_to_canvas(image: Image.Image, canvas: tuple[int, int]) -> Image.Image:
    """Fit an arbitrary image into a pixel canvas as a 1-bit bitmap.

    Mirrors what the CUPS raster path used to do for uploads: scale to fit
    (preserving aspect ratio), center on a white canvas, and dither to 1-bit.
    Transparency is flattened against white.

    Args:
        image (Image.Image): Source image, any mode or size.
        canvas (tuple[int, int]): Target size as ``(width, height)``.

    Returns:
        Image.Image: 1-bit image exactly ``canvas`` sized.
    """
    if image.mode in ("RGBA", "LA", "PA") or "transparency" in image.info:
        background = Image.new("RGBA", image.size, (255, 255, 255, 255))
        background.alpha_composite(image.convert("RGBA"))
        image = background
    if image.mode != "L":
        image = image.convert("L")
    image = ImageOps.autocontrast(image)
    if image.size != canvas:
        fitted = ImageOps.contain(image, canvas)
        background_l = Image.new("L", canvas, 255)
        background_l.paste(
            fitted,
            ((canvas[0] - fitted.width) // 2, (canvas[1] - fitted.height) // 2),
        )
        image = background_l
    return image.convert("1", dither=Image.Dither.FLOYDSTEINBERG)
