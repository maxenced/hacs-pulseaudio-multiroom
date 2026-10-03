"""Fixtures for the PulseAudio Multiroom tests."""

from collections.abc import Generator
from types import MappingProxyType
from unittest.mock import MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pulseaudio_multiroom.api import PulseState, SinkState
from custom_components.pulseaudio_multiroom.const import (
    CONF_SINK,
    CONF_SOURCE,
    DOMAIN,
    SUBENTRY_ROOM,
    SUBENTRY_SOURCE,
)
from homeassistant.config_entries import ConfigSubentryDataWithId
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant, State


def state_of(hass: HomeAssistant, entity_id: str) -> State:
    """Return the state of an entity that must exist."""
    state = hass.states.get(entity_id)
    assert state is not None, entity_id
    return state


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading the integration from custom_components."""


def make_state() -> PulseState:
    """Return a server with two rooms, two sources, Spotify playing in output1."""
    return PulseState(
        sinks={
            "output1": SinkState(volume=99, muted=False),
            "output2": SinkState(volume=46, muted=True),
        },
        sources={"null-spotify.monitor", "null-radio.monitor"},
        loopbacks={("output1", "null-spotify.monitor"): [42]},
    )


@pytest.fixture
def mock_client() -> Generator[MagicMock]:
    """Mock the blocking PulseAudio client and the event listener."""
    with (
        patch(
            "custom_components.pulseaudio_multiroom.coordinator.PulseClient",
            autospec=True,
        ) as client_cls,
        patch(
            "custom_components.pulseaudio_multiroom.config_flow.PulseClient",
            new=client_cls,
        ),
        patch(
            "custom_components.pulseaudio_multiroom.coordinator.PulseEventListener",
            autospec=True,
        ),
    ):
        client = client_cls.return_value
        client.server = "tcp:pulse.local:4713"
        client.get_state.return_value = make_state()
        yield client


def _subentry(subentry_type: str, title: str, data: dict) -> ConfigSubentryDataWithId:
    return ConfigSubentryDataWithId(
        data=MappingProxyType(data),
        subentry_id=f"{subentry_type}_{title.lower()}",
        subentry_type=subentry_type,
        title=title,
        unique_id=None,
    )


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """Return an entry with rooms Salon/Bureau and sources Spotify/Radio."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="PulseAudio pulse.local",
        unique_id="pulse.local",
        data={CONF_HOST: "pulse.local", CONF_PORT: 4713},
        subentries_data=[
            _subentry(SUBENTRY_ROOM, "Salon", {CONF_SINK: "output1"}),
            _subentry(SUBENTRY_ROOM, "Bureau", {CONF_SINK: "output2"}),
            _subentry(
                SUBENTRY_SOURCE, "Spotify", {CONF_SOURCE: "null-spotify.monitor"}
            ),
            _subentry(SUBENTRY_SOURCE, "Radio", {CONF_SOURCE: "null-radio.monitor"}),
        ],
    )


@pytest.fixture
async def setup_integration(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: MagicMock
) -> MockConfigEntry:
    """Set up the integration with the mocked client."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry
