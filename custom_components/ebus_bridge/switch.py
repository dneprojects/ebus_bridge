"""Switch-Plattform: schreibbare An/Aus-Felder (reine On/Off-Enums)."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import EbusdError
from .const import DOMAIN
from .coordinator import EbusdCoordinator
from .entity import EbusdBaseEntity
from .model import FieldDesc, bool_tokens, is_binary, value_is_on


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: EbusdCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        EbusdSwitch(coordinator, d)
        for d in coordinator.fields
        if d.writable
        and is_binary(d)
        and coordinator.included(d)
        and coordinator.data.get(d.key) is not None
    )


class EbusdSwitch(EbusdBaseEntity, SwitchEntity):
    def __init__(self, coordinator: EbusdCoordinator, desc: FieldDesc) -> None:
        super().__init__(coordinator, desc)
        self._attr_unique_id = f"{DOMAIN}_{desc.uid}_set"
        self._on_token, self._off_token = bool_tokens(desc)

    @property
    def is_on(self) -> bool | None:
        return value_is_on(self._value)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._write(self._on_token)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._write(self._off_token)

    async def _write(self, token: str) -> None:
        await self.coordinator.client.write(
            self._desc.circuit, self._desc.message, token
        )
        # Nach dem Schreiben frisch lesen (nicht gepollte Werte sonst leer).
        try:
            await self.coordinator.client.read(
                self._desc.circuit, self._desc.message
            )
        except EbusdError:
            pass
        await self.coordinator.async_request_refresh()
