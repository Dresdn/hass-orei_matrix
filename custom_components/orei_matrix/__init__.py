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

PLATFORMS = ["binary_sensor", "media_player", "sensor", "switch", "button"]
_LOGGER.warning("OREI MATRIX DEV BUILD LOADED")


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    client = OreiMatrixClient(entry.data["host"], entry.data.get("port", 23))
    type_str = await client.get_type()

    async def async_update_data() -> dict:
        try:
            power = await client.get_power()
            outputs = await client.get_output_sources()
            input_links = await client.get_in_links()
            return {
                "power": power,
                "type": type_str,
                "outputs": outputs,
                "input_links": input_links,
                "connected": client.is_connected,
                "firmware_version": client.firmware_version,
            }
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

    # ---------------------
    # Service: Refresh
    # ---------------------
    async def handle_refresh_service(call: ServiceCall) -> None:
        """Handle manual refresh of all states."""
        await coordinator.async_request_refresh()

    # ---------------------
    # Services: Output power (CEC)
    # ---------------------
    async def handle_power_on_output(call: ServiceCall) -> None:
        output = call.data["output"]
        if not 1 <= output <= output_count:
            _LOGGER.error("Invalid output %d (must be 1-%d)", output, output_count)
            return
        await client.set_cec_out(output, "on")
        await client.set_output_active(output)
        await coordinator.async_request_refresh()
        _LOGGER.info("Powered on output %d and set as active source", output)

    async def handle_power_off_output(call: ServiceCall) -> None:
        output = call.data["output"]
        if not 1 <= output <= output_count:
            _LOGGER.error("Invalid output %d (must be 1-%d)", output, output_count)
            return
        await client.set_cec_out(output, "off")
        await coordinator.async_request_refresh()
        _LOGGER.info("Powered off output %d", output)

    async def handle_set_output_active(call: ServiceCall) -> None:
        output = call.data["output"]
        if not 1 <= output <= output_count:
            _LOGGER.error("Invalid output %d (must be 1-%d)", output, output_count)
            return
        await client.set_output_active(output)
        await coordinator.async_request_refresh()
        _LOGGER.info("Set output %d as active source", output)

    # ---------------------
    # Services: Input power (CEC)
    # ---------------------
    async def handle_power_on_input(call: ServiceCall) -> None:
        input_id = call.data["input"]
        if not 1 <= input_id <= input_count:
            _LOGGER.error("Invalid input %d (must be 1-%d)", input_id, input_count)
            return
        await client.set_cec_in(input_id, "on")
        await coordinator.async_request_refresh()
        _LOGGER.info("Powered on input %d", input_id)

    async def handle_power_off_input(call: ServiceCall) -> None:
        input_id = call.data["input"]
        if not 1 <= input_id <= input_count:
            _LOGGER.error("Invalid input %d (must be 1-%d)", input_id, input_count)
            return
        await client.set_cec_in(input_id, "off")
        await coordinator.async_request_refresh()
        _LOGGER.info("Powered off input %d", input_id)

    # ---------------------
    # Services: CEC output volume / mute
    # ---------------------
    async def handle_cec_volume_up(call: ServiceCall) -> None:
        output = call.data["output"]
        if not 1 <= output <= output_count:
            _LOGGER.error("Invalid output %d (must be 1-%d)", output, output_count)
            return
        await client.set_cec_out_volume_up(output)
        _LOGGER.info("Sent CEC volume-up to output %d", output)

    async def handle_cec_volume_down(call: ServiceCall) -> None:
        output = call.data["output"]
        if not 1 <= output <= output_count:
            _LOGGER.error("Invalid output %d (must be 1-%d)", output, output_count)
            return
        await client.set_cec_out_volume_down(output)
        _LOGGER.info("Sent CEC volume-down to output %d", output)

    async def handle_cec_mute(call: ServiceCall) -> None:
        output = call.data["output"]
        if not 1 <= output <= output_count:
            _LOGGER.error("Invalid output %d (must be 1-%d)", output, output_count)
            return
        await client.set_cec_out_mute(output)
        _LOGGER.info("Sent CEC mute to output %d", output)

    async def handle_cec_power_on(call: ServiceCall) -> None:
        output = call.data["output"]
        if not 1 <= output <= output_count:
            _LOGGER.error("Invalid output %d (must be 1-%d)", output, output_count)
            return
        await client.set_cec_out_power_on(output)
        _LOGGER.info("Sent CEC power-on to output %d", output)

    async def handle_cec_power_off(call: ServiceCall) -> None:
        output = call.data["output"]
        if not 1 <= output <= output_count:
            _LOGGER.error("Invalid output %d (must be 1-%d)", output, output_count)
            return
        await client.set_cec_out_power_off(output)
        _LOGGER.info("Sent CEC power-off to output %d", output)

    async def handle_cec_set_active_source(call: ServiceCall) -> None:
        output = call.data["output"]
        if not 1 <= output <= output_count:
            _LOGGER.error("Invalid output %d (must be 1-%d)", output, output_count)
            return
        await client.set_cec_out_active_source(output)
        _LOGGER.info("Sent CEC active-source to output %d", output)

    # ---------------------
    # Services: Routing
    # ---------------------
    async def handle_route_input_to_output(call: ServiceCall) -> None:
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

    async def handle_route_input_to_outputs(call: ServiceCall) -> None:
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

    async def handle_route_input_to_all_outputs(call: ServiceCall) -> None:
        input_id = call.data["input"]
        if not 1 <= input_id <= input_count:
            _LOGGER.error("Invalid input %d (must be 1-%d)", input_id, input_count)
            return
        await client.route_input_to_all_outputs(input_id)
        await coordinator.async_request_refresh()
        _LOGGER.info("Routed input %d to all outputs", input_id)

    # ---------------------
    # Services: All outputs
    # ---------------------
    async def handle_power_on_all_outputs(call: ServiceCall) -> None:
        for output in range(1, output_count + 1):
            await client.set_cec_out(output, "on")
            await client.set_output_active(output)
        await coordinator.async_request_refresh()
        _LOGGER.info("Powered on all %d outputs", output_count)

    async def handle_power_off_all_outputs(call: ServiceCall) -> None:
        for output in range(1, output_count + 1):
            await client.set_cec_out(output, "off")
        await coordinator.async_request_refresh()
        _LOGGER.info("Powered off all %d outputs", output_count)

    # ---------------------
    # Service: EDID management
    # ---------------------
    async def handle_set_edid(call: ServiceCall) -> None:
        input_id = call.data["input"]
        edid_profile = call.data["edid_profile"]
        if not 1 <= input_id <= input_count:
            _LOGGER.error("Invalid input %d (must be 1-%d)", input_id, input_count)
            return
        await client.set_edid(input_id, edid_profile)
        _LOGGER.info("Set EDID profile '%s' on input %d", edid_profile, input_id)

    # ---------------------
    # Register all services
    # ---------------------
    _output_schema = vol.Schema({vol.Required("output"): cv.positive_int})
    _input_schema = vol.Schema({vol.Required("input"): cv.positive_int})

    _reg = hass.services.async_register
    _reg(DOMAIN, "refresh", handle_refresh_service)
    _reg(DOMAIN, "power_on_output", handle_power_on_output, schema=_output_schema)
    _reg(DOMAIN, "power_off_output", handle_power_off_output, schema=_output_schema)
    _reg(DOMAIN, "set_output_active", handle_set_output_active, schema=_output_schema)
    _reg(DOMAIN, "power_on_input", handle_power_on_input, schema=_input_schema)
    _reg(DOMAIN, "power_off_input", handle_power_off_input, schema=_input_schema)
    _reg(DOMAIN, "cec_volume_up", handle_cec_volume_up, schema=_output_schema)
    _reg(DOMAIN, "cec_volume_down", handle_cec_volume_down, schema=_output_schema)
    _reg(DOMAIN, "cec_mute", handle_cec_mute, schema=_output_schema)
    _reg(DOMAIN, "cec_power_on", handle_cec_power_on, schema=_output_schema)
    _reg(DOMAIN, "cec_power_off", handle_cec_power_off, schema=_output_schema)
    _reg(
        DOMAIN,
        "cec_set_active_source",
        handle_cec_set_active_source,
        schema=_output_schema,
    )
    _reg(
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
    _reg(
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
    _reg(
        DOMAIN,
        "route_input_to_all_outputs",
        handle_route_input_to_all_outputs,
        schema=_input_schema,
    )
    _reg(DOMAIN, "power_on_all_outputs", handle_power_on_all_outputs)
    _reg(DOMAIN, "power_off_all_outputs", handle_power_off_all_outputs)
    _reg(
        DOMAIN,
        "set_edid",
        handle_set_edid,
        schema=vol.Schema(
            {
                vol.Required("input"): cv.positive_int,
                vol.Required("edid_profile"): cv.string,
            }
        ),
    )

    # Register update listener for options changes
    async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Handle an options update."""
        await hass.config_entries.async_reload(entry.entry_id)

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded
