"""End-to-end tests for setup/unload lifecycle and the send_message service."""
from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ha_messenger.const import (
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
    DOMAIN,
    SERVICE_SEND_MESSAGE,
)


DEFAULT_DATA: dict[str, object] = {
    CONF_NAME: "Messenger",
    CONF_WIDTH: 1280,
    CONF_HEIGHT: 720,
    CONF_FONT_SIZE: 96,
    CONF_BG: "#000000",
    CONF_FG: "#FFFFFF",
    CONF_DEFAULT_DURATION: 10,
}


async def _setup(hass: HomeAssistant, *, name: str = "Messenger") -> MockConfigEntry:
    data = {**DEFAULT_DATA, CONF_NAME: name}
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=data,
        unique_id=f"{DOMAIN}:{name.lower()}",
        title=name,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


# --- Lifecycle ------------------------------------------------------------ #


async def test_setup_entry_creates_entities_and_service(hass: HomeAssistant) -> None:
    entry = await _setup(hass)

    assert hass.states.get("camera.messenger") is not None
    assert hass.states.get("binary_sensor.messenger_motion") is not None
    assert hass.services.has_service(DOMAIN, SERVICE_SEND_MESSAGE)

    runtimes = hass.data[DOMAIN][DATA_RUNTIMES]
    assert entry.entry_id in runtimes
    camera_map = hass.data[DOMAIN][DATA_CAMERA_TO_ENTRY]
    assert "camera.messenger" in camera_map


async def test_unload_entry_cleans_up(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    # Last entry unloaded: service + domain bucket should be gone.
    assert not hass.services.has_service(DOMAIN, SERVICE_SEND_MESSAGE)
    assert DOMAIN not in hass.data


async def test_service_survives_while_other_channels_exist(hass: HomeAssistant) -> None:
    a = await _setup(hass, name="Alpha")
    b = await _setup(hass, name="Bravo")

    assert await hass.config_entries.async_unload(a.entry_id)
    await hass.async_block_till_done()

    # Bravo still present → service must remain registered.
    assert hass.services.has_service(DOMAIN, SERVICE_SEND_MESSAGE)
    assert b.entry_id in hass.data[DOMAIN][DATA_RUNTIMES]


# --- send_message service (TODO contract) -------------------------------- #


async def test_send_message_updates_runtime_current_message(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    await hass.services.async_call(
        DOMAIN,
        SERVICE_SEND_MESSAGE,
        {ATTR_MESSAGE: "Hello world", "entity_id": "camera.messenger"},
        blocking=True,
    )
    runtime = hass.data[DOMAIN][DATA_RUNTIMES][entry.entry_id]
    assert runtime.current_message == "Hello world"


async def test_send_message_fires_motion_sensor(hass: HomeAssistant) -> None:
    await _setup(hass)
    await hass.services.async_call(
        DOMAIN,
        SERVICE_SEND_MESSAGE,
        {ATTR_MESSAGE: "ping", "entity_id": "camera.messenger"},
        blocking=True,
    )
    await hass.async_block_till_done()
    state = hass.states.get("binary_sensor.messenger_motion")
    assert state is not None
    assert state.state == "on"


async def test_send_message_fans_out_when_no_target_specified(hass: HomeAssistant) -> None:
    a = await _setup(hass, name="Alpha")
    b = await _setup(hass, name="Bravo")
    await hass.services.async_call(
        DOMAIN,
        SERVICE_SEND_MESSAGE,
        {ATTR_MESSAGE: "broadcast"},
        blocking=True,
    )
    ra = hass.data[DOMAIN][DATA_RUNTIMES][a.entry_id]
    rb = hass.data[DOMAIN][DATA_RUNTIMES][b.entry_id]
    assert ra.current_message == "broadcast"
    assert rb.current_message == "broadcast"


async def test_send_message_with_unknown_target_raises(hass: HomeAssistant) -> None:
    await _setup(hass)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SEND_MESSAGE,
            {ATTR_MESSAGE: "x", "entity_id": "camera.does_not_exist"},
            blocking=True,
        )


async def test_send_message_calls_notify_targets_legacy(hass: HomeAssistant) -> None:
    """On HA cores without ``notify.send_message`` we fall back to ``notify.<name>``."""
    await _setup(hass)

    # Register a fake legacy notify service we can assert against.
    calls: list[dict[str, object]] = []

    async def _capture(call):
        calls.append(dict(call.data))

    hass.services.async_register("notify", "mobile_app_test", _capture)

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SEND_MESSAGE,
        {
            ATTR_MESSAGE: "Dinner",
            ATTR_NOTIFY_TARGETS: ["mobile_app_test"],
            "entity_id": "camera.messenger",
        },
        blocking=True,
    )
    await hass.async_block_till_done()

    assert len(calls) == 1
    assert calls[0]["message"] == "Dinner"
    # The contract is: do NOT attach the camera entity_id under data.image,
    # so the Companion app renders it as a text push notification.
    assert "data" not in calls[0]


async def test_send_message_calls_notify_targets_modern(hass: HomeAssistant) -> None:
    """On modern HA, ``notify_targets`` routes through ``notify.send_message``.

    Users pass either the bare slug (``mobile_app_test``) or the full notify
    entity id (``notify.mobile_app_test``); both must resolve to the same
    ``notify.send_message`` target.
    """
    from homeassistant.components.notify import SERVICE_SEND_MESSAGE as NOTIFY_SEND_MESSAGE

    await _setup(hass)

    # Override the modern ``notify.send_message`` action with a spy. (We re-register
    # rather than set up a real notify entity so the test doesn't depend on the
    # mobile_app/entity-side machinery.) ``async_call`` merges ``target`` into
    # ``service_data`` before dispatch, so the target entity_id arrives in call.data.
    calls: list[dict[str, object]] = []

    async def _capture(call):
        calls.append(dict(call.data))

    hass.services.async_register("notify", NOTIFY_SEND_MESSAGE, _capture)

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SEND_MESSAGE,
        {
            ATTR_MESSAGE: "Dinner",
            ATTR_NOTIFY_TARGETS: ["mobile_app_test"],
            "entity_id": "camera.messenger",
        },
        blocking=True,
    )
    await hass.async_block_till_done()

    assert len(calls) == 1
    assert calls[0]["message"] == "Dinner"
    assert calls[0]["entity_id"] == ["notify.mobile_app_test"]

    # A full entity id target should pass through unchanged.
    calls.clear()
    await hass.services.async_call(
        DOMAIN,
        SERVICE_SEND_MESSAGE,
        {
            ATTR_MESSAGE: "Dinner",
            ATTR_NOTIFY_TARGETS: ["notify.mobile_app_other"],
            "entity_id": "camera.messenger",
        },
        blocking=True,
    )
    await hass.async_block_till_done()
    assert len(calls) == 1
    assert calls[0]["entity_id"] == ["notify.mobile_app_other"]


async def test_send_message_custom_duration_overrides_default(hass: HomeAssistant) -> None:
    """Passing ``duration`` must propagate to the motion sensor trigger."""
    from datetime import timedelta
    from unittest.mock import patch

    import custom_components.ha_messenger.binary_sensor as bs_mod

    await _setup(hass)

    # Dispatcher stores the bound ``_handle_trigger`` as the callback key, so
    # patching the class method does not replace an already-registered listener.
    # Spy on ``async_call_later`` instead — that receives the motion duration.
    orig_later = bs_mod.async_call_later
    seen: list[int] = []

    def _spy_later(hass_inner, delay, action):
        if isinstance(delay, timedelta):
            seen.append(int(delay.total_seconds()))
        else:
            seen.append(int(delay))
        return orig_later(hass_inner, delay, action)

    with patch.object(bs_mod, "async_call_later", side_effect=_spy_later):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SEND_MESSAGE,
            {
                ATTR_MESSAGE: "x",
                ATTR_DURATION: 42,
                "entity_id": "camera.messenger",
            },
            blocking=True,
        )
        await hass.async_block_till_done()

    assert seen == [42]
