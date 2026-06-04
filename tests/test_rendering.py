"""Tests for ``custom_components.ha_messenger.rendering``.

These tests are pure-Python + Pillow — no Home Assistant required. Tests for
functions that still raise ``NotImplementedError`` (``layout_text`` and
anything that transitively calls it) are the concrete spec for the
user-contribution slot in ``rendering.py``; they start failing and turn green
as the implementation lands.
"""
from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from custom_components.ha_messenger.rendering import (
    HORIZONTAL_PADDING_FRACTION,
    Layout,
    parse_hex_color,
    layout_text,
    render_message,
)

# --- parse_hex_color ----------------------------------------------------- #


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("#000000", (0, 0, 0)),
        ("#FFFFFF", (255, 255, 255)),
        ("ffffff", (255, 255, 255)),
        ("#1976d2", (25, 118, 210)),
        ("  #1976D2  ", (25, 118, 210)),
    ],
)
def test_parse_hex_color_accepts_valid(value: str, expected: tuple[int, int, int]) -> None:
    assert parse_hex_color(value) == expected


@pytest.mark.parametrize("value", ["#FFF", "red", "#GGGGGG", "", "#1234567"])
def test_parse_hex_color_rejects_invalid(value: str) -> None:
    with pytest.raises(ValueError):
        parse_hex_color(value)


# --- render_message ------------------------------------------------------- #


def _decode(data: bytes) -> Image.Image:
    return Image.open(BytesIO(data))


def _default_kwargs(**overrides: object) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "text": "Hello",
        "width": 640,
        "height": 360,
        "font_size": 64,
        "background_color": "#000000",
        "text_color": "#FFFFFF",
    }
    kwargs.update(overrides)
    return kwargs


def test_render_message_returns_jpeg_bytes() -> None:
    data = render_message(**_default_kwargs())
    # JPEG magic bytes (SOI marker).
    assert data[:3] == b"\xff\xd8\xff"
    assert len(data) > 100  # not an empty/corrupt frame


def test_render_message_matches_requested_size() -> None:
    data = render_message(**_default_kwargs(width=800, height=450))
    img = _decode(data)
    assert img.size == (800, 450)


def test_render_message_different_messages_differ() -> None:
    a = render_message(**_default_kwargs(text="Alpha"))
    b = render_message(**_default_kwargs(text="Bravo"))
    assert a != b


def test_render_message_empty_string_is_valid() -> None:
    data = render_message(**_default_kwargs(text=""))
    img = _decode(data)
    assert img.size == (640, 360)


def test_render_message_background_color_dominates_with_empty_text() -> None:
    data = render_message(**_default_kwargs(text="", background_color="#FF0000"))
    img = _decode(data).convert("RGB")
    # Sample the top-left corner — it should be the background color.
    r, g, b = img.getpixel((2, 2))
    # Allow small JPEG quantization tolerance.
    assert r > 230 and g < 25 and b < 25


# --- layout_text ---------------------------------------------------------- #
# The contract in ``rendering.py::layout_text`` describes what the function
# must return. These tests assert that contract without hard-coding layout
# math — they're implementation-agnostic.


@pytest.fixture()
def draw_and_font():
    from PIL import ImageDraw, ImageFont

    from custom_components.ha_messenger.rendering import DEFAULT_FONT_PATH

    img = Image.new("RGB", (1280, 720))
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(str(DEFAULT_FONT_PATH), size=72)
    return draw, font


def test_layout_text_returns_layout_instance(draw_and_font) -> None:
    draw, font = draw_and_font
    result = layout_text("Hello", draw, font, 1280, 720)
    assert isinstance(result, Layout)


def test_layout_text_short_text_fits_one_line(draw_and_font) -> None:
    draw, font = draw_and_font
    result = layout_text("Hi", draw, font, 1280, 720)
    assert len(result.lines) == 1
    assert result.lines[0].strip() == "Hi"


def test_layout_text_wraps_overlong_text_to_multiple_lines(draw_and_font) -> None:
    draw, font = draw_and_font
    # Constructed to exceed the available width at font_size=72 on a 1280px
    # canvas (with padding).
    text = "The quick brown fox jumps over the lazy dog several times over"
    result = layout_text(text, draw, font, 1280, 720)
    assert len(result.lines) >= 2


def test_layout_text_lines_respect_available_width(draw_and_font) -> None:
    draw, font = draw_and_font
    text = "The quick brown fox jumps over the lazy dog several times over"
    canvas_w = 1280
    result = layout_text(text, draw, font, canvas_w, 720)
    available = canvas_w * (1 - 2 * HORIZONTAL_PADDING_FRACTION)
    for line in result.lines:
        # Allow a small tolerance for single-word lines longer than the
        # available width (the contract lets the implementer choose whether
        # to mid-word-break, so we tolerate either path).
        if " " in line:
            assert draw.textlength(line, font=font) <= available + 1


def test_layout_text_block_is_vertically_centered(draw_and_font) -> None:
    draw, font = draw_and_font
    canvas_h = 720
    result = layout_text("Centered text", draw, font, 1280, canvas_h)
    block_height = len(result.lines) * result.line_height
    block_center = result.top_y + block_height / 2
    # Within half a line-height of the canvas center is "centered enough".
    assert abs(block_center - canvas_h / 2) <= result.line_height
