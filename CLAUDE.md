# HA Messenger — Claude Context

A Home Assistant custom integration (HACS-installable) that lets a user send a
short text message from the Companion app and have it appear on Apple TV +
other Companion apps via a dynamically-rendered "virtual camera" whose feed
flips a motion `binary_sensor` when new messages arrive.

## 30-second architecture

```
service: ha_messenger.send_message
  → _async_send_message()
    → runtime.current_message = text
    → SIGNAL_MESSAGE_UPDATED   → camera invalidates cache, re-renders on next poll
    → SIGNAL_MOTION_TRIGGER    → binary_sensor flips on, async_call_later turns it off
    → for t in notify_targets: notify.<t>(image=<camera entity_id>)

HomeKit Bridge (separate, user-configured integration) watches our camera +
linked_motion_sensor → Apple TV shows a motion notification with the rendered
frame.
```

**One `ConfigEntry` == one channel == one camera + one binary_sensor**, held
together by a `ChannelRuntime` dataclass in
`hass.data[DOMAIN][DATA_RUNTIMES][entry_id]`.

## File responsibilities

| File | Responsibility | Imports HA core? |
| --- | --- | --- |
| `rendering.py` | Pure PIL: text → JPEG bytes. Unit-testable in isolation. | **No** — keep it that way |
| `const.py` | `DOMAIN`, config keys, defaults, dispatcher signal format strings, `hass.data` sub-keys | No |
| `camera.py` | `HaMessengerCamera` entity; `async_camera_image` reads from runtime, delegates render | Yes |
| `binary_sensor.py` | `HaMessengerMotion` entity; `async_call_later` auto-off on new triggers | Yes |
| `__init__.py` | `async_setup_entry` / `async_unload_entry`, `ChannelRuntime`, service registration and handler | Yes |
| `config_flow.py` | UI setup + options flow; semantic validation lives in `validate_channel_input` | Yes |
| `services.yaml` + `translations/en.json` | UI metadata for services and config steps | — |
| `fonts/default.ttf` | Bundled DejaVu Sans 2.37.3 — licensed; do not remove the adjacent `LICENSE-DejaVu.txt` | — |
| `manifest.json`, `hacs.json` | Integration + HACS metadata. Keep `version` bumps in sync with git tags. | — |

## Currently-open contribution slots

Each is a single small function whose scaffold exists and whose docstring
already spells out the trade-offs. Keep them small (<15 lines each).

1. **`rendering.py::layout_text`** — word-wrap + vertical centering. Returns a
   `Layout` (lines, line_height, top_y). Use `draw.textlength(word, font=font)`
   for pixel-accurate measurements.
2. **`__init__.py::_async_send_message`** — per-channel fan-out: update
   runtime, dispatch `SIGNAL_MESSAGE_UPDATED` + `SIGNAL_MOTION_TRIGGER`, then
   fan out to `notify.*` targets with the camera as image attachment.
3. **`config_flow.py::validate_channel_input`** — semantic validation of form
   input. Must return `{field_name: error_key}` with keys that already exist
   in `translations/en.json` (`invalid_color`, `invalid_dimension`,
   `invalid_font_size`, `invalid_duration`).

## Conventions (load-bearing)

- **PIL blocks the event loop** — always wrap `render_message` calls in
  `hass.async_add_executor_job(...)`. `ChannelRuntime.render()` already does
  this; do the same in any new render sites.
- **Runtime is source-of-truth for the message**, not an entity attribute.
  The camera exposes `current_message` as a read-only `extra_state_attributes`
  view; the runtime is the writer.
- **Dispatcher signals are per-entry.** Always use
  `SIGNAL_MESSAGE_UPDATED.format(entry_id=entry_id)` /
  `SIGNAL_MOTION_TRIGGER.format(entry_id=entry_id)`. Never hard-code.
- **Entity-id ↔ entry-id resolution** goes through
  `hass.data[DOMAIN][DATA_CAMERA_TO_ENTRY]`. The camera populates this in
  `async_added_to_hass` and removes in `async_will_remove_from_hass`.
- **Service registration is once, globally** — guarded by
  `hass.services.has_service`. It's removed only in the last entry's
  `async_unload_entry`.
- **Options-flow updates must invalidate the render cache.** See
  `_async_options_updated` in `__init__.py`; rebuild the `ChannelConfig` and
  call `runtime.invalidate_render_cache()` so new colors/size take effect on
  the next `async_camera_image` call.
- **Service errors raise `ServiceValidationError`**, not `ValueError`.
- **`integration_type: "hub"`** in `manifest.json` is intentional (matches
  "one config entry spawns multiple entities"). Do not change to `service`.

## Anti-patterns (don't)

- Don't add a `sensor` or `input_text` platform to hold the message. The
  runtime + camera attribute is deliberate and keeps state ownership clean.
- Don't read/write `hass.data[DOMAIN]` outside `async_setup_entry` /
  `async_unload_entry` / the service handler. Entities should hold a
  reference to the runtime they were handed at construction time.
- Don't use `ImageFont.load_default()` — it's a ~10px bitmap font, unusable on
  a TV. Always use the bundled TTF.
- Don't hard-code `camera.messenger` anywhere. Users can set `name` to
  anything; always resolve through the target selector or the reverse map.
- Don't ship breaking manifest changes without bumping `VERSION` in
  `HaMessengerConfigFlow` and implementing `async_migrate_entry`.

## Testing

**Unit tests** live in `tests/` and use
`pytest-homeassistant-custom-component`. The three TODO functions each have
tests that act as concrete contracts; they fail today and turn green as
each implementation lands.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements_test.txt
pytest                              # full suite
pytest tests/test_rendering.py -v   # pure-Python, no HA harness
pytest -k "not send_message"        # skip TODO-dependent tests
```

Expected failures before each TODO is filled:

| TODO function | Failing tests |
| --- | --- |
| `rendering.py::layout_text` | `tests/test_rendering.py::test_render_message_*`, `test_layout_text_*` |
| `config_flow.py::validate_channel_input` | `tests/test_config_flow.py::test_validate_*`, `test_user_step_creates_entry_on_valid_input`, `test_user_step_surfaces_validation_errors` |
| `__init__.py::_async_send_message` | `tests/test_init.py::test_send_message_*` |

Passing even pre-TODO:

- `test_rendering.py::test_parse_hex_color_*`
- `test_models.py::*` (ChannelConfig + ChannelRuntime caching)
- `test_config_flow.py::test_user_step_shows_form`, `test_user_step_rejects_duplicate_name`
- `test_init.py::test_setup_entry_*`, `test_unload_entry_cleans_up`,
  `test_service_survives_while_other_channels_exist`,
  `test_send_message_with_unknown_target_raises`

**Syntax smoke (no deps):**

```bash
python3 -c "
import ast, json, pathlib
for p in ['hacs.json', 'custom_components/ha_messenger/manifest.json',
          'custom_components/ha_messenger/translations/en.json']:
    json.loads(pathlib.Path(p).read_text())
for p in list(pathlib.Path('custom_components/ha_messenger').rglob('*.py')) + \
         list(pathlib.Path('tests').rglob('*.py')):
    ast.parse(p.read_text())
print('ok')
"
```

**End-to-end (requires a HA dev instance):**

1. Symlink `custom_components/ha_messenger` into the dev config dir, restart.
2. Settings → Devices & Services → Add "HA Messenger". Entities
   `camera.<name>` and `binary_sensor.<name>_motion` should appear.
3. Developer Tools → Services → `ha_messenger.send_message`,
   `message: "Hello"`, target `camera.<name>`. Verify: camera preview
   updates; motion sensor flips on then off after `duration` seconds.
4. Add HomeKit Bridge, include both entities, set `linked_motion_sensor`,
   pair Apple TV in the Home app. Re-fire the service → motion alert on TV.

**CI:** `.github/workflows/validate.yml` runs `hassfest` + `hacs/action` on
push/PR. `hassfest` catches most manifest/structure errors; HACS action
catches HACS-specific requirements. (No CI test job yet — add one if the
suite becomes a signal you want on PRs.)

## Branch / commit conventions

- Branches: `e7hz3r0/<short-name>`, <30 chars.
- Don't amend commits or force-push. Make new commits.
- Don't skip hooks (`--no-verify`).
- Only commit when explicitly asked.

## Useful external docs

- Camera entity: https://developers.home-assistant.io/docs/core/entity/camera
- Config flow: https://developers.home-assistant.io/docs/config_entries_config_flow_handler
- HomeKit `linked_motion_sensor`: https://www.home-assistant.io/integrations/homekit/#linked_motion_sensor
- HACS publishing: https://www.hacs.xyz/docs/publish/integration/
