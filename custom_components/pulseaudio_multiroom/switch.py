"""Mute and source routing (loopback) switches of each room."""

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigSubentry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_SOURCE, SUBENTRY_ROOM, SUBENTRY_SOURCE
from .coordinator import PulseMultiroomConfigEntry, PulseMultiroomCoordinator
from .entity import RoomEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PulseMultiroomConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the mute switch and one loopback switch per source in each room."""
    coordinator = entry.runtime_data
    rooms = [s for s in entry.subentries.values() if s.subentry_type == SUBENTRY_ROOM]
    sources = [
        s for s in entry.subentries.values() if s.subentry_type == SUBENTRY_SOURCE
    ]

    expected_unique_ids: set[str] = set()
    for room in rooms:
        entities: list[SwitchEntity] = [RoomMute(coordinator, room, "mute")]
        entities.extend(
            RoomSourceLoopback(coordinator, room, source) for source in sources
        )
        expected_unique_ids.update(e.unique_id for e in entities if e.unique_id)
        async_add_entities(entities, config_subentry_id=room.subentry_id)

    # Loopback switches belong to the room device: drop the ones whose source
    # subentry was removed, HA only cleans up entities of a removed room.
    registry = er.async_get(hass)
    for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if (
            reg_entry.domain == Platform.SWITCH
            and reg_entry.unique_id not in expected_unique_ids
        ):
            registry.async_remove(reg_entry.entity_id)


class RoomMute(RoomEntity, SwitchEntity):
    """Mute of the room sink."""

    _attr_translation_key = "mute"

    @property
    def is_on(self) -> bool | None:
        """Return True if the room is muted."""
        if (sink := self.coordinator.data.sinks.get(self.sink)) is None:
            return None
        return sink.muted

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Mute the room."""
        await self.coordinator.async_run(
            self.coordinator.client.set_mute, self.sink, True
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Unmute the room."""
        await self.coordinator.async_run(
            self.coordinator.client.set_mute, self.sink, False
        )


class RoomSourceLoopback(RoomEntity, SwitchEntity):
    """Whether a source is routed to the room (a loopback module exists)."""

    _attr_translation_key = "source"

    def __init__(
        self,
        coordinator: PulseMultiroomCoordinator,
        room: ConfigSubentry,
        source: ConfigSubentry,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, room, f"{source.subentry_id}_loopback")
        self.source: str = source.data[CONF_SOURCE]
        self._attr_translation_placeholders = {"source": source.title}

    @property
    def _modules(self) -> list[int]:
        return self.coordinator.data.loopbacks.get((self.sink, self.source), [])

    @property
    def available(self) -> bool:
        """Return True if the source can be routed (or is already routed)."""
        return super().available and (
            self.source in self.coordinator.data.sources or bool(self._modules)
        )

    @property
    def is_on(self) -> bool:
        """Return True if the source plays in the room."""
        return bool(self._modules)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Route the source to the room."""
        if not self.is_on:
            await self.coordinator.async_run(
                self.coordinator.client.load_loopback, self.sink, self.source
            )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Stop routing the source to the room."""
        if modules := self._modules:
            await self.coordinator.async_run(
                self.coordinator.client.unload_modules, modules
            )
