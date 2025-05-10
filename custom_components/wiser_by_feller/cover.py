"""Platform for cover integration."""

from __future__ import annotations

import logging
import sched
import time

from aiowiserbyfeller import Device, Load, Motor
from aiowiserbyfeller.const import KIND_AWNING, KIND_VENETIAN_BLINDS

from homeassistant.components.cover import (
    ATTR_POSITION,
    ATTR_TILT_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DOMAIN
from .coordinator import WiserCoordinator
from .entity import WiserEntity
from .util import (
    cover_position_to_wiser,
    cover_tilt_to_wiser,
    wiser_to_cover_position,
    wiser_to_cover_tilt,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Wiser cover entities."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []
    for load in coordinator.loads:
        load.raw_state = coordinator.states[load.id]
        device = coordinator.devices[load.device]
        room = coordinator.rooms[load.room] if load.room is not None else None

        if isinstance(load, Motor) and load.sub_type == "relay":
            entities.append(WiserRelayEntity(coordinator, load, device, room))
        elif isinstance(load, Motor) and load.kind == KIND_VENETIAN_BLINDS:
            entities.append(WiserTiltableCoverEntity(coordinator, load, device, room))
        elif isinstance(load, Motor):
            entities.append(WiserCoverEntity(coordinator, load, device, room))

    if entities:
        async_add_entities(entities)


class WiserRelayEntity(WiserEntity, CoverEntity):
    """Wiser entity class for basic motor entities."""

    def __init__(
        self, coordinator: WiserCoordinator, load: Load, device: Device, room: dict
    ) -> None:
        """Set up the relay entity."""
        super().__init__(coordinator, load, device, room)

        self._attr_name = None
        self._attr_supported_features = (
            CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
        )

        # There is no suitable default for "motor", so we use shade.
        self._attr_device_class = CoverDeviceClass.SHADE
        self._scheduler = sched.scheduler(time.time, time.sleep)
        self._scheduler_id = None

    @property
    def is_closed(self) -> bool:
        """Return if the cover is closed or not."""
        return self._load.state["level"] == 10000

    @property
    def is_opening(self) -> bool:
        """Return if the cover is opening or not."""
        return "moving" in self._load.state and self._load.state["moving"] == "up"

    @property
    def is_closing(self) -> bool:
        """Return if the cover is closing or not."""
        return "moving" in self._load.state and self._load.state["moving"] == "down"

    async def async_stop_cover(self, **kwargs):
        """Stop the cover."""
        await self._load.async_stop()

    async def async_open_cover(self, **kwargs):
        """Open the cover."""
        await self._load.async_set_level(0)
        self.start_tracking()

    async def async_close_cover(self, **kwargs):
        """Close cover."""
        await self._load.async_set_level(10000)
        self.start_tracking()

    def start_tracking(self):
        """Keep track of cover movement while moving."""
        if self._scheduler_id is not None:
            _LOGGER.info(f"Cancelling scheduler {self._scheduler_id}")
            self._scheduler.cancel(self._scheduler_id)
            self._scheduler_id = None

        self._scheduler_id = self._scheduler.enter(
            1, 1, self.async_keep_track, (self._scheduler,)
        )

        self._scheduler.run()

    def async_keep_track(self, scheduler):
        """Update load data and stop tracking if not moving anymore."""
        _LOGGER.debug("Updating load #%s while moving", self._load.id)
        self._load.async_refresh_state()
        if self.is_closing or self.is_opening:
            self.start_tracking()


class WiserCoverEntity(WiserRelayEntity, CoverEntity):
    """Wiser entity class for non-tiltable covers like shades and awnings."""

    def __init__(
        self, coordinator: WiserCoordinator, load: Load, device: Device, room: dict
    ) -> None:
        """Set up Wiser cover entity."""
        super().__init__(coordinator, load, device, room)

        self._attr_supported_features = (
            CoverEntityFeature.OPEN
            | CoverEntityFeature.CLOSE
            | CoverEntityFeature.STOP
            | CoverEntityFeature.SET_POSITION
        )

        # There is no suitable default for "motor", so we use shade.
        self._attr_device_class = (
            CoverDeviceClass.AWNING
            if load.kind == KIND_AWNING
            else CoverDeviceClass.SHADE
        )

    @property
    def current_cover_position(self) -> int | None:
        """Return current position of cover. None is unknown, 0 is closed, 100 is fully open."""
        if self._load.state is None:
            return None

        return wiser_to_cover_position(self._load.state["level"])

    async def async_set_cover_position(self, **kwargs):
        """Move the cover to a specific position."""
        level = cover_position_to_wiser(kwargs.get(ATTR_POSITION))
        await self._load.async_set_level(level)
        self.start_tracking()

    async def async_stop_cover(self, **kwargs):
        """Stop the cover."""
        await self._load.async_set_stop()
        self.start_tracking()


class WiserTiltableCoverEntity(WiserCoverEntity, CoverEntity):
    """Wiser entity class for tiltable covers like venetian blinds."""

    def __init__(
        self, coordinator: WiserCoordinator, load: Load, device: Device, room: dict
    ) -> None:
        """Set up Wiser tiltable cover entity."""
        super().__init__(coordinator, load, device, room)

        self._attr_supported_features = (
            CoverEntityFeature.OPEN
            | CoverEntityFeature.CLOSE
            | CoverEntityFeature.STOP
            | CoverEntityFeature.SET_POSITION
            | CoverEntityFeature.OPEN_TILT
            | CoverEntityFeature.CLOSE_TILT
            | CoverEntityFeature.STOP_TILT
            | CoverEntityFeature.SET_TILT_POSITION
        )

        self._attr_device_class = CoverDeviceClass.BLIND

    @property
    def is_closed(self) -> bool | None:
        """Return if the cover is closed."""
        if (
            self.current_cover_position is None
            or self.current_cover_tilt_position is None
        ):
            return None

        return (
            self.current_cover_position == 0 and self.current_cover_tilt_position == 0
        )

    @property
    def current_cover_tilt_position(self) -> int | None:
        """Return current position of cover tilt. None is unknown, 0 is closed, 100 is fully open."""
        return wiser_to_cover_tilt(self._load.state["tilt"])

    async def async_open_cover_tilt(self, **kwargs):
        """Open the cover tilt."""

    async def async_close_cover_tilt(self, **kwargs):
        """Close the cover tilt."""

    async def async_set_cover_tilt_position(self, **kwargs):
        """Move the cover tilt to a specific position."""
        tilt = cover_tilt_to_wiser(kwargs.get(ATTR_TILT_POSITION))
        await self._load.async_set_tilt(tilt)

    async def async_stop_cover_tilt(self, **kwargs):
        """Stop the cover."""
        await self._load.async_stop()
