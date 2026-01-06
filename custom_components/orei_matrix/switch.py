import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_INPUTS, CONF_SOURCES, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    client = data["client"]
    coordinator = data["coordinator"]
    config = data["config"]

    # Create power switch and input switches
    entities: list[SwitchEntity] = [
        OreiMatrixPowerSwitch(client, coordinator, config, entry.entry_id)
    ]

    # Create input switches
    inputs = config.get(CONF_INPUTS, config.get(CONF_SOURCES, []))
    for idx, input_name in enumerate(inputs, start=1):
        entities.append(
            OreiMatrixInputSwitch(client, coordinator, input_name, idx, entry.entry_id)
        )

    async_add_entities(entities)


class OreiMatrixPowerSwitch(CoordinatorEntity, SwitchEntity):
    """Switch for Orei HDMI Matrix power."""

    def __init__(self, client, coordinator, config, entry_id):
        super().__init__(coordinator)
        self._client = client
        self._config = config
        self._entry_id = entry_id

        # Use entry_id for unique ID (stable across IP changes)
        self._attr_unique_id = f"{entry_id}_power"

        # Set friendly name and entity_id suggestion
        self._attr_name = "Power"
        self._attr_has_entity_name = True  # Use device name + entity name

    @property
    def device_info(self):
        """Device info for grouping and model-based naming."""
        model = self.coordinator.data.get("type", "Unknown")
        name = f"Orei {model}" if model != "Unknown" else "Orei HDMI Matrix"
        return {
            "identifiers": {(DOMAIN, self._entry_id)},
            "name": name,
            "manufacturer": "Orei",
            "model": model,
            "configuration_url": f"http://{self._config.get('host')}",
        }

    @property
    def is_on(self):
        return self.coordinator.data.get("power")

    async def async_turn_on(self, **kwargs):
        await self._client.set_power(True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        await self._client.set_power(False)
        await self.coordinator.async_request_refresh()


class OreiMatrixInputSwitch(CoordinatorEntity, SwitchEntity):
    """Represents one HDMI input source with CEC control."""

    def __init__(self, client, coordinator, input_name, input_id, entry_id):
        """Initialize the input switch."""
        super().__init__(coordinator)
        self._client = client
        self._input_id = input_id
        self._entry_id = entry_id
        self._host = coordinator.config_entry.data.get("host")

        # Use entry_id for stable unique ID
        self._attr_unique_id = f"{entry_id}_input_{input_id}"

        # Set friendly name
        self._attr_name = input_name
        self._attr_has_entity_name = True

    @property
    def available(self):
        """Entity availability based on matrix power."""
        return bool(self.coordinator.data.get("power"))

    @property
    def is_on(self):
        """Return True if the input has an active HDMI signal (sync state).

        States from device:
        - "sync" = Active video signal → ON
        - "connect" = Cable connected, no signal → OFF
        - "disconnect" = Nothing connected → OFF
        """
        if not self.available:
            return False

        input_links = self.coordinator.data.get("input_links", {})
        link_state = input_links.get(self._input_id, "disconnect")

        # Only show "on" when actively sending video
        return link_state == "sync"

    @property
    def extra_state_attributes(self):
        """Return additional state attributes."""
        outputs = self.coordinator.data.get("outputs", {})
        input_links = self.coordinator.data.get("input_links", {})

        # Find which outputs this input is routed to
        routed_outputs = [
            output_id
            for output_id, input_id in outputs.items()
            if input_id == self._input_id
        ]

        link_state = input_links.get(self._input_id, "disconnect")

        return {
            "input_id": self._input_id,
            "link_state": link_state,
            "routed_to_outputs": routed_outputs if routed_outputs else "None",
            "output_count": len(routed_outputs),
        }

    @property
    def device_info(self):
        """Device info for grouping under the matrix."""
        model = self.coordinator.data.get("type", "Unknown")
        name = f"Orei {model}" if model != "Unknown" else "Orei HDMI Matrix"
        return {
            "identifiers": {(DOMAIN, self._entry_id)},
            "name": name,
            "manufacturer": "Orei",
            "model": model,
            "configuration_url": f"http://{self._host}",
        }

    async def async_turn_on(self, **kwargs):
        """Send CEC power on command to this input."""
        if not self.available:
            _LOGGER.warning("Matrix is off; cannot control %s", self.name)
            return

        await self._client.set_cec_in(self._input_id, "on")
        _LOGGER.info("Sent CEC power on to %s (input %d)", self.name, self._input_id)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        """Send CEC power off command to this input."""
        if not self.available:
            _LOGGER.warning("Matrix is off; cannot control %s", self.name)
            return

        await self._client.set_cec_in(self._input_id, "off")
        _LOGGER.info("Sent CEC power off to %s (input %d)", self.name, self._input_id)
        await self.coordinator.async_request_refresh()
