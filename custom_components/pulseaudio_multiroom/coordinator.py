"""Coordinator keeping a snapshot of the PulseAudio server state."""

from collections.abc import Callable
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import PulseClient, PulseConnectionError, PulseEventListener, PulseState
from .const import DOMAIN, FALLBACK_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

type PulseMultiroomConfigEntry = ConfigEntry[PulseMultiroomCoordinator]


class PulseMultiroomCoordinator(DataUpdateCoordinator[PulseState]):
    """Fetch the server state, refreshed on PulseAudio events."""

    config_entry: PulseMultiroomConfigEntry

    def __init__(self, hass: HomeAssistant, entry: PulseMultiroomConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=FALLBACK_SCAN_INTERVAL,
            request_refresh_debouncer=Debouncer(
                hass, _LOGGER, cooldown=0.3, immediate=False
            ),
        )
        self.client = PulseClient(entry.data[CONF_HOST], entry.data[CONF_PORT])
        self._listener = PulseEventListener(self.client.server, self._on_pulse_event)

    def _on_pulse_event(self) -> None:
        """Schedule a refresh (called from the listener thread)."""
        self.hass.loop.call_soon_threadsafe(self._async_schedule_refresh)

    @callback
    def _async_schedule_refresh(self) -> None:
        self.config_entry.async_create_background_task(
            self.hass, self.async_request_refresh(), "pulseaudio_multiroom_refresh"
        )

    async def _async_update_data(self) -> PulseState:
        try:
            return await self.hass.async_add_executor_job(self.client.get_state)
        except PulseConnectionError as err:
            raise UpdateFailed(f"Error communicating with PulseAudio: {err}") from err

    async def async_run[*Ts](self, command: Callable[[*Ts], None], *args: *Ts) -> None:
        """Run a blocking client command, then refresh the state."""
        try:
            await self.hass.async_add_executor_job(command, *args)
        except PulseConnectionError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        await self.async_request_refresh()

    def start_listener(self) -> None:
        """Start the event listener thread."""
        self._listener.start()

    async def async_shutdown(self) -> None:
        """Stop the listener and close the connection (called on entry unload)."""
        await super().async_shutdown()
        self._listener.stop()
        if self._listener.is_alive():
            await self.hass.async_add_executor_job(self._listener.join)
        await self.hass.async_add_executor_job(self.client.close)
