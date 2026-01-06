import logging

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.selector import selector

from .const import (
    CONF_HOST,
    CONF_INPUTS,
    CONF_OUTPUTS,
    CONF_PORT,
    CONF_SOURCES,
    CONF_ZONES,
    DOMAIN,
)
from .coordinator import OreiMatrixClient

_LOGGER = logging.getLogger(__name__)


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidDeviceResponse(HomeAssistantError):
    """Error to indicate device returned invalid response."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""


async def validate_input(hass, data):
    """Validate the user input allows us to connect.

    Data has the keys from CONF_* with values provided by the user.
    """
    host = data[CONF_HOST]
    port = data.get(CONF_PORT, 23)
    client = OreiMatrixClient(host, port)

    try:
        await client.connect()
    except TimeoutError as err:
        _LOGGER.error("Connection timeout to %s:%s", host, port)
        raise CannotConnect(
            f"Connection timeout - device at {host}:{port} did not respond"
        ) from err
    except OSError as err:
        _LOGGER.error("Network error connecting to %s:%s - %s", host, port, err)
        raise CannotConnect(
            f"Network error - check that {host}:{port} is reachable"
        ) from err
    except Exception as err:
        _LOGGER.error("Failed to connect to %s:%s - %s", host, port, err)
        raise CannotConnect(f"Connection failed - {err}") from err

    try:
        device_type = await client.get_type()
        status = await client.get_status()
    finally:
        await client.disconnect()

    if not device_type or len(device_type) < 3:
        raise InvalidDeviceResponse(
            f"Device at {host}:{port} did not respond with valid model type"
        )

    return {
        "title": f"Orei {device_type}",
        "type": device_type,
        "input_count": status["input_count"],
        "output_count": status["output_count"],
    }


class OreiMatrixConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle Orei HDMI Matrix config flow."""

    VERSION = 1

    def __init__(self):
        """Initialize the config flow."""
        self._host: str | None = None
        self._port: int | None = None
        self._device_info: dict | None = None

    @staticmethod
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OreiMatrixOptionsFlow()

    async def async_step_user(self, user_input=None):
        """Handle initial connection setup - IP and port only."""
        errors = {}
        description_placeholders = {}

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
                # Store connection info for next step
                self._host = user_input[CONF_HOST]
                self._port = user_input.get(CONF_PORT, 23)
                self._device_info = info
                # Move to naming step
                return await self.async_step_naming()
            except CannotConnect as err:
                errors["base"] = "cannot_connect"
                description_placeholders["error_detail"] = str(err)
            except InvalidDeviceResponse as err:
                errors["base"] = "invalid_response"
                description_placeholders["error_detail"] = str(err)
            except Exception as err:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
                description_placeholders["error_detail"] = str(err)

        data_schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Optional(CONF_PORT, default=23): int,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
            description_placeholders=description_placeholders,
        )

    async def async_step_naming(self, user_input=None):
        """Handle naming inputs and outputs."""
        if user_input is not None:
            # Extract input and output names from user_input
            inputs = []
            outputs = []

            for key, value in user_input.items():
                if key.startswith("input_") and value:
                    inputs.append(value)
                elif key.startswith("output_") and value:
                    outputs.append(value)

            # Create the config entry
            data = {
                CONF_HOST: self._host,
                CONF_PORT: self._port,
                CONF_INPUTS: inputs,
                CONF_OUTPUTS: outputs,
            }

            assert self._device_info is not None
            return self.async_create_entry(
                title=self._device_info["title"],
                data=data,
            )

        # Build schema with auto-discovered counts
        assert self._device_info is not None
        input_count = self._device_info["input_count"]
        output_count = self._device_info["output_count"]

        schema_dict = {}
        for i in range(1, input_count + 1):
            schema_dict[vol.Optional(f"input_{i}", default=f"Input {i}")] = str
        for i in range(1, output_count + 1):
            schema_dict[vol.Optional(f"output_{i}", default=f"Output {i}")] = str

        return self.async_show_form(
            step_id="naming",
            data_schema=vol.Schema(schema_dict),
            description_placeholders={
                "device_type": self._device_info["type"],
                "input_count": str(input_count),
                "output_count": str(output_count),
            },
        )


class OreiMatrixOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Orei HDMI Matrix."""

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        errors = {}
        description_placeholders = {}

        if user_input is not None:
            # Validate connection if host or port changed
            current_host = self.config_entry.data.get(CONF_HOST)
            current_port = self.config_entry.data.get(CONF_PORT, 23)
            new_host = user_input.get(CONF_HOST)
            new_port = user_input.get(CONF_PORT, 23)

            if new_host != current_host or new_port != current_port:
                try:
                    info = await validate_input(self.hass, user_input)
                    new_title = info["title"]
                except CannotConnect as err:
                    errors["base"] = "cannot_connect"
                    description_placeholders["error_detail"] = str(err)
                except InvalidDeviceResponse as err:
                    errors["base"] = "invalid_response"
                    description_placeholders["error_detail"] = str(err)
                except Exception as err:
                    _LOGGER.exception("Unexpected exception")
                    errors["base"] = "unknown"
                    description_placeholders["error_detail"] = str(err)
            else:
                new_title = f"Orei HDMI Matrix ({new_host})"

            if not errors:
                # Update config entry with new data AND title
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    title=new_title,
                    data={**self.config_entry.data, **user_input},
                )
                return self.async_create_entry(title="", data={})

        # Pre-fill with current values (support both old and new formats)
        current_data = self.config_entry.data
        # Try new format first, fall back to old format
        inputs = current_data.get(CONF_INPUTS, current_data.get(CONF_SOURCES, []))
        outputs = current_data.get(CONF_OUTPUTS, current_data.get(CONF_ZONES, []))

        data_schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=current_data.get(CONF_HOST, "")): str,
                vol.Required(CONF_PORT, default=current_data.get(CONF_PORT, 23)): int,
                vol.Optional(CONF_INPUTS, default=inputs): selector(
                    {"text": {"multiple": True}}
                ),
                vol.Optional(CONF_OUTPUTS, default=outputs): selector(
                    {"text": {"multiple": True}}
                ),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=data_schema,
            errors=errors,
            description_placeholders=description_placeholders,
        )
