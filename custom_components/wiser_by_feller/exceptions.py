"""Exceptions for the Wiser By Feller integration."""

from homeassistant.exceptions import HomeAssistantError, IntegrationError


class InvalidEntitySpecified(IntegrationError):
    """When an action is performed on a non-existing device."""


class InvalidEntityChannelSpecified(IntegrationError):
    """When an action is performed on a non-existing device channel."""


class UnexpectedGatewayResult(IntegrationError):
    """When invalid or unexpected data is returned by the µGateway API."""


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
