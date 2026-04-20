"""Config flow for HA Messenger."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
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
    DOMAIN,
    MAX_DIMENSION,
    MAX_DURATION,
    MAX_FONT_SIZE,
    MIN_DIMENSION,
    MIN_DURATION,
    MIN_FONT_SIZE,
)
from .rendering import parse_hex_color


def _channel_schema(defaults: dict[str, Any] | None = None, *, include_name: bool) -> vol.Schema:
    defaults = defaults or {}
    schema: dict[Any, Any] = {}
    if include_name:
        schema[vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, "Messenger"))] = str
    schema[vol.Required(CONF_WIDTH, default=defaults.get(CONF_WIDTH, DEFAULT_WIDTH))] = (
        selector.NumberSelector(
            selector.NumberSelectorConfig(min=MIN_DIMENSION, max=MAX_DIMENSION, step=1, mode=selector.NumberSelectorMode.BOX)
        )
    )
    schema[vol.Required(CONF_HEIGHT, default=defaults.get(CONF_HEIGHT, DEFAULT_HEIGHT))] = (
        selector.NumberSelector(
            selector.NumberSelectorConfig(min=MIN_DIMENSION, max=MAX_DIMENSION, step=1, mode=selector.NumberSelectorMode.BOX)
        )
    )
    schema[vol.Required(CONF_FONT_SIZE, default=defaults.get(CONF_FONT_SIZE, DEFAULT_FONT_SIZE))] = (
        selector.NumberSelector(
            selector.NumberSelectorConfig(min=MIN_FONT_SIZE, max=MAX_FONT_SIZE, step=1, mode=selector.NumberSelectorMode.BOX)
        )
    )
    schema[vol.Required(CONF_BG, default=defaults.get(CONF_BG, DEFAULT_BG))] = str
    schema[vol.Required(CONF_FG, default=defaults.get(CONF_FG, DEFAULT_FG))] = str
    schema[vol.Required(CONF_DEFAULT_DURATION, default=defaults.get(CONF_DEFAULT_DURATION, DEFAULT_DURATION))] = (
        selector.NumberSelector(
            selector.NumberSelectorConfig(min=MIN_DURATION, max=MAX_DURATION, step=1, unit_of_measurement="s", mode=selector.NumberSelectorMode.BOX)
        )
    )
    return vol.Schema(schema)


def validate_channel_input(user_input: dict[str, Any]) -> dict[str, str]:
    """Return a dict of ``{field_name: error_key}`` for any invalid values."""
    errors: dict[str, str] = {}

    for key in (CONF_BG, CONF_FG):
        try:
            parse_hex_color(str(user_input[key]))
        except ValueError:
            errors[key] = "invalid_color"

    w = int(user_input[CONF_WIDTH])
    h = int(user_input[CONF_HEIGHT])
    if not MIN_DIMENSION <= w <= MAX_DIMENSION:
        errors[CONF_WIDTH] = "invalid_dimension"
    if not MIN_DIMENSION <= h <= MAX_DIMENSION:
        errors[CONF_HEIGHT] = "invalid_dimension"

    fs = int(user_input[CONF_FONT_SIZE])
    if not MIN_FONT_SIZE <= fs <= MAX_FONT_SIZE:
        errors[CONF_FONT_SIZE] = "invalid_font_size"

    d = int(user_input[CONF_DEFAULT_DURATION])
    if not MIN_DURATION <= d <= MAX_DURATION:
        errors[CONF_DEFAULT_DURATION] = "invalid_duration"

    return errors


class HaMessengerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for HA Messenger."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = validate_channel_input(user_input)
            if not errors:
                name = user_input[CONF_NAME]
                await self.async_set_unique_id(f"{DOMAIN}:{name.lower()}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=name, data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=_channel_schema(user_input, include_name=True),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return HaMessengerOptionsFlow(config_entry)


class HaMessengerOptionsFlow(OptionsFlow):
    """Allow users to tweak rendering params without removing the channel."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = validate_channel_input({**user_input, CONF_NAME: self._entry.data.get(CONF_NAME, "")})
            if not errors:
                return self.async_create_entry(title="", data=user_input)

        current = {**self._entry.data, **self._entry.options}
        return self.async_show_form(
            step_id="init",
            data_schema=_channel_schema(user_input or current, include_name=False),
            errors=errors,
        )
