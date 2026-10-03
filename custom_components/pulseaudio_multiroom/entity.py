"""Base entity for a room (PulseAudio sink) of the multiroom."""

from homeassistant.config_entries import ConfigSubentry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_SINK, DOMAIN
from .coordinator import PulseMultiroomCoordinator


class RoomEntity(CoordinatorEntity[PulseMultiroomCoordinator]):
    """Entity attached to the device of a room."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: PulseMultiroomCoordinator,
        room: ConfigSubentry,
        key: str,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.sink: str = room.data[CONF_SINK]
        self._attr_unique_id = f"{room.subentry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, room.subentry_id)},
            name=room.title,
            manufacturer="PulseAudio",
            model="Sink",
            model_id=self.sink,
        )

    @property
    def available(self) -> bool:
        """Return True if the room sink exists on the server."""
        return super().available and self.sink in self.coordinator.data.sinks
