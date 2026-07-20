"""Select-Plattform: schreibbare Enum-Felder (Betriebsarten o. ä.)."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import EbusdError
from .const import DOMAIN
from .coordinator import EbusdCoordinator
from .entity import EbusdBaseEntity, add_fields_dynamically
from .model import FieldDesc, is_binary


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: EbusdCoordinator = hass.data[DOMAIN][entry.entry_id]
    entry.async_on_unload(
        add_fields_dynamically(
            coordinator,
            async_add_entities,
            lambda d: (
                d.writable
                and d.values
                and not is_binary(d)  # reine An/Aus -> switch
                and coordinator.included(d)
            ),
            lambda d: EbusdSelect(coordinator, d),
        )
    )


class EbusdSelect(EbusdBaseEntity, SelectEntity):
    def __init__(self, coordinator: EbusdCoordinator, desc: FieldDesc) -> None:
        super().__init__(coordinator, desc)
        self._attr_unique_id = f"{DOMAIN}_{desc.uid}_set"
        # Optionen aus der Enum-Map (Reihenfolge erhalten, dedupliziert)
        self._attr_options = list(dict.fromkeys((desc.values or {}).values()))

    @property
    def current_option(self) -> str | None:
        value = self._value
        if value is None:
            return None
        if value in (self._attr_options or []):
            return value
        # falls ebusd numerisch liefert -> über die Map auf den Namen abbilden
        return (self._desc.values or {}).get(str(value))

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.client.write(
            self._desc.circuit, self._desc.message, option
        )
        try:
            await self.coordinator.client.read(
                self._desc.circuit, self._desc.message
            )
        except EbusdError:
            pass
        await self.coordinator.async_request_refresh()
