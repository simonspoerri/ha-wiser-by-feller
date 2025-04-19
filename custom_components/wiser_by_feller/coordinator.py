"""Coordinator for Wiser by Feller integration."""

from __future__ import annotations

from datetime import timedelta
import logging
import time
from typing import Any

from aiowiserbyfeller import (
    AuthorizationFailed,
    Device,
    Job,
    Load,
    Scene,
    UnsuccessfulRequest,
    Websocket,
    WiserByFellerAPI,
)
from aiowiserbyfeller.util import parse_wiser_device_ref_c
import async_timeout
import websockets.client

from homeassistant.core import ServiceCall, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .util import rgb_tuple_to_hex

_LOGGER = logging.getLogger(__name__)


class WiserCoordinator(DataUpdateCoordinator):
    """Class for coordinating all Wiser devices / entities."""

    def __init__(self, hass, api: WiserByFellerAPI, host: str, token: str):
        """Initialize global data updater."""
        super().__init__(
            hass,
            _LOGGER,
            name="WiserLightCoordinator",
            update_interval=timedelta(seconds=30),
        )
        self._hass = hass
        self._api = api
        self._loads = None
        self._states = None
        self._devices = None
        self._device_ids_by_serial = None
        self._scenes = None
        self._jobs = None
        self._rooms = None
        self._rssi = None
        self._gateway = None
        self._ws = Websocket(host, token, _LOGGER)

    @property
    def loads(self) -> list[Load] | None:
        return self._loads

    @property
    def states(self) -> list[dict] | None:
        return self._states

    @property
    def devices(self) -> list[dict] | None:
        return self._devices

    @property
    def scenes(self) -> list[Scene] | None:
        return self._scenes

    @property
    def jobs(self) -> list[Job] | None:
        return self._jobs

    @property
    def gateway(self) -> Device | None:
        return self._gateway

    @property
    def rooms(self) -> list[dict] | None:
        return self._rooms

    @property
    def rssi(self) -> int | None:
        return self._rssi

    @callback
    async def async_set_status_light(self, call: ServiceCall) -> None:
        channel = call.data["channel"]
        device_id = call.data["device"]
        registry = dr.async_get(self.hass)
        device = registry.async_get(device_id)
        sn = device.serial_number

        if sn not in self._device_ids_by_serial:
            raise Exception(
                f"Device {device_id} not found!"
            )  # TODO more fitting exception + logging

        wdevice = self._device_ids_by_serial[sn]

        if channel >= len(self._devices[wdevice].inputs):
            raise Exception(
                f"Device {device_id} does not have channel {channel}"
            )  # TODO more fitting exception + logging

        data = {
            "color": rgb_tuple_to_hex(tuple(call.data["color"])),
            "foreground_bri": call.data["brightness_on"],
            "background_bri": call.data["brightness_off"]
            if "brightness_off" in call.data
            else call.data["brightness_on"],
        }

        # TODO: Error Handling
        # TODO: It appears the very first time it does not set the configuration
        config = await self._api.async_get_device_config(wdevice)
        await self._api.async_set_device_input_config(config["id"], channel, data)
        await self._api.async_apply_device_config(config["id"])

        return True

    async def _async_update_data(self):
        """Fetch data from API endpoint.

        This is the place to pre-process the data to lookup tables
        so entities can quickly look up their data.
        """
        try:
            # Note: asyncio.TimeoutError and aiohttp.ClientError are already
            # handled by the data update coordinator.
            async with async_timeout.timeout(10):
                if self._loads is None:
                    await self.async_update_loads()

                if self._rooms is None:
                    await self.async_update_rooms()

                if self._devices is None:
                    await self.async_update_devices()

                if self._jobs is None:
                    await self.async_update_jobs()

                if self._scenes is None:
                    await self.async_update_scenes()

                await self.async_update_states()
                await self.async_update_rssi()
        except AuthorizationFailed as err:
            # Raising ConfigEntryAuthFailed will cancel future updates
            # and start a config flow with SOURCE_REAUTH (async_step_reauth)
            raise ConfigEntryAuthFailed from err
        except UnsuccessfulRequest as err:
            raise UpdateFailed(f"Error communicating with API: {err}")

    def ws_init(self):
        self._ws.subscribe(self.ws_update_load)
        self._ws.init()
        # TODO: Check connection / reconnect -> Watchdog

    def ws_update_load(self, data: dict):
        if self._states is None:
            return  # State is not ready yet.

        if "load" not in data:
            raise Exception("Received unexpected data from webservice")

        load = data["load"]
        self._states[load["id"]] = load["state"]
        self.logger.info(f"Load {load['id']}: {load['state']}")  # TODO: Remove debug
        self.async_set_updated_data(None)

    async def async_update_loads(self):
        self._loads = await self._api.async_get_loads()

    async def async_update_devices(self):
        result = {}
        serials = {}

        for device in await self._api.async_get_devices_detail():
            result[device.id] = device
            serials[device.combined_serial_number] = device.id
            info = parse_wiser_device_ref_c(device.c["comm_ref"])
            if info["wlan"]:
                self._gateway = device

        self._devices = result
        self._device_ids_by_serial = serials

    async def async_update_rooms(self):
        result = {}

        for room in await self._api.async_get_rooms():
            result[room["id"]] = room

        self._rooms = result

    async def async_update_states(self):
        result = {}

        for load in await self._api.async_get_loads_state():
            result[load["id"]] = load["state"]

        self._states = result

    async def async_update_jobs(self):
        result = {}

        for job in await self._api.async_get_jobs():
            result[job.id] = job

        self._jobs = result

    async def async_update_scenes(self):
        result = {}

        for scene in await self._api.async_get_scenes():
            result[scene.id] = scene

        self._scenes = result

    async def async_update_rssi(self):
        self._rssi = await self._api.async_get_net_rssi()

    # TODO: use async_get_system_health and add uptime, sockets, reboot_cause (?), mem_{size,free} (?), flash_{size,free} (?), wlan_resets
