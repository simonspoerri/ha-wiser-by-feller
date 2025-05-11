"""Diagnostics support for Wiser by Feller integration."""

from __future__ import annotations
from typing import Any
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.components.diagnostics import async_redact_data
import json
from . import DOMAIN

TO_REDACT = ["token", "serial_nr", "serial_number"]


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    _coordinator = hass.data[DOMAIN][entry.entry_id]
    _loads_json = []
    for load in _coordinator.loads:
        _loads_json.append(load.raw_data)

    _devices_json = []
    for device_id in _coordinator.devices:
        _devices_json.append(_coordinator.devices[device_id].raw_data)

    return {
        "entry_data": async_redact_data(entry.data, TO_REDACT),
        "loads": async_redact_data(_loads_json, TO_REDACT),
        "rooms": async_redact_data(_coordinator.rooms, TO_REDACT),
        "devices": async_redact_data(_devices_json, TO_REDACT),
        # TODO:  Gateway data
    }


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry, device: DeviceEntry
) -> dict[str, Any]:
    """Return diagnostics for a device."""
    _coordinator = hass.data[DOMAIN][entry.entry_id]
    _device_id = next(iter(device.identifiers))[1].partition("_")[0]
    _device_data = _coordinator.devices[_device_id].raw_data

    return {
        "device": async_redact_data(json.loads(device.json_repr), TO_REDACT),
        "device_data": async_redact_data(_device_data, TO_REDACT),
    }
