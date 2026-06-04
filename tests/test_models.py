"""Tests for the in-memory models: ``ChannelConfig`` and ``ChannelRuntime``.

``ChannelRuntime.render`` uses ``hass.async_add_executor_job`` to offload
Pillow work; these tests verify the caching behavior around that call.
Because the render path eventually calls ``layout_text`` (user TODO), tests
that trigger a real render will fail until that slot is filled — those are
marked clearly below.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from custom_components.ha_messenger import ChannelConfig, ChannelRuntime
from custom_components.ha_messenger.const import (
    CONF_BG,
    CONF_DEFAULT_DURATION,
    CONF_FG,
    CONF_FONT_SIZE,
    CONF_HEIGHT,
    CONF_NAME,
    CONF_WIDTH,
    DEFAULT_BG,
    DEFAULT_DURATION,
    DEFAULT_FG,
    DEFAULT_FONT_SIZE,
    DEFAULT_HEIGHT,
    DEFAULT_WIDTH,
)


def _fake_entry(data: dict, options: dict | None = None):
    """Minimal stand-in for ``ConfigEntry`` — only the attributes we read."""
    return SimpleNamespace(data=data, options=options or {})


# --- ChannelConfig -------------------------------------------------------- #


def test_channel_config_from_entry_uses_defaults_when_only_name_supplied() -> None:
    entry = _fake_entry({CONF_NAME: "Messenger"})
    config = ChannelConfig.from_entry(entry)
    assert config.name == "Messenger"
    assert config.width == DEFAULT_WIDTH
    assert config.height == DEFAULT_HEIGHT
    assert config.font_size == DEFAULT_FONT_SIZE
    assert config.background_color == DEFAULT_BG
    assert config.text_color == DEFAULT_FG
    assert config.default_duration == DEFAULT_DURATION


def test_channel_config_from_entry_reads_all_fields() -> None:
    entry = _fake_entry(
        {
            CONF_NAME: "Living Room",
            CONF_WIDTH: 1920,
            CONF_HEIGHT: 1080,
            CONF_FONT_SIZE: 120,
            CONF_BG: "#112233",
            CONF_FG: "#CCDDEE",
            CONF_DEFAULT_DURATION: 25,
        }
    )
    config = ChannelConfig.from_entry(entry)
    assert config.name == "Living Room"
    assert config.width == 1920
    assert config.height == 1080
    assert config.font_size == 120
    assert config.background_color == "#112233"
    assert config.text_color == "#CCDDEE"
    assert config.default_duration == 25


def test_channel_config_options_override_data() -> None:
    entry = _fake_entry(
        {CONF_NAME: "Messenger", CONF_WIDTH: 800},
        {CONF_WIDTH: 1600, CONF_FONT_SIZE: 72},
    )
    config = ChannelConfig.from_entry(entry)
    assert config.width == 1600  # options win
    assert config.font_size == 72
    assert config.name == "Messenger"  # data carries over


# --- ChannelRuntime ------------------------------------------------------- #


class _FakeHass:
    """Sufficient stand-in for the one method ChannelRuntime.render uses."""

    def __init__(self) -> None:
        self.executor_calls = 0

    async def async_add_executor_job(self, func, *args):
        self.executor_calls += 1
        return func(*args)


@pytest.fixture()
def runtime() -> ChannelRuntime:
    config = ChannelConfig(
        name="Test",
        width=320,
        height=180,
        font_size=32,
        background_color="#000000",
        text_color="#FFFFFF",
        default_duration=10,
    )
    return ChannelRuntime(entry_id="abc", config=config, current_message="Hello")


async def test_runtime_render_caches_bytes_across_calls(runtime: ChannelRuntime) -> None:
    """The second render of the same (message, w, h) must hit the cache."""
    hass = _FakeHass()
    first = await runtime.render(hass, 320, 180)
    second = await runtime.render(hass, 320, 180)
    assert first is second  # same cached object
    assert hass.executor_calls == 1  # second call skipped the executor


async def test_runtime_render_different_sizes_are_cached_separately(
    runtime: ChannelRuntime,
) -> None:
    hass = _FakeHass()
    a = await runtime.render(hass, 320, 180)
    b = await runtime.render(hass, 640, 360)
    assert a != b
    assert hass.executor_calls == 2


async def test_runtime_invalidate_clears_cache(runtime: ChannelRuntime) -> None:
    hass = _FakeHass()
    await runtime.render(hass, 320, 180)
    runtime.invalidate_render_cache()
    await runtime.render(hass, 320, 180)
    assert hass.executor_calls == 2


async def test_runtime_render_changes_when_message_changes(runtime: ChannelRuntime) -> None:
    hass = _FakeHass()
    await runtime.render(hass, 320, 180)
    runtime.current_message = "Different"
    runtime.invalidate_render_cache()
    second = await runtime.render(hass, 320, 180)
    assert second is not None
    assert hass.executor_calls == 2


def test_runtime_device_info_has_stable_identifiers(runtime: ChannelRuntime) -> None:
    info = runtime.device_info
    assert info["identifiers"] == {("ha_messenger", "abc")}
    assert info["name"] == "Test"
