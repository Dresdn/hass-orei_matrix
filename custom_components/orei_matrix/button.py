import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_OUTPUTS, CONF_ZONES, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Orei HDMI Matrix buttons."""
    data = hass.data[DOMAIN][entry.entry_id]
    client = data["client"]
    coordinator = data["coordinator"]
    config = data["config"]

    # Support both new (outputs) and old (zones) format
    outputs = config.get(CONF_OUTPUTS, config.get(CONF_ZONES, []))

    entities = []

    # Create explicit power on/off buttons for each output
    for idx, output_name in enumerate(outputs, start=1):
        entities.append(
            OreiMatrixOutputPowerButton(
                client, coordinator, output_name, idx, entry.entry_id, "on"
            )
        )
        entities.append(
            OreiMatrixOutputPowerButton(
                client, coordinator, output_name, idx, entry.entry_id, "off"
            )
        )

    async_add_entities(entities)


class OreiMatrixOutputPowerButton(CoordinatorEntity, ButtonEntity):
    """Button to send explicit CEC power commands to an output."""

    def __init__(
        self, client, coordinator, output_name, output_id, entry_id, command_type
    ):
        """Initialize the button."""
        super().__init__(coordinator)
        self._client = client
        self._output_id = output_id
        self._entry_id = entry_id
        self._command_type = command_type
        self._host = coordinator.config_entry.data.get("host")

        # Use entry_id for stable unique ID
        self._attr_unique_id = f"{entry_id}_output_{output_id}_power_{command_type}"

        # Set friendly name
        cmd_name = "Power On" if command_type == "on" else "Power Off"
        self._attr_name = f"{output_name} {cmd_name}"
        self._attr_has_entity_name = True

        # Set icons
        self._attr_icon = "mdi:power-on" if command_type == "on" else "mdi:power-off"

    @property
    def available(self):
        """Entity availability based on matrix power."""
        return bool(self.coordinator.data.get("power"))

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

    async def async_press(self) -> None:
        """Handle the button press."""
        if not self.available:
            _LOGGER.warning("Matrix is off; cannot control output %d", self._output_id)
            return

        # Send CEC command
        await self._client.set_cec_out(self._output_id, self._command_type)

        # If powering on, also set as active source
        if self._command_type == "on":
            await self._client.set_output_active(self._output_id)
            _LOGGER.info(
                "Powered on output %d and set as active source", self._output_id
            )
        else:
            _LOGGER.info("Powered off output %d", self._output_id)


class OreiMatrixOutputButton(CoordinatorEntity, ButtonEntity):
    """Represents one HDMI matrix output as a button to cycle sources."""

    def __init__(self, client, coordinator, config, zone_name, output_id, entry_id):
        super().__init__(coordinator)
        sources = config.get("sources", [])
        self._client = client
        self._config = config
        self._output_id = output_id
        self._sources = sources
        self._current = None
        self._entry_id = entry_id

        # Use entry_id for stable unique ID
        self._attr_unique_id = f"{entry_id}_output_{output_id}_next"

        # Set friendly name
        self._attr_name = f"{zone_name} Next Source"
        self._attr_has_entity_name = True

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

    @callback
    def _handle_coordinator_update(self):
        outputs = self.coordinator.data.get("outputs")
        if not outputs:
            return
        self._current = outputs.get(self._output_id)
        self.async_write_ha_state()

    async def async_press(self) -> None:
        """Handle the button press."""
        if self._current is None:
            _LOGGER.warning(
                "Current input is unknown; cannot change source for %s.", self.name
            )
            return

        input_id = (self._current % len(self._sources)) + 1
        source = self._sources[input_id - 1]
        await self._client.set_output_source(input_id, self._output_id)
        await self.coordinator.async_request_refresh()
        _LOGGER.info("Switched %s to %s", self.name, source)
        await self.coordinator.async_request_refresh()
        _LOGGER.info("Switched %s to %s", self.name, source)
