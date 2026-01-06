import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN
from .coordinator import OreiMatrixClient

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["media_player", "switch", "button"]
_LOGGER.warning("OREI MATRIX DEV BUILD LOADED")


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    client = OreiMatrixClient(entry.data["host"], entry.data.get("port", 23))
    type_str = await client.get_type()

    async def async_update_data():
        try:
            power = await client.get_power()
            outputs = await client.get_output_sources()
            return {"power": power, "type": type_str, "outputs": outputs}
        except Exception as err:
            _LOGGER.error("Update failed: %s", err)
            raise UpdateFailed(err) from err

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="orei_matrix",
        update_method=async_update_data,
        update_interval=timedelta(seconds=30),
    )

    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
        "config": entry.options if entry.options else entry.data,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]

    async def handle_refresh_service(call: ServiceCall):
        """Handle manual refresh of all states."""
        await coordinator.async_request_refresh()

    # Register the service
    hass.services.async_register(
        DOMAIN,
        "refresh",
        handle_refresh_service,
        schema=None,
    )

    async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry):
        """Handle an options update."""
        await hass.config_entries.async_reload(entry.entry_id)

    # Register update listener for options changes
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded
    return unloaded
