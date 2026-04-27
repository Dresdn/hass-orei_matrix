import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Orei Matrix sensors."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]

    async_add_entities([OreiMatrixFirmwareSensor(coordinator, entry.entry_id)])


class OreiMatrixFirmwareSensor(CoordinatorEntity, SensorEntity):
    """Sensor that surfaces the matrix firmware version string."""

    _attr_has_entity_name = True
    _attr_name = "Firmware Version"
    _attr_icon = "mdi:chip"

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._attr_unique_id = f"{entry_id}_firmware_version"
        self._host = coordinator.config_entry.data.get("host")

    @property
    def native_value(self) -> str | None:
        """Return the firmware version string reported by the matrix."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("firmware_version")

    @property
    def device_info(self) -> DeviceInfo:
        data = self.coordinator.data or {}
        model = data.get("type", "Unknown")
        fw = data.get("firmware_version")
        name = f"Orei {model}" if model != "Unknown" else "Orei HDMI Matrix"
        info = DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name=name,
            manufacturer="OREI",
            model=model,
            configuration_url=f"http://{self._host}",
        )
        if fw:
            info["sw_version"] = fw
        return info
