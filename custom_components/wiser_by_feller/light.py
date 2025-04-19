"""Platform for light integration."""

from __future__ import annotations

import logging
from typing import Any

from aiowiserbyfeller import (
    KIND_LIGHT,
    KIND_SWITCH,
    DaliRgbw,
    DaliTw,
    Device,
    Dim,
    Load,
    OnOff,
)

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DOMAIN
from .coordinator import WiserCoordinator
from .entity import WiserEntity
from .util import brightness_to_wiser, wiser_to_brightness

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []
    for load in coordinator.loads:
        load.raw_state = coordinator.states[load.id]
        device = coordinator.devices[load.device]
        room = coordinator.rooms[load.room] if load.room is not None else None

        if isinstance(load, OnOff) and load.kind == KIND_SWITCH:
            entities.append(WiserOnOffSwitchEntity(coordinator, load, device, room))
        elif isinstance(load, OnOff):
            entities.append(WiserOnOffEntity(coordinator, load, device, room))
        # elif (isinstance(load, DaliTw)):
        #     entities.append(WiserDimTwEntity(coordinator, load, device, room))
        # elif (isinstance(load, DaliRgbw)):
        #     entities.append(WiserDimRgbEntity(coordinator, load, device, room))
        elif isinstance(load, Dim):  # Includes Dali
            entities.append(WiserDimEntity(coordinator, load, device, room))

    if entities:
        async_add_entities(entities)


class WiserOnOffEntity(WiserEntity, LightEntity):
    """Entity class for simple non-dimmable lights."""

    def __init__(
        self, coordinator: WiserCoordinator, load: Load, device: Device, room: dict
    ) -> None:
        super().__init__(coordinator, load, device, room)
        self._attr_name = None
        self._brightness = None
        self._attr_color_mode = ColorMode.ONOFF
        self._attr_supported_color_modes = [ColorMode.ONOFF]

    @property
    def is_on(self) -> bool | None:
        return self._load.state

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._load.async_control_on()
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._load.async_control_off()
        await self.coordinator.async_request_refresh()


class WiserOnOffSwitchEntity(WiserEntity, SwitchEntity):
    """Entity class for simple non-dimmable switches."""

    def __init__(
        self, coordinator: WiserCoordinator, load: Load, device: Device, room: dict
    ) -> None:
        super().__init__(coordinator, load, device, room)
        self._attr_name = None
        self._brightness = None

    @property
    def is_on(self) -> bool | None:
        return self._load.state

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._load.async_control_on()
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._load.async_control_off()
        await self.coordinator.async_request_refresh()


class WiserDimEntity(WiserEntity, LightEntity):
    """Entity class for simple dimmable lights."""

    def __init__(
        self, coordinator: WiserCoordinator, load: Load, device: Device, room: dict
    ) -> None:
        super().__init__(coordinator, load, device, room)
        self._attr_name = None
        self._attr_color_mode = ColorMode.BRIGHTNESS
        self._attr_supported_color_modes = [ColorMode.BRIGHTNESS]

    @property
    def is_on(self) -> bool | None:
        """Return True if entity is on."""
        return self._load.raw_state["bri"] > 0

    @property
    def brightness(self):
        """Return the brightness of this light between 0..255."""
        return wiser_to_brightness(self._load.raw_state["bri"])

    async def async_turn_on(self, **kwargs: Any) -> None:
        bri = brightness_to_wiser(kwargs.get(ATTR_BRIGHTNESS, 255))
        await self._load.async_set_target_state({"bri": bri})
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._load.async_set_target_state({"bri": 0})
        await self.coordinator.async_request_refresh()

    # TODO: Turning off and getting off state does not work.
    # TODO: Control all lights together
