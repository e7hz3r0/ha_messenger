"""Pure rendering helpers for HA Messenger.

No Home Assistant imports live here — the module is directly unit-testable and
runs entirely in a worker thread via ``hass.async_add_executor_job``.
"""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

DEFAULT_FONT_PATH = Path(__file__).parent / "fonts" / "default.ttf"

# Fraction of the canvas reserved as horizontal padding on each side.
HORIZONTAL_PADDING_FRACTION = 0.06
# Fraction of the font size used as vertical spacing between wrapped lines.
LINE_SPACING_FRACTION = 0.25
JPEG_QUALITY = 85


@dataclass(frozen=True)
class Layout:
    """Result of the layout pass: how to draw wrapped text on the canvas."""

    lines: tuple[str, ...]
    line_height: int
    top_y: int


def _parse_hex_color(value: str) -> tuple[int, int, int]:
    """Parse ``#RRGGBB`` into an ``(r, g, b)`` tuple. Raises ValueError if malformed."""
    v = value.strip().lstrip("#")
    if len(v) != 6:
        raise ValueError(f"expected #RRGGBB, got {value!r}")
    return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)


def _load_font(font_size: int, font_path: Path | str | None) -> ImageFont.FreeTypeFont:
    path = Path(font_path) if font_path else DEFAULT_FONT_PATH
    return ImageFont.truetype(str(path), size=font_size)


def layout_text(
    text: str,
    draw: ImageDraw.ImageDraw,
    font: ImageFont.FreeTypeFont,
    canvas_width: int,
    canvas_height: int,
) -> Layout:
    """Word-wrap ``text`` to fit within the canvas and compute vertical centering."""
    x_pad = int(canvas_width * HORIZONTAL_PADDING_FRACTION)
    max_width = float(canvas_width - 2 * x_pad)
    bbox = font.getbbox("Ag")
    base_h = bbox[3] - bbox[1]
    spacing = int(base_h * LINE_SPACING_FRACTION)
    line_height = base_h + spacing

    lines: list[str] = []

    def append_wrapped_paragraph(para: str) -> None:
        words = para.split()
        if not words:
            return
        current = ""
        for word in words:
            trial = f"{current} {word}".strip() if current else word
            if draw.textlength(trial, font=font) <= max_width + 1e-6:
                current = trial
                continue
            if current:
                lines.append(current)
                current = ""
            if draw.textlength(word, font=font) <= max_width + 1e-6:
                current = word
                continue
            chunk = ""
            for ch in word:
                cand = chunk + ch
                if not chunk or draw.textlength(cand, font=font) <= max_width + 1e-6:
                    chunk = cand
                else:
                    lines.append(chunk)
                    chunk = ch
            current = chunk
        if current:
            lines.append(current)

    for para in (text or "").split("\n"):
        if para.strip() == "":
            lines.append("")
            continue
        append_wrapped_paragraph(para)

    if not lines:
        lines = [""]

    block_h = len(lines) * line_height
    top_y = int((canvas_height - block_h) / 2)

    return Layout(lines=tuple(lines), line_height=line_height, top_y=top_y)


def render_message(
    text: str,
    width: int,
    height: int,
    font_size: int,
    background_color: str,
    text_color: str,
    font_path: Path | str | None = None,
) -> bytes:
    """Render ``text`` to a JPEG byte string sized ``width x height``."""
    bg = _parse_hex_color(background_color)
    fg = _parse_hex_color(text_color)

    img = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(img)
    font = _load_font(font_size, font_path)

    layout = layout_text(text or "", draw, font, width, height)

    x_padding = int(width * HORIZONTAL_PADDING_FRACTION)
    y = layout.top_y
    for line in layout.lines:
        line_width = draw.textlength(line, font=font)
        x = int((width - line_width) / 2) if line_width < width - 2 * x_padding else x_padding
        draw.text((x, y), line, fill=fg, font=font)
        y += layout.line_height

    buf = BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return buf.getvalue()
