import logging

from homeassistant.components.media_player import MediaPlayerEntity
from homeassistant.components.media_player.const import MediaPlayerEntityFeature
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_INPUTS, CONF_OUTPUTS, CONF_SOURCES, CONF_ZONES, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Orei HDMI Matrix outputs as media players."""
    data = hass.data[DOMAIN][entry.entry_id]
    client = data["client"]
    coordinator = data["coordinator"]
    config = data["config"]

    # Support both new (outputs) and old (zones) format
    outputs = config.get(CONF_OUTPUTS, config.get(CONF_ZONES, []))
    inputs = config.get(CONF_INPUTS, config.get(CONF_SOURCES, []))

    entities = [
        OreiMatrixOutputMediaPlayer(
            client, coordinator, inputs, output_name, idx, entry.entry_id
        )
        for idx, output_name in enumerate(outputs, start=1)
    ]

    async_add_entities(entities)


class OreiMatrixOutputMediaPlayer(CoordinatorEntity, MediaPlayerEntity):
    """Represents one HDMI matrix output as a media player source selector."""

    _attr_supported_features = MediaPlayerEntityFeature.SELECT_SOURCE

    def __init__(self, client, coordinator, inputs, output_name, output_id, entry_id):
        super().__init__(coordinator)
        self._client = client
        self._output_id = output_id
        self._inputs = inputs
        self._attr_source_list = inputs
        self._attr_source = None
        self._entry_id = entry_id
        self._host = coordinator.config_entry.data.get("host")

        # Use entry_id for stable unique ID
        self._attr_unique_id = f"{entry_id}_output_{output_id}"

        # Set friendly name
        self._attr_name = output_name
        self._attr_has_entity_name = True

    @property
    def available(self):
        """Entity availability based on matrix power."""
        return bool(self.coordinator.data.get("power"))

    @property
    def state(self):
        """Entity state is 'on' when matrix powered."""
        return STATE_ON if self.available else STATE_OFF

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
            "configuration_url": f"http://{self._host}",
        }

    @callback
    def _handle_coordinator_update(self):
        if not self.available:
            return
        outputs = self.coordinator.data.get("outputs")
        if not outputs:
            return
        src_id = outputs.get(self._output_id)
        if src_id and 1 <= src_id <= len(self._inputs):
            self._attr_source = self._inputs[src_id - 1]
            self.async_write_ha_state()

    async def async_select_source(self, source):
        """Change active source for this output."""
        if not self.available:
            _LOGGER.warning("Matrix is off; cannot change source for %s.", self.name)
            return
        if source not in self._inputs:
            _LOGGER.warning("Unknown source %s for %s", source, self.name)
            return

        input_id = self._inputs.index(source) + 1

        # Just switch the input routing - user controls TV power manually
        await self._client.set_output_source(input_id, self._output_id)

        await self.coordinator.async_request_refresh()
        _LOGGER.info(
            "Switched %s to %s (input %d)",
            self.name,
            source,
            input_id,
        )
