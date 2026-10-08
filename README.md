# PulseAudio Multiroom

[![Validate](https://github.com/maxenced/hacs-pulseaudio-multiroom/actions/workflows/validate.yml/badge.svg)](https://github.com/maxenced/hacs-pulseaudio-multiroom/actions/workflows/validate.yml)
[![hacs](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/docs/faq/custom_repositories)

Home Assistant integration driving a software multiroom built on a PulseAudio
(or PipeWire, through `pipewire-pulse`) server: one sink per room, sources
routed to rooms with `module-loopback`.

For each **room** (a sink, e.g. a `module-remap-sink` on one channel of a
multichannel sound card) it creates a device with:

- `number.<room>_volume`: sink volume, 0-100 %;
- `switch.<room>_mute`: sink mute;
- `switch.<room>_<source>`: one per configured **source** (e.g. the monitor of
  a `module-null-sink` a player writes to), on when a loopback from the source
  to the room's sink exists. Turning it on loads `module-loopback
  sink=<sink> source=<source>`, turning it off unloads it.

State is pushed: a background connection subscribes to PulseAudio events, so
changes made elsewhere (pavucontrol, `pactl`, `default.pa`) show up at once.
Loopbacks are matched on their `sink=` and `source=` arguments whoever loaded
them, so modules created by the core `pulseaudio_loopback` switches or by
`default.pa` are recognized.

## Requirements

- Home Assistant 2026.9 or later.
- The PulseAudio server reachable over TCP, e.g. in `default.pa`:
  `load-module module-native-protocol-tcp auth-anonymous=1` (restrict it with
  `auth-ip-acl=` if the port is reachable from untrusted networks).
- With PipeWire: add `"tcp:4713"` to `server.address` in
  `pipewire-pulse.conf`. Module loading from network clients may need
  `client.access = "unrestricted"` on that address.

## Installation

### HACS (recommended)

1. HACS → ⋮ → *Custom repositories*, add
   `https://github.com/maxenced/hacs-pulseaudio-multiroom` with type
   *Integration*.
2. Install *PulseAudio Multiroom*, then restart Home Assistant.

### Manual

Copy `custom_components/pulseaudio_multiroom` into the Home Assistant
`config/custom_components` directory, then restart Home Assistant.

## Configuration

1. Settings → Devices & services → Add integration → *PulseAudio Multiroom*,
   enter the server host (`host.docker.internal` when Home Assistant runs in
   Docker on the PulseAudio host) and port (4713).
2. On the integration entry, use **Add source** for each player (name +
   source, e.g. *Spotify Maxence* → `null-spotify.monitor`).
3. Use **Add room** for each room (name + sink, e.g. *Salon* → `output4`).

Rooms and sources can be renamed or pointed to another sink/source later with
their *Reconfigure* menu.

## Migrating from `pulseaudio_loopback`

Both can run side by side (they act on the same modules), but the YAML
`switch: - platform: pulseaudio_loopback` entries become redundant: remove
them once automations and dashboards use the new switches.

## Development

```bash
uv sync
uv run ruff format && uv run ruff check
uv run ty check
uv run pytest
```

## License

Apache 2.0, see [LICENSE](LICENSE).
