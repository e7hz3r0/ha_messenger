"""Tests for the config flow and options flow.

Uses the ``hass`` fixture from ``pytest-homeassistant-custom-component`` to
spin up a realistic Home Assistant core.
"""
from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ha_messenger.config_flow import validate_channel_input
from custom_components.ha_messenger.const import (
    CONF_BG,
    CONF_DEFAULT_DURATION,
    CONF_FG,
    CONF_FONT_SIZE,
    CONF_HEIGHT,
    CONF_NAME,
    CONF_WIDTH,
    DOMAIN,
)


def _valid_input(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        CONF_NAME: "Messenger",
        CONF_WIDTH: 1280,
        CONF_HEIGHT: 720,
        CONF_FONT_SIZE: 96,
        CONF_BG: "#000000",
        CONF_FG: "#FFFFFF",
        CONF_DEFAULT_DURATION: 10,
    }
    data.update(overrides)
    return data


# --- validate_channel_input (user contribution slot) --------------------- #


def test_validate_accepts_defaults() -> None:
    """Baseline-correct input must produce zero errors."""
    assert validate_channel_input(_valid_input()) == {}


# Only unambiguously-invalid values are asserted here — the contract docstring
# in config_flow.py explicitly lets the user decide whether to accept shorthand
# (#FFF) or named CSS colors ("red"). Garbage must always reject.
@pytest.mark.parametrize("bad", ["", "not-a-color", "#ZZZZZZ", "rgb(0,0,0)"])
def test_validate_rejects_garbage_background_color(bad: str) -> None:
    errors = validate_channel_input(_valid_input(**{CONF_BG: bad}))
    assert errors.get(CONF_BG) == "invalid_color"


@pytest.mark.parametrize("bad", ["", "not-a-color", "#ZZZZZZ"])
def test_validate_rejects_garbage_text_color(bad: str) -> None:
    errors = validate_channel_input(_valid_input(**{CONF_FG: bad}))
    assert errors.get(CONF_FG) == "invalid_color"


def test_validate_returns_mapping_on_failure() -> None:
    """Per contract: returns ``{field_name: error_key}`` using the keys
    already present in ``translations/en.json``."""
    errors = validate_channel_input(_valid_input(**{CONF_BG: "not-a-color"}))
    assert isinstance(errors, dict)
    for key in errors.values():
        assert key in {
            "invalid_color",
            "invalid_dimension",
            "invalid_font_size",
            "invalid_duration",
        }


# --- async_step_user ------------------------------------------------------ #


async def test_user_step_shows_form(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_user_step_creates_entry_on_valid_input(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _valid_input()
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Messenger"
    assert result["data"][CONF_NAME] == "Messenger"


async def test_user_step_surfaces_validation_errors(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _valid_input(**{CONF_BG: "not-a-color"}),
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"]
    # The error key must match a string declared in translations/en.json.
    assert result["errors"].get(CONF_BG) == "invalid_color"


async def test_user_step_rejects_duplicate_name(hass: HomeAssistant) -> None:
    """Two entries with the same lowercased name must collide."""
    first = MockConfigEntry(domain=DOMAIN, data=_valid_input(), unique_id=f"{DOMAIN}:messenger")
    first.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _valid_input()
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


# --- options flow -------------------------------------------------------- #


async def test_options_flow_updates_channel(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data=_valid_input(), unique_id=f"{DOMAIN}:messenger")
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM

    new_options = {
        CONF_WIDTH: 1920,
        CONF_HEIGHT: 1080,
        CONF_FONT_SIZE: 120,
        CONF_BG: "#111111",
        CONF_FG: "#EEEEEE",
        CONF_DEFAULT_DURATION: 20,
    }
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], new_options
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_WIDTH] == 1920
    assert entry.options[CONF_FONT_SIZE] == 120
