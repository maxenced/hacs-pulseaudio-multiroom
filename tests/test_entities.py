"""Tests for the volume, mute and loopback entities."""

from unittest.mock import MagicMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pulseaudio_multiroom.api import PulseConnectionError
from homeassistant.components.number import (
    ATTR_VALUE,
    DOMAIN as NUMBER_DOMAIN,
    SERVICE_SET_VALUE,
)
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .conftest import make_state, state_of


async def test_entities_created(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """Each room gets a volume, a mute and one switch per source."""
    assert state_of(hass, "number.salon_volume").state == "99"
    assert state_of(hass, "number.bureau_volume").state == "46"
    assert state_of(hass, "switch.salon_mute").state == STATE_OFF
    assert state_of(hass, "switch.bureau_mute").state == STATE_ON
    assert state_of(hass, "switch.salon_spotify").state == STATE_ON
    assert state_of(hass, "switch.salon_radio").state == STATE_OFF
    assert state_of(hass, "switch.bureau_spotify").state == STATE_OFF

    devices = dr.async_entries_for_config_entry(
        dr.async_get(hass), setup_integration.entry_id
    )
    assert {(d.name, d.model_id) for d in devices} == {
        ("Salon", "output1"),
        ("Bureau", "output2"),
    }


@pytest.mark.usefixtures("setup_integration")
async def test_set_volume(hass: HomeAssistant, mock_client: MagicMock) -> None:
    """Setting the volume calls the client with an integer percentage."""
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: "number.bureau_volume", ATTR_VALUE: 70.4},
        blocking=True,
    )
    mock_client.set_volume.assert_called_once_with("output2", 70)


@pytest.mark.usefixtures("setup_integration")
async def test_mute(hass: HomeAssistant, mock_client: MagicMock) -> None:
    """The mute switch mutes and unmutes the sink."""
    for service, muted in ((SERVICE_TURN_ON, True), (SERVICE_TURN_OFF, False)):
        await hass.services.async_call(
            SWITCH_DOMAIN,
            service,
            {ATTR_ENTITY_ID: "switch.salon_mute"},
            blocking=True,
        )
        mock_client.set_mute.assert_called_with("output1", muted)


@pytest.mark.usefixtures("setup_integration")
async def test_loopback(hass: HomeAssistant, mock_client: MagicMock) -> None:
    """Source switches load and unload loopback modules."""
    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: "switch.salon_radio"},
        blocking=True,
    )
    mock_client.load_loopback.assert_called_once_with("output1", "null-radio.monitor")

    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: "switch.salon_spotify"},
        blocking=True,
    )
    mock_client.unload_modules.assert_called_once_with([42])

    # Already in the requested state: nothing is sent to the server
    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: "switch.bureau_radio"},
        blocking=True,
    )
    assert mock_client.unload_modules.call_count == 1


@pytest.mark.usefixtures("setup_integration")
async def test_command_error(hass: HomeAssistant, mock_client: MagicMock) -> None:
    """A server error surfaces as a HomeAssistantError."""
    mock_client.set_volume.side_effect = PulseConnectionError("boom")
    with pytest.raises(HomeAssistantError, match="boom"):
        await hass.services.async_call(
            NUMBER_DOMAIN,
            SERVICE_SET_VALUE,
            {ATTR_ENTITY_ID: "number.salon_volume", ATTR_VALUE: 10},
            blocking=True,
        )


async def test_missing_sink_and_source(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """A room whose sink is gone and a source that is gone are unavailable."""
    state = make_state()
    del state.sinks["output2"]
    state.sources.discard("null-radio.monitor")
    mock_client.get_state.return_value = state
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert state_of(hass, "number.bureau_volume").state == STATE_UNAVAILABLE
    assert state_of(hass, "switch.salon_radio").state == STATE_UNAVAILABLE
    assert state_of(hass, "switch.salon_spotify").state == STATE_ON


async def test_setup_retry(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """The entry is retried while the server is unreachable."""
    mock_client.get_state.side_effect = PulseConnectionError("down")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_removed_source_cleans_switches(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """Removing a source subentry removes its switch in every room."""
    entry = setup_integration
    hass.config_entries.async_remove_subentry(entry, "source_radio")
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    assert registry.async_get("switch.salon_radio") is None
    assert registry.async_get("switch.bureau_radio") is None
    assert registry.async_get("switch.salon_spotify") is not None


async def test_unload(hass: HomeAssistant, setup_integration: MockConfigEntry) -> None:
    """The entry unloads cleanly."""
    assert await hass.config_entries.async_unload(setup_integration.entry_id)
    assert setup_integration.state is ConfigEntryState.NOT_LOADED
