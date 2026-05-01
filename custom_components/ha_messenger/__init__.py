"""HA Messenger integration.

Sets up one virtual camera + one motion binary_sensor per config entry, and
registers the ``ha_messenger.send_message`` service.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_DURATION,
    ATTR_MESSAGE,
    ATTR_NOTIFY_TARGETS,
    CONF_BG,
    CONF_DEFAULT_DURATION,
    CONF_FG,
    CONF_FONT_SIZE,
    CONF_HEIGHT,
    CONF_NAME,
    CONF_WIDTH,
    DATA_CAMERA_TO_ENTRY,
    DATA_RUNTIMES,
    DEFAULT_BG,
    DEFAULT_DURATION,
    DEFAULT_FG,
    DEFAULT_FONT_SIZE,
    DEFAULT_HEIGHT,
    DEFAULT_WIDTH,
    DOMAIN,
    MAX_DURATION,
    MIN_DURATION,
    SERVICE_SEND_MESSAGE,
    SIGNAL_MESSAGE_UPDATED,
    SIGNAL_MOTION_TRIGGER,
)
from .rendering import render_message

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.CAMERA, Platform.BINARY_SENSOR]

SEND_MESSAGE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_MESSAGE): cv.string,
        vol.Optional(ATTR_DURATION): vol.All(
            vol.Coerce(int), vol.Range(min=MIN_DURATION, max=MAX_DURATION)
        ),
        vol.Optional(ATTR_NOTIFY_TARGETS): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional("entity_id"): cv.entity_ids,
        vol.Optional("device_id"): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional("area_id"): vol.All(cv.ensure_list, [cv.string]),
    },
    extra=vol.ALLOW_EXTRA,
)


@dataclass
class ChannelConfig:
    """Frozen-ish view of a channel's config, rebuilt on options update."""

    name: str
    width: int
    height: int
    font_size: int
    background_color: str
    text_color: str
    default_duration: int

    @classmethod
    def from_entry(cls, entry: ConfigEntry) -> ChannelConfig:
        data = {**entry.data, **entry.options}
        return cls(
            name=data[CONF_NAME],
            width=int(data.get(CONF_WIDTH, DEFAULT_WIDTH)),
            height=int(data.get(CONF_HEIGHT, DEFAULT_HEIGHT)),
            font_size=int(data.get(CONF_FONT_SIZE, DEFAULT_FONT_SIZE)),
            background_color=data.get(CONF_BG, DEFAULT_BG),
            text_color=data.get(CONF_FG, DEFAULT_FG),
            default_duration=int(data.get(CONF_DEFAULT_DURATION, DEFAULT_DURATION)),
        )


@dataclass
class ChannelRuntime:
    """Per-entry runtime state held in ``hass.data``."""

    entry_id: str
    config: ChannelConfig
    current_message: str = ""
    last_sent_at: datetime | None = None
    camera_entity_id: str | None = None
    _cache: dict[tuple[str, int, int], bytes] = field(default_factory=dict)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.entry_id)},
            name=self.config.name,
            manufacturer="HA Messenger",
            model="Virtual messenger channel",
        )

    def invalidate_render_cache(self) -> None:
        self._cache.clear()

    async def render(self, hass: HomeAssistant, width: int, height: int) -> bytes:
        """Render (or return cached) JPEG bytes for the current message."""
        key = (self.current_message, width, height)
        async with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                return cached
            data = await hass.async_add_executor_job(
                render_message,
                self.current_message,
                width,
                height,
                self.config.font_size,
                self.config.background_color,
                self.config.text_color,
            )
            self._cache[key] = data
            return data


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up HA Messenger from a config entry."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    domain_data.setdefault(DATA_RUNTIMES, {})
    domain_data.setdefault(DATA_CAMERA_TO_ENTRY, {})

    runtime = ChannelRuntime(entry_id=entry.entry_id, config=ChannelConfig.from_entry(entry))
    domain_data[DATA_RUNTIMES][entry.entry_id] = runtime

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    if not hass.services.has_service(DOMAIN, SERVICE_SEND_MESSAGE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SEND_MESSAGE,
            _make_send_message_handler(hass),
            schema=SEND_MESSAGE_SCHEMA,
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry, cleaning up runtime + service registration."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unloaded:
        return False

    domain_data = hass.data[DOMAIN]
    del domain_data[DATA_RUNTIMES][entry.entry_id]

    if not domain_data[DATA_RUNTIMES]:
        hass.services.async_remove(DOMAIN, SERVICE_SEND_MESSAGE)
        hass.data.pop(DOMAIN)

    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """React to options-flow changes by rebuilding the channel config."""
    runtime: ChannelRuntime = hass.data[DOMAIN][DATA_RUNTIMES][entry.entry_id]
    runtime.config = ChannelConfig.from_entry(entry)
    runtime.invalidate_render_cache()
    async_dispatcher_send(hass, SIGNAL_MESSAGE_UPDATED.format(entry_id=entry.entry_id))


@callback
def _resolve_entries(hass: HomeAssistant, call: ServiceCall) -> list[str]:
    """Map the call's target (entity_id/device_id/area_id) to our entry_ids.

    Falls back to fanning out to every channel if no target is specified.
    Raises ``ServiceValidationError`` when any given entity_id is not a
    registered ha_messenger camera — silently ignoring typos would hide real
    misconfiguration.
    """
    camera_to_entry: dict[str, str] = hass.data[DOMAIN][DATA_CAMERA_TO_ENTRY]
    runtimes: dict[str, ChannelRuntime] = hass.data[DOMAIN][DATA_RUNTIMES]

    entity_ids: list[str] = list(call.data.get("entity_id") or [])
    if not entity_ids and not call.data.get("device_id") and not call.data.get("area_id"):
        return list(runtimes.keys())

    if call.data.get("device_id") or call.data.get("area_id"):
        raise ServiceValidationError(
            "Targeting by device or area is not yet supported. "
            "Target a specific ha_messenger camera entity directly."
        )

    unknown = [e for e in entity_ids if e not in camera_to_entry]
    if unknown:
        raise ServiceValidationError(
            f"Unknown ha_messenger camera target(s): {', '.join(unknown)}"
        )
    return list({camera_to_entry[e] for e in entity_ids})


def _make_send_message_handler(hass: HomeAssistant):
    async def _handle(call: ServiceCall) -> None:
        entry_ids = _resolve_entries(hass, call)
        if not entry_ids:
            raise ServiceValidationError(
                "No ha_messenger channels matched the service target."
            )
        await _async_send_message(hass, call, entry_ids)

    return _handle


async def _async_send_message(
    hass: HomeAssistant,
    call: ServiceCall,
    entry_ids: list[str],
) -> None:
    """Fan a send_message call out to each resolved channel."""
    message = call.data[ATTR_MESSAGE]
    notify_targets: list[str] = call.data.get(ATTR_NOTIFY_TARGETS) or []
    runtimes: dict[str, ChannelRuntime] = hass.data[DOMAIN][DATA_RUNTIMES]

    for entry_id in entry_ids:
        runtime = runtimes[entry_id]
        runtime.current_message = message
        runtime.last_sent_at = dt_util.utcnow()
        runtime.invalidate_render_cache()

        async_dispatcher_send(hass, SIGNAL_MESSAGE_UPDATED.format(entry_id=entry_id))

        duration = call.data.get(ATTR_DURATION)
        if duration is None:
            duration = runtime.config.default_duration
        async_dispatcher_send(
            hass,
            SIGNAL_MOTION_TRIGGER.format(entry_id=entry_id),
            duration,
        )

        if not notify_targets:
            continue

        if runtime.camera_entity_id is None:
            # Camera platform setup hasn't completed — motion already fired,
            # but we can't attach an image yet. Surface it loudly.
            _LOGGER.warning(
                "Skipping notify fanout for channel %s: camera entity not registered yet",
                entry_id,
            )
            continue

        for name in notify_targets:
            await hass.services.async_call(
                "notify",
                name,
                {"message": message, "data": {"image": runtime.camera_entity_id}},
                blocking=True,
            )
