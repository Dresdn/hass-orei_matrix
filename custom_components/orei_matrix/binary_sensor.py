import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Orei Matrix binary sensors."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]

    async_add_entities([OreiMatrixConnectionSensor(coordinator, entry.entry_id)])


class OreiMatrixConnectionSensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor that reflects live TCP connection state to the matrix."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_has_entity_name = True
    _attr_name = "Connected"

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._attr_unique_id = f"{entry_id}_connected"
        self._host = coordinator.config_entry.data.get("host")

    @property
    def available(self) -> bool:
        """Connectivity sensor is always available — it reports the connection state."""
        return True

    @property
    def is_on(self) -> bool:
        """Return True when the last coordinator update succeeded."""
        return self.coordinator.last_update_success

    @property
    def device_info(self) -> DeviceInfo:
        data = self.coordinator.data or {}
        model = data.get("type", "Unknown")
        name = f"Orei {model}" if model != "Unknown" else "Orei HDMI Matrix"
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name=name,
            manufacturer="OREI",
            model=model,
            configuration_url=f"http://{self._host}",
        )
