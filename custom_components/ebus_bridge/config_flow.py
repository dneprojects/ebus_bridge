"""Config-Flow (Host + TCP/HTTP-Port) + Options-Flow (Poll-Intervall + Ausschluss)."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components import network
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import EbusdClient, EbusdError
from .const import (
    CONF_EXCLUDE,
    CONF_FAST,
    CONF_HOST,
    CONF_HTTP_PORT,
    CONF_POLL_PRIORITY,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    DEFAULT_EXCLUDE,
    DEFAULT_FAST,
    DEFAULT_HTTP_PORT,
    DEFAULT_POLL_PRIORITY,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)


class EbusdConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            client = EbusdClient(
                user_input[CONF_HOST],
                user_input[CONF_PORT],
                user_input[CONF_HTTP_PORT],
                async_get_clientsession(self.hass),
            )
            try:
                await client.test()
            except EbusdError:
                errors["base"] = "cannot_connect"

            if not errors:
                await self.async_set_unique_id(
                    f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}"
                )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input[CONF_HOST], data=user_input
                )

        # Host mit der HA-Host-IP vorbelegen (ebusd läuft i. d. R. lokal als Add-on).
        if user_input and user_input.get(CONF_HOST):
            default_host = user_input[CONF_HOST]
        else:
            try:
                default_host = await network.async_get_source_ip(
                    self.hass, target=network.MDNS_TARGET_IP
                )
            except HomeAssistantError:
                default_host = ""

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=default_host): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
                vol.Required(CONF_HTTP_PORT, default=DEFAULT_HTTP_PORT): int,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return EbusdOptionsFlow(config_entry)


class EbusdOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry) -> None:
        self._entry = config_entry

    async def async_step_init(self, user_input: dict | None = None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        opts = self._entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=opts.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): int,
                vol.Optional(
                    CONF_EXCLUDE,
                    default=opts.get(CONF_EXCLUDE, DEFAULT_EXCLUDE),
                ): str,
                vol.Optional(
                    CONF_FAST,
                    default=opts.get(CONF_FAST, DEFAULT_FAST),
                ): str,
                vol.Optional(
                    CONF_POLL_PRIORITY,
                    default=opts.get(CONF_POLL_PRIORITY, DEFAULT_POLL_PRIORITY),
                ): vol.All(int, vol.Range(min=0, max=9)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
