# HA Messenger

Send a short text message from the Home Assistant Companion app and have it
appear as a motion-triggered alert on Companion apps and on an Apple TV — no
extra infrastructure required.

The integration creates one *virtual camera* entity whose video feed is a
rendered image of the current message, plus a paired motion `binary_sensor`.
Sending a message updates the image and briefly fires the motion sensor. Your
existing HomeKit bridge is what surfaces the alert on Apple TV.

> **Status — v0.1.** All core functions implemented and tested. See
> [CLAUDE.md](CLAUDE.md) for architecture notes.

## How it works

```
Companion app  ──► service: ha_messenger.send_message(message, duration, notify_targets)
                        │
                        ▼
              camera.messenger frame updates (PIL-rendered text)
              binary_sensor.messenger_motion fires briefly
                        │
           ┌────────────┴───────────────┐
           ▼                            ▼
   HomeKit bridge → Apple TV    notify.mobile_app_* push
   motion notification          (with camera image attached)
```

## Install via HACS

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=e7hz3r0&repository=ha_messenger&category=integration)

Click the badge to open this repo in HACS on your own Home Assistant instance,
then install **HA Messenger** and restart Home Assistant. After restart:
Settings → Devices & Services → **Add Integration** → **HA Messenger**.

Or add it manually:

1. HACS → Integrations → three-dot menu → **Custom repositories**.
2. Add `https://github.com/e7hz3r0/ha_messenger` with category **Integration**.
3. Install **HA Messenger** and restart Home Assistant.
4. Settings → Devices & Services → **Add Integration** → **HA Messenger**.

## Configuration

The config flow asks for:

| Field | Default | Notes |
| --- | --- | --- |
| `name` | — | Display name (e.g. `Messenger`) |
| `width` / `height` | `1280 × 720` | Rendered frame size |
| `font_size` | `96` | Rendered text size in pixels |
| `background_color` | `#000000` | Hex color |
| `text_color` | `#FFFFFF` | Hex color |
| `default_duration` | `10` | Seconds the motion sensor stays on |

All fields except `name` can be changed later via the integration's Options
flow.

## Usage

### Service call

```yaml
service: ha_messenger.send_message
target:
  entity_id: camera.messenger
data:
  message: "Dinner is ready"
  duration: 15
  notify_targets:
    - mobile_app_ethan_iphone
```

- `message` — required text.
- `duration` — seconds the motion sensor stays on (overrides default).
- `notify_targets` — optional list of `notify.*` service names. Each receives a
  push notification with the rendered camera image attached.

### Example Companion-app automation

Create a script bound to a Companion-app action or widget:

```yaml
alias: Send quick message
fields:
  message: { selector: { text: {} } }
sequence:
  - service: ha_messenger.send_message
    target: { entity_id: camera.messenger }
    data:
      message: "{{ message }}"
      notify_targets:
        - mobile_app_other_device
```

## Apple TV setup (HomeKit bridge)

To make motion alerts show on Apple TV, add the **HomeKit Bridge** integration
(separate, built-in HA integration) and include both the camera *and* the
linked motion sensor:

```yaml
# configuration.yaml — HomeKit Bridge entry
homekit:
  - name: HA Messenger Bridge
    mode: bridge
    filter:
      include_entities:
        - camera.messenger
        - binary_sensor.messenger_motion
    entity_config:
      camera.messenger:
        linked_motion_sensor: binary_sensor.messenger_motion
```

Pair the bridge in the Apple Home app, and Apple TV (with a Home hub) will
surface motion notifications with the rendered text when the service fires.

## Companion app — Lovelace card

Add a Picture Entity card pointing at `camera.messenger` to see the rendered
message live:

```yaml
type: picture-entity
entity: camera.messenger
camera_view: live
```

## Development

```bash
# Symlink into a HA dev instance
ln -s $(pwd)/custom_components/ha_messenger \
      ~/.homeassistant/custom_components/ha_messenger
```

Then restart HA and add the integration via the UI.

Contributors: start with [CLAUDE.md](CLAUDE.md) — it documents the architecture,
file responsibilities, and the three currently-open contribution slots.

## License

- Integration code: MIT — see `LICENSE`.
- Bundled font (`custom_components/ha_messenger/fonts/default.ttf`): DejaVu Sans
  2.37.3 under the Bitstream Vera license + additions — see
  `custom_components/ha_messenger/fonts/LICENSE-DejaVu.txt`.
