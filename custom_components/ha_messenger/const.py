"""Constants for the HA Messenger integration."""
from __future__ import annotations

from typing import Final

DOMAIN: Final = "ha_messenger"

CONF_NAME: Final = "name"
CONF_WIDTH: Final = "width"
CONF_HEIGHT: Final = "height"
CONF_FONT_SIZE: Final = "font_size"
CONF_BG: Final = "background_color"
CONF_FG: Final = "text_color"
CONF_DEFAULT_DURATION: Final = "default_duration"

DEFAULT_WIDTH: Final = 1280
DEFAULT_HEIGHT: Final = 720
DEFAULT_FONT_SIZE: Final = 96
DEFAULT_BG: Final = "#000000"
DEFAULT_FG: Final = "#FFFFFF"
DEFAULT_DURATION: Final = 10

MIN_DIMENSION: Final = 64
MAX_DIMENSION: Final = 3840
MIN_FONT_SIZE: Final = 8
MAX_FONT_SIZE: Final = 512
MIN_DURATION: Final = 1
MAX_DURATION: Final = 300

SERVICE_SEND_MESSAGE: Final = "send_message"

ATTR_MESSAGE: Final = "message"
ATTR_DURATION: Final = "duration"
ATTR_NOTIFY_TARGETS: Final = "notify_targets"
ATTR_PREVIEW_ONLY: Final = "preview_only"

SIGNAL_MESSAGE_UPDATED: Final = "ha_messenger_message_updated_{entry_id}"
SIGNAL_MOTION_TRIGGER: Final = "ha_messenger_motion_trigger_{entry_id}"

DATA_RUNTIMES: Final = "runtimes"
DATA_CAMERA_TO_ENTRY: Final = "camera_to_entry"

FONT_FILENAME: Final = "default.ttf"
