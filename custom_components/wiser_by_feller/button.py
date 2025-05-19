"""Platform for button integration."""

from __future__ import annotations

import logging
from typing import Any

from aiowiserbyfeller import Device, Load
from aiowiserbyfeller.const import BUTTON_ON, EVENT_CLICK
from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DOMAIN
from .coordinator import WiserCoordinator
from .entity import WiserEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Wiser button entities."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []
    for load in coordinator.loads:
        load.raw_state = coordinator.states[load.id]
        device = coordinator.devices[load.device]
        room = coordinator.rooms[load.room] if load.room is not None else None
        entities.append(WiserPingEntity(coordinator, load, device, room))

        if await coordinator.async_is_onoff_impulse_load(load):
            entities.append(WiserImpulseEntity(coordinator, load, device, room))
        # else: see light.py

    for device in coordinator.devices.items():
        device = device[1]
        if len(device.outputs) > 0:
            continue

        entities.append(WiserPingEntity(coordinator, None, device, None))

    if entities:
        async_add_entities(entities)


class WiserPingEntity(WiserEntity, ButtonEntity):
    """Entity class for ping button entities.

    These allow a load or device to be pinged, resulting in a flashing button
    illumination on the targeted device. This helps to identify devices.
    """

    def __init__(
        self,
        coordinator: WiserCoordinator,
        load: Load | None,
        device: Device,
        room: dict | None,
    ) -> None:
        """Set up wiser ping button entity."""
        super().__init__(coordinator, load, device, room)
        self._attr_unique_id = f"{self._attr_raw_unique_id}_identify"
        self._attr_device_class = ButtonDeviceClass.IDENTIFY
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def translation_key(self):
        """Return the translation key to translate the entity's name and states."""
        return "identify"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""

    async def async_press(self, **kwargs: Any) -> None:
        """Ping the load or device to illuminate the button."""
        if self._load:
            await self._load.async_ping(10000, "ramp", "#1abcf2")
        else:
            await self.coordinator.async_ping_device(self._device.id)


class WiserImpulseEntity(WiserEntity, ButtonEntity):
    """Entity class for push button entities.

    These are OnOff loads that have been configured for impulse switching.
    """

    def __init__(
        self,
        coordinator: WiserCoordinator,
        load: Load,
        device: Device,
        room: dict | None,
    ) -> None:
        """Set up wiser impulse button entity."""
        super().__init__(coordinator, load, device, room)

    async def async_press(self, **kwargs: Any) -> None:
        """Simulate a button press of the physical device."""
        await self._load.async_ctrl(BUTTON_ON, EVENT_CLICK)
