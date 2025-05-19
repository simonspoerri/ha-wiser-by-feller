"""Config flow for Wiser by Feller integration."""

from __future__ import annotations

import logging
from typing import Any

from aiohttp.client_exceptions import ClientError
from aiowiserbyfeller import (
    Auth,
    AuthorizationFailed,
    UnauthorizedUser,
    WiserByFellerAPI,
)
from homeassistant import config_entries
from homeassistant.components import dhcp
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import AbortFlow
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
import voluptuous as vol

from .const import (
    CONF_IMPORTUSER,
    DEFAULT_API_USER,
    DEFAULT_IMPORT_USER,
    DOMAIN,
    OPTIONS_ALLOW_MISSING_GATEWAY_DATA,
)
from .exceptions import CannotConnect, InvalidAuth

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Required(CONF_USERNAME, default=DEFAULT_API_USER): cv.string,
        vol.Required(CONF_IMPORTUSER, default=DEFAULT_IMPORT_USER): cv.string,
    }
)

OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(OPTIONS_ALLOW_MISSING_GATEWAY_DATA, default=False): bool,
    }
)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Wiser by Feller."""

    VERSION = 1
    MINOR_VERSION = 1

    _reauth_entry: list[str, Any]
    _reauth_entry_data: list[str, Any]
    _discovered_host: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await self.validate_input(self.hass, user_input)
                await self.async_set_unique_id(info["sn"])
            except CannotConnect:
                errors["base"] = "cannot_connect"  # TODO: errors are not translated
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except AbortFlow as e:
                raise e
            except Exception as e:  # pylint: disable=broad-except
                _LOGGER.exception(f"Unexpected exception: {e}")
                errors["base"] = str(e)
            else:
                return self.async_create_entry(title=info["title"], data=info)

        # Dynamically set the default value for CONF_HOST
        step_user_data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_HOST, default=self._discovered_host or vol.UNDEFINED
                ): cv.string,
                vol.Required(CONF_USERNAME, default=DEFAULT_API_USER): cv.string,
                vol.Required(CONF_IMPORTUSER, default=DEFAULT_IMPORT_USER): cv.string,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=step_user_data_schema,
            errors=errors,
        )

    async def async_step_dhcp(
        self, discovery_info: dhcp.DhcpServiceInfo
    ) -> ConfigFlowResult:
        """Handle a flow initialized by discovery."""
        try:
            session = async_get_clientsession(self.hass)
            auth = Auth(session, discovery_info.ip)
            api = WiserByFellerAPI(auth)
            info = await api.async_get_info()
        except Exception:  # pylint: disable=broad-except
            return self.async_abort(reason="not_wiser_gateway")

        await self.async_set_unique_id(info["sn"])
        self._abort_if_unique_id_configured({CONF_HOST: discovery_info.ip})
        self._async_abort_entries_match({CONF_HOST: discovery_info.ip})

        self._discovered_host = discovery_info.ip

        return await self.async_step_user()

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Handle a flow initialized by discovery (mdns)."""

        try:
            host = discovery_info.host
            session = async_get_clientsession(self.hass)
            auth = Auth(session, host)
            api = WiserByFellerAPI(auth)
            info = await api.async_get_info()
        except Exception:  # pylint: disable=broad-except
            return self.async_abort(reason="not_wiser_gateway")

        await self.async_set_unique_id(info["sn"])
        self._abort_if_unique_id_configured({CONF_HOST: host})
        self._async_abort_entries_match({CONF_HOST: host})

        self._discovered_host = host

        return await self.async_step_user()

    async def validate_input(
        self,
        hass: HomeAssistant,
        user_input: dict[str, Any],
        allow_existing: bool = False,
    ) -> dict[str, Any]:
        """Validate user input for µGateway setup."""
        session = async_get_clientsession(hass)
        auth = Auth(session, user_input[CONF_HOST])
        api = WiserByFellerAPI(auth)
        info = await api.async_get_info()

        await self.async_set_unique_id(info["sn"])
        if not allow_existing:
            self._abort_if_unique_id_configured({CONF_HOST: user_input[CONF_HOST]})
            self._async_abort_entries_match({CONF_HOST: user_input[CONF_HOST]})

        try:
            token = await auth.claim(
                user_input[CONF_USERNAME], user_input[CONF_IMPORTUSER]
            )
        except (AuthorizationFailed, ClientError) as err:
            raise CannotConnect from err

        net_state = await api.async_get_net_state()

        return {
            "title": net_state["hostname"],
            "token": token,
            "sn": info["sn"],
            "host": user_input[CONF_HOST],
            "username": user_input[CONF_USERNAME],
        }

    async def async_step_reauth(self, entry_data: list[str, Any]) -> ConfigFlowResult:
        """Handle configuration by re-auth."""
        self._reauth_entry_data = entry_data
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reauthentication with new credentials."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await self.validate_input(self.hass, user_input, True)
                await self.async_set_unique_id(info["sn"])
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except (InvalidAuth, UnauthorizedUser):
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                self.hass.config_entries.async_update_entry(
                    self._reauth_entry,
                    data=info,
                )
                await self.hass.config_entries.async_reload(self._reauth_entry_id)

                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_HOST, default=self._reauth_entry_data.get(CONF_HOST)
                    ): str,
                    vol.Required(
                        CONF_USERNAME,
                        default=self._reauth_entry_data.get(
                            CONF_USERNAME, DEFAULT_API_USER
                        ),
                    ): str,
                    vol.Required(CONF_IMPORTUSER, default=DEFAULT_IMPORT_USER): str,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OptionsFlowHandler()


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handles options flow for the component."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA, self.config_entry.options
            ),
        )
