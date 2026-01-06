import logging
from datetime import timedelta

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_INPUTS, CONF_OUTPUTS, CONF_SOURCES, CONF_ZONES, DOMAIN
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
    client = data["client"]
    coordinator = data["coordinator"]
    config = data["config"]

    # Get input/output counts from config
    outputs = config.get(CONF_OUTPUTS, config.get(CONF_ZONES, []))
    inputs = config.get(CONF_INPUTS, config.get(CONF_SOURCES, []))
    output_count = len(outputs)
    input_count = len(inputs)

    # Service: Refresh
    async def handle_refresh_service(call: ServiceCall):
        """Handle manual refresh of all states."""
        await coordinator.async_request_refresh()

    # Service: Power On Output
    async def handle_power_on_output(call: ServiceCall):
        """Power on an output and set as active source."""
        output = call.data["output"]
        if not 1 <= output <= output_count:
            _LOGGER.error("Invalid output %d (must be 1-%d)", output, output_count)
            return

        await client.set_cec_out(output, "on")
        await client.set_output_active(output)
        await coordinator.async_request_refresh()
        _LOGGER.info("Powered on output %d and set as active source", output)

    # Service: Power Off Output
    async def handle_power_off_output(call: ServiceCall):
        """Power off an output."""
        output = call.data["output"]
        if not 1 <= output <= output_count:
            _LOGGER.error("Invalid output %d (must be 1-%d)", output, output_count)
            return

        await client.set_cec_out(output, "off")
        await coordinator.async_request_refresh()
        _LOGGER.info("Powered off output %d", output)

    # Service: Set Output Active
    async def handle_set_output_active(call: ServiceCall):
        """Set output as active source on TV."""
        output = call.data["output"]
        if not 1 <= output <= output_count:
            _LOGGER.error("Invalid output %d (must be 1-%d)", output, output_count)
            return

        await client.set_output_active(output)
        await coordinator.async_request_refresh()
        _LOGGER.info("Set output %d as active source", output)

    # Service: Power On Input
    async def handle_power_on_input(call: ServiceCall):
        """Power on an input device."""
        input_id = call.data["input"]
        if not 1 <= input_id <= input_count:
            _LOGGER.error("Invalid input %d (must be 1-%d)", input_id, input_count)
            return

        await client.set_cec_in(input_id, "on")
        await coordinator.async_request_refresh()
        _LOGGER.info("Powered on input %d", input_id)

    # Service: Power Off Input
    async def handle_power_off_input(call: ServiceCall):
        """Power off an input device."""
        input_id = call.data["input"]
        if not 1 <= input_id <= input_count:
            _LOGGER.error("Invalid input %d (must be 1-%d)", input_id, input_count)
            return

        await client.set_cec_in(input_id, "off")
        await coordinator.async_request_refresh()
        _LOGGER.info("Powered off input %d", input_id)

    # Service: Route Input to Output
    async def handle_route_input_to_output(call: ServiceCall):
        """Route a specific input to a specific output."""
        input_id = call.data["input"]
        output = call.data["output"]

        if not 1 <= input_id <= input_count:
            _LOGGER.error("Invalid input %d (must be 1-%d)", input_id, input_count)
            return
        if not 1 <= output <= output_count:
            _LOGGER.error("Invalid output %d (must be 1-%d)", output, output_count)
            return

        await client.set_output_source(input_id, output)
        await coordinator.async_request_refresh()
        _LOGGER.info("Routed input %d to output %d", input_id, output)

    # Service: Route Input to Multiple Outputs
    async def handle_route_input_to_outputs(call: ServiceCall):
        """Route a single input to multiple outputs."""
        input_id = call.data["input"]
        output_list = call.data["outputs"]

        if not 1 <= input_id <= input_count:
            _LOGGER.error("Invalid input %d (must be 1-%d)", input_id, input_count)
            return

        for output in output_list:
            if not 1 <= output <= output_count:
                _LOGGER.error("Invalid output %d (must be 1-%d)", output, output_count)
                continue
            await client.set_output_source(input_id, output)

        await coordinator.async_request_refresh()
        _LOGGER.info("Routed input %d to outputs %s", input_id, output_list)

    # Service: Power On All Outputs
    async def handle_power_on_all_outputs(call: ServiceCall):
        """Power on all outputs and set as active sources."""
        for output in range(1, output_count + 1):
            await client.set_cec_out(output, "on")
            await client.set_output_active(output)

        await coordinator.async_request_refresh()
        _LOGGER.info("Powered on all %d outputs", output_count)

    # Service: Power Off All Outputs
    async def handle_power_off_all_outputs(call: ServiceCall):
        """Power off all outputs."""
        for output in range(1, output_count + 1):
            await client.set_cec_out(output, "off")

        await coordinator.async_request_refresh()
        _LOGGER.info("Powered off all %d outputs", output_count)

    # Register all services with schemas
    hass.services.async_register(DOMAIN, "refresh", handle_refresh_service)

    hass.services.async_register(
        DOMAIN,
        "power_on_output",
        handle_power_on_output,
        schema=vol.Schema({vol.Required("output"): cv.positive_int}),
    )

    hass.services.async_register(
        DOMAIN,
        "power_off_output",
        handle_power_off_output,
        schema=vol.Schema({vol.Required("output"): cv.positive_int}),
    )

    hass.services.async_register(
        DOMAIN,
        "set_output_active",
        handle_set_output_active,
        schema=vol.Schema({vol.Required("output"): cv.positive_int}),
    )

    hass.services.async_register(
        DOMAIN,
        "power_on_input",
        handle_power_on_input,
        schema=vol.Schema({vol.Required("input"): cv.positive_int}),
    )

    hass.services.async_register(
        DOMAIN,
        "power_off_input",
        handle_power_off_input,
        schema=vol.Schema({vol.Required("input"): cv.positive_int}),
    )

    hass.services.async_register(
        DOMAIN,
        "route_input_to_output",
        handle_route_input_to_output,
        schema=vol.Schema(
            {
                vol.Required("input"): cv.positive_int,
                vol.Required("output"): cv.positive_int,
            }
        ),
    )

    hass.services.async_register(
        DOMAIN,
        "route_input_to_outputs",
        handle_route_input_to_outputs,
        schema=vol.Schema(
            {
                vol.Required("input"): cv.positive_int,
                vol.Required("outputs"): vol.All(cv.ensure_list, [cv.positive_int]),
            }
        ),
    )

    hass.services.async_register(
        DOMAIN, "power_on_all_outputs", handle_power_on_all_outputs
    )

    hass.services.async_register(
        DOMAIN, "power_off_all_outputs", handle_power_off_all_outputs
    )

    # Register update listener for options changes
    async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry):
        """Handle an options update."""
        await hass.config_entries.async_reload(entry.entry_id)

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded
    return unloaded
