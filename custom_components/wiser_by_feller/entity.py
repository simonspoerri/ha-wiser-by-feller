"""Base entity class for Wiser by Feller integration."""

from __future__ import annotations

from typing import Any

from aiowiserbyfeller import Device, Load
from aiowiserbyfeller.util import parse_wiser_device_ref_c

from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DOMAIN
from .const import MANUFACTURER
from .coordinator import WiserCoordinator
from .util import resolve_device_name


class WiserEntity(CoordinatorEntity):
    def __init__(
        self,
        coordinator: WiserCoordinator,
        load: Load | None,
        device: Device,
        room: dict | None,
    ) -> None:
        info = parse_wiser_device_ref_c(device.c["comm_ref"])

        self.coordinator_context = (
            device.id if load is None else load.id
        )  # TODO: Suboptimal
        self.coordinator = coordinator
        self._attr_has_entity_name = True
        self._attr_unique_id = (
            device.id if load is None else f"{load.device}_{load.channel}"
        )
        self._device = device
        self._device_name = resolve_device_name(device, room, load)
        self._is_gateway = info["wlan"]
        self._load = load
        self._room = room

    @property
    def device_info(self) -> DeviceInfo:
        model = f"{self._device.c['comm_ref']} + {self._device.a['comm_ref']}"
        firmware = f"{self._device.c['fw_version']} (Controls) / {self._device.a['fw_version']} (Base)"
        url = f"http://{self.coordinator._api.auth.host}" if self._is_gateway else None
        area = None if self._room is None else self._room["name"]
        via = (
            (DOMAIN, self.coordinator.gateway.combined_serial_number)
            if not self._is_gateway
            else None
        )

        return DeviceInfo(
            identifiers={
                (DOMAIN, self._attr_unique_id),
            },
            name=resolve_device_name(self._device, self._room, self._load),
            manufacturer=MANUFACTURER,
            model=model,
            sw_version=firmware,
            serial_number=self._device.combined_serial_number,
            suggested_area=area,
            configuration_url=url,
            via_device=via,
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._load.raw_state = self.coordinator.states[self._load.id]
        self.async_write_ha_state()
