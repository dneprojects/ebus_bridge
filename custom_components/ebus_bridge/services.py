"""Services für eBUS Bridge: generischer Schreibzugriff auf ebusd.

`ebus_bridge.write` reicht einen Wert direkt an ebusds `write`-Kommando durch –
universell, ohne eigene Definitionen. Mehrfeld-Werte mit `;` trennen
(z. B. `0;3;06:00;22:00;20.0`). Nach dem Schreiben wird frisch gelesen und der
aktuelle Wert der Nachricht als Response zurückgegeben.
"""
from __future__ import annotations

import voluptuous as vol
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
import homeassistant.helpers.config_validation as cv

from .client import EbusdError
from .const import DOMAIN
from .coordinator import EbusdCoordinator

SERVICE_WRITE = "write"

WRITE_SCHEMA = vol.Schema(
    {
        vol.Required("circuit"): cv.string,
        vol.Required("message"): cv.string,
        vol.Required("value"): vol.Coerce(str),
        vol.Optional("entry_id"): cv.string,
    }
)


def _get_coordinator(hass: HomeAssistant, entry_id: str | None) -> EbusdCoordinator:
    data: dict[str, EbusdCoordinator] = hass.data.get(DOMAIN, {})
    if not data:
        raise ServiceValidationError("eBUS Bridge ist nicht eingerichtet.")
    if entry_id:
        if entry_id not in data:
            raise ServiceValidationError(f"Unbekannte entry_id: {entry_id}")
        return data[entry_id]
    if len(data) == 1:
        return next(iter(data.values()))
    raise ServiceValidationError(
        "Mehrere eBUS-Bridge-Instanzen – bitte entry_id angeben."
    )


async def async_setup_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_WRITE):
        return

    async def _handle_write(call: ServiceCall) -> ServiceResponse:
        coordinator = _get_coordinator(hass, call.data.get("entry_id"))
        circuit = call.data["circuit"]
        message = call.data["message"]
        value = call.data["value"]
        try:
            await coordinator.client.write(circuit, message, value)
        except EbusdError as err:
            raise HomeAssistantError(f"ebusd write fehlgeschlagen: {err}") from err
        # Best-effort frischer Read, damit /data den neuen Wert zeigt.
        try:
            await coordinator.client.read(circuit, message)
        except EbusdError:
            pass
        await coordinator.async_request_refresh()
        values = {
            field: val
            for (c, m, field), val in coordinator.data.items()
            if c == circuit and m == message
        }
        return {"written": value, "values": values}

    hass.services.async_register(
        DOMAIN,
        SERVICE_WRITE,
        _handle_write,
        schema=WRITE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )


def async_unload_services(hass: HomeAssistant) -> None:
    """Service entfernen, wenn keine Instanz mehr geladen ist."""
    if not hass.data.get(DOMAIN):
        hass.services.async_remove(DOMAIN, SERVICE_WRITE)
