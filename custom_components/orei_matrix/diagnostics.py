"""Diagnostics support for Orei HDMI Matrix."""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_HOST, DOMAIN


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    coordinator_data: dict = coordinator.data or {}

    return {
        "config_entry": {
            "host": entry.data.get(CONF_HOST),
            "port": entry.data.get("port", 23),
            "input_count": len(entry.data.get("inputs", entry.data.get("sources", []))),
            "output_count": len(entry.data.get("outputs", entry.data.get("zones", []))),
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "last_exception": str(coordinator.last_exception)
            if coordinator.last_exception
            else None,
        },
        "device_state": {
            "connected": coordinator_data.get("connected"),
            "power": coordinator_data.get("power"),
            "type": coordinator_data.get("type"),
            "firmware_version": coordinator_data.get("firmware_version"),
            "routing": coordinator_data.get("outputs"),
            "input_links": coordinator_data.get("input_links"),
        },
    }
