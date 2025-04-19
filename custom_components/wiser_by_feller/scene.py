"""Platform for scene integration."""

from __future__ import annotations

import logging
from typing import Any

from aiowiserbyfeller import Scene

from homeassistant.components.scene import Scene as HaScene
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DOMAIN
from .coordinator import WiserCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []

    for scene in coordinator.scenes.items():
        scene = scene[1]

        if scene.job not in coordinator.jobs:
            continue

        entities.append(WiserSceneEntity(coordinator, scene))

    if entities:
        async_add_entities(entities)


class WiserSceneEntity(HaScene):
    """Entity class for scenes."""

    def __init__(
        self,
        coordinator: WiserCoordinator,
        scene: Scene,
    ) -> None:
        self.coordinator = coordinator
        self._attr_has_entity_name = True
        self._attr_unique_id = f"scene_{scene.id}"
        self._attr_name = scene.name
        self._scene = scene

    async def async_activate(self, **kwargs: Any) -> None:
        """Trigger Wiser scene."""
        job = self.coordinator.jobs[self._scene.job]
        await job.async_trigger_all()
