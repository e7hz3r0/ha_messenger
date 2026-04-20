"""Virtual camera entity that renders the current message as a JPEG/MJPEG feed."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DATA_CAMERA_TO_ENTRY,
    DATA_RUNTIMES,
    DOMAIN,
    SIGNAL_MESSAGE_UPDATED,
)

if TYPE_CHECKING:
    from . import ChannelRuntime

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the virtual camera entity for this config entry."""
    runtime: ChannelRuntime = hass.data[DOMAIN][DATA_RUNTIMES][entry.entry_id]
    entity = HaMessengerCamera(entry, runtime)
    async_add_entities([entity])


class HaMessengerCamera(Camera):
    """Renders the channel's current message on demand."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_supported_features = CameraEntityFeature(0)
    _attr_brand = "HA Messenger"
    _attr_model = "Virtual camera"

    def __init__(self, entry: ConfigEntry, runtime: ChannelRuntime) -> None:
        super().__init__()
        self._entry = entry
        self._runtime = runtime
        self._attr_unique_id = f"{entry.entry_id}_camera"
        self._attr_device_info = runtime.device_info
        # Frame interval controls how often HA re-polls async_camera_image when
        # serving an MJPEG stream. 0.5s is the default; we keep it high-ish
        # because the image only changes on send_message.
        self.content_type = "image/jpeg"

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        return {
            "current_message": self._runtime.current_message,
            "last_sent_at": (
                self._runtime.last_sent_at.isoformat()
                if self._runtime.last_sent_at
                else None
            ),
        }

    async def async_added_to_hass(self) -> None:
        """Register entity_id ↔ entry_id lookup and subscribe to updates."""
        self.hass.data[DOMAIN][DATA_CAMERA_TO_ENTRY][self.entity_id] = self._entry.entry_id

        signal = SIGNAL_MESSAGE_UPDATED.format(entry_id=self._entry.entry_id)
        self.async_on_remove(
            async_dispatcher_connect(self.hass, signal, self._handle_message_updated)
        )

    async def async_will_remove_from_hass(self) -> None:
        self.hass.data[DOMAIN][DATA_CAMERA_TO_ENTRY].pop(self.entity_id, None)

    @callback
    def _handle_message_updated(self) -> None:
        """Invalidate the rendered-bytes cache and refresh entity state."""
        self._runtime.invalidate_render_cache()
        self.async_write_ha_state()

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return a JPEG-encoded frame, rendered on demand and cached."""
        target_w = width or self._runtime.config.width
        target_h = height or self._runtime.config.height
        try:
            return await self._runtime.render(self.hass, target_w, target_h)
        except Exception:  # noqa: BLE001 — surface render bugs in the log
            _LOGGER.exception("Failed to render message for %s", self.entity_id)
            return None
