"""Config flow for the PulseAudio Multiroom integration."""

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    ConfigEntry,
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import PulseClient, PulseConnectionError, PulseState
from .const import (
    CONF_SINK,
    CONF_SOURCE,
    DEFAULT_PORT,
    DOMAIN,
    SUBENTRY_ROOM,
    SUBENTRY_SOURCE,
)
from .coordinator import PulseMultiroomConfigEntry

_LOGGER = logging.getLogger(__name__)


async def _async_read_server(hass: HomeAssistant, host: str, port: int) -> PulseState:
    """Connect once to the server to validate host and port."""
    client = PulseClient(host, port)
    try:
        return await hass.async_add_executor_job(client.get_state)
    finally:
        await hass.async_add_executor_job(client.close)


class PulseMultiroomConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the PulseAudio server connection."""

    VERSION = 1

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return the subentries supported by this integration."""
        return {SUBENTRY_ROOM: RoomSubentryFlow, SUBENTRY_SOURCE: SourceSubentryFlow}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the PulseAudio server address."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host, port = user_input[CONF_HOST], user_input[CONF_PORT]
            await self.async_set_unique_id(host)
            if self.source == SOURCE_RECONFIGURE:
                self._abort_if_unique_id_mismatch()
            else:
                self._abort_if_unique_id_configured()
            try:
                await _async_read_server(self.hass, host, port)
            except PulseConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error while connecting to PulseAudio")
                errors["base"] = "unknown"
            else:
                if self.source == SOURCE_RECONFIGURE:
                    return self.async_update_reload_and_abort(
                        self._get_reconfigure_entry(), data_updates=user_input
                    )
                return self.async_create_entry(
                    title=f"PulseAudio {host}", data=user_input
                )

        defaults = user_input or (
            dict(self._get_reconfigure_entry().data)
            if self.source == SOURCE_RECONFIGURE
            else {CONF_PORT: DEFAULT_PORT}
        )
        return self.async_show_form(
            step_id="reconfigure" if self.source == SOURCE_RECONFIGURE else "user",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Required(CONF_HOST): str,
                        vol.Required(CONF_PORT): vol.All(
                            vol.Coerce(int), vol.Range(min=1, max=65535)
                        ),
                    }
                ),
                defaults,
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the server port (the host identifies the entry)."""
        return await self.async_step_user(user_input)


class _PulseSubentryFlow(ConfigSubentryFlow):
    """Common flow for a room (sink) or a source subentry."""

    subentry_type: str
    data_key: str

    def _choices(self, state: PulseState) -> list[str]:
        raise NotImplementedError

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Add a subentry."""
        return await self._async_step_edit(user_input)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Edit a subentry."""
        return await self._async_step_edit(user_input)

    async def _async_step_edit(
        self, user_input: dict[str, Any] | None
    ) -> SubentryFlowResult:
        entry: PulseMultiroomConfigEntry = self._get_entry()
        if entry.state is not ConfigEntryState.LOADED:
            return self.async_abort(reason="entry_not_loaded")
        reconfiguring = self.source == SOURCE_RECONFIGURE
        current = self._get_reconfigure_subentry() if reconfiguring else None

        errors: dict[str, str] = {}
        if user_input is not None:
            value = user_input[self.data_key]
            used_by_other = any(
                sub.subentry_type == self.subentry_type
                and sub.data[self.data_key] == value
                and (current is None or sub.subentry_id != current.subentry_id)
                for sub in entry.subentries.values()
            )
            if used_by_other:
                errors[self.data_key] = "already_configured"
            else:
                title = user_input[CONF_NAME]
                data = {self.data_key: value}
                if current is not None:
                    return self.async_update_and_abort(
                        entry, current, data=data, title=title
                    )
                return self.async_create_entry(title=title, data=data)

        if user_input is None and current is not None:
            user_input = {CONF_NAME: current.title, **current.data}
        options = sorted(self._choices(entry.runtime_data.data))
        return self.async_show_form(
            step_id="reconfigure" if reconfiguring else "user",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Required(CONF_NAME): str,
                        vol.Required(self.data_key): SelectSelector(
                            SelectSelectorConfig(
                                options=options,
                                custom_value=True,
                                mode=SelectSelectorMode.DROPDOWN,
                            )
                        ),
                    }
                ),
                user_input or {},
            ),
            errors=errors,
        )


class RoomSubentryFlow(_PulseSubentryFlow):
    """A room is a PulseAudio sink with its own volume."""

    subentry_type = SUBENTRY_ROOM
    data_key = CONF_SINK

    def _choices(self, state: PulseState) -> list[str]:
        return list(state.sinks)


class SourceSubentryFlow(_PulseSubentryFlow):
    """A source can be routed to every room with a loopback."""

    subentry_type = SUBENTRY_SOURCE
    data_key = CONF_SOURCE

    def _choices(self, state: PulseState) -> list[str]:
        return list(state.sources)
