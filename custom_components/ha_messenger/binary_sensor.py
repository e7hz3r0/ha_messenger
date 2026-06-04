"""Motion binary_sensor that fires briefly when a message is sent."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later

from .const import DATA_RUNTIMES, DOMAIN, SIGNAL_MOTION_TRIGGER

if TYPE_CHECKING:
    from . import ChannelRuntime

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime: ChannelRuntime = hass.data[DOMAIN][DATA_RUNTIMES][entry.entry_id]
    async_add_entities([HaMessengerMotion(entry, runtime)])


class HaMessengerMotion(BinarySensorEntity):
    """Binary sensor that turns on for ``duration`` seconds per send_message call."""

    _attr_has_entity_name = True
    _attr_translation_key = "motion"
    _attr_name = "Motion"
    _attr_device_class = BinarySensorDeviceClass.MOTION
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry, runtime: ChannelRuntime) -> None:
        self._entry = entry
        self._runtime = runtime
        self._attr_unique_id = f"{entry.entry_id}_motion"
        self._attr_device_info = runtime.device_info
        self._attr_is_on = False
        self._cancel_off: CALLBACK_TYPE | None = None

    async def async_added_to_hass(self) -> None:
        signal = SIGNAL_MOTION_TRIGGER.format(entry_id=self._entry.entry_id)
        self.async_on_remove(
            async_dispatcher_connect(self.hass, signal, self._handle_trigger)
        )

    async def async_will_remove_from_hass(self) -> None:
        if self._cancel_off is not None:
            self._cancel_off()
            self._cancel_off = None

    @callback
    def _handle_trigger(self, duration: int) -> None:
        """Turn motion on immediately; schedule off after ``duration`` seconds.

        Cancels any prior pending-off so back-to-back messages extend the
        window rather than clip it.
        """
        if self._cancel_off is not None:
            self._cancel_off()
            self._cancel_off = None

        self._attr_is_on = True
        self.async_write_ha_state()

        self._cancel_off = async_call_later(self.hass, duration, self._turn_off)

    @callback
    def _turn_off(self, _now) -> None:
        self._cancel_off = None
        self._attr_is_on = False
        self.async_write_ha_state()
