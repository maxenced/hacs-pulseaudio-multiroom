"""Tests for the config flow and the room/source subentry flows."""

from unittest.mock import MagicMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pulseaudio_multiroom.api import PulseConnectionError
from custom_components.pulseaudio_multiroom.const import (
    CONF_SINK,
    CONF_SOURCE,
    DOMAIN,
    SUBENTRY_ROOM,
    SUBENTRY_SOURCE,
)
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from .conftest import state_of


@pytest.mark.usefixtures("mock_client")
async def test_user_flow(hass: HomeAssistant) -> None:
    """A reachable server creates an entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "pulse.local", CONF_PORT: 4713}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "PulseAudio pulse.local"
    assert result["data"] == {CONF_HOST: "pulse.local", CONF_PORT: 4713}
    assert result["result"].unique_id == "pulse.local"


async def test_user_flow_cannot_connect(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """An unreachable server shows an error, then the flow can recover."""
    mock_client.get_state.side_effect = PulseConnectionError("refused")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "pulse.local", CONF_PORT: 4713}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}

    mock_client.get_state.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "pulse.local", CONF_PORT: 4713}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


@pytest.mark.usefixtures("mock_client")
async def test_user_flow_already_configured(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """The same host can only be added once."""
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "pulse.local", CONF_PORT: 4713}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reconfigure(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """The port can be changed, the host can't."""
    entry = setup_integration
    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "pulse.local", CONF_PORT: 4714}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_PORT] == 4714

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "other.local", CONF_PORT: 4713}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "unique_id_mismatch"


async def test_add_room(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """A room is added from the sinks of the server, a sink only once."""
    entry = setup_integration
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_ROOM), context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    schema = result["data_schema"]
    assert schema is not None
    sink_selector = schema.schema[CONF_SINK]
    assert sink_selector.config["options"] == ["output1", "output2"]

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {CONF_NAME: "Cuisine", CONF_SINK: "output1"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_SINK: "already_configured"}

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {CONF_NAME: "Cuisine", CONF_SINK: "output3"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert hass.states.get("number.cuisine_volume") is not None


async def test_reconfigure_source(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """A source can be renamed, which renames its switches."""
    entry = setup_integration
    result = await entry.start_subentry_reconfigure_flow(hass, "source_radio")
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {CONF_NAME: "FIP", CONF_SOURCE: "null-radio.monitor"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert entry.subentries["source_radio"].title == "FIP"
    assert state_of(hass, "switch.salon_radio").name == "Salon FIP"


async def test_subentry_needs_loaded_entry(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """Rooms can't be added while the server is not connected."""
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.subentries.async_init(
        (config_entry.entry_id, SUBENTRY_SOURCE), context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "entry_not_loaded"
