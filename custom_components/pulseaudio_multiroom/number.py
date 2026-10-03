"""Volume of each room."""

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import SUBENTRY_ROOM
from .coordinator import PulseMultiroomConfigEntry
from .entity import RoomEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PulseMultiroomConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up one volume entity per room."""
    coordinator = entry.runtime_data
    for subentry_id, room in entry.subentries.items():
        if room.subentry_type == SUBENTRY_ROOM:
            async_add_entities(
                [RoomVolume(coordinator, room, "volume")],
                config_subentry_id=subentry_id,
            )


class RoomVolume(RoomEntity, NumberEntity):
    """Volume of the room sink, in percent."""

    _attr_translation_key = "volume"
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER

    @property
    def native_value(self) -> int | None:
        """Return the current volume."""
        if (sink := self.coordinator.data.sinks.get(self.sink)) is None:
            return None
        return sink.volume

    async def async_set_native_value(self, value: float) -> None:
        """Set the volume."""
        await self.coordinator.async_run(
            self.coordinator.client.set_volume, self.sink, round(value)
        )
