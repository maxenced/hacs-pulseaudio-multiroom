"""Constants for the PulseAudio Multiroom integration."""

from datetime import timedelta

DOMAIN = "pulseaudio_multiroom"

DEFAULT_PORT = 4713

CONF_SINK = "sink"
CONF_SOURCE = "source"

SUBENTRY_ROOM = "room"
SUBENTRY_SOURCE = "source"

# Safety net only: state changes are pushed by the event listener
FALLBACK_SCAN_INTERVAL = timedelta(minutes=5)
