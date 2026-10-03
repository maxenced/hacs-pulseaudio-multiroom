"""The PulseAudio Multiroom integration."""

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import PulseMultiroomConfigEntry, PulseMultiroomCoordinator

PLATFORMS: list[Platform] = [Platform.NUMBER, Platform.SWITCH]


async def async_setup_entry(
    hass: HomeAssistant, entry: PulseMultiroomConfigEntry
) -> bool:
    """Set up PulseAudio Multiroom from a config entry."""
    coordinator = PulseMultiroomCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    # Rooms and sources are subentries: reload to add/remove their entities
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    coordinator.start_listener()
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: PulseMultiroomConfigEntry
) -> bool:
    """Unload a config entry."""
    # The coordinator shutdown (listener thread, connection) runs on unload
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(
    hass: HomeAssistant, entry: PulseMultiroomConfigEntry
) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
