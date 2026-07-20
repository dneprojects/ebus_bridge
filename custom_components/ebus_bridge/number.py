"""Number-Plattform: schreibbare numerische Felder (Sollwerte)."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import EbusdError
from .const import DOMAIN
from .coordinator import EbusdCoordinator
from .entity import EbusdBaseEntity, add_fields_dynamically
from .model import FieldDesc


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: EbusdCoordinator = hass.data[DOMAIN][entry.entry_id]
    entry.async_on_unload(
        add_fields_dynamically(
            coordinator,
            async_add_entities,
            lambda d: d.writable and d.numeric and coordinator.included(d),
            lambda d: EbusdNumber(coordinator, d),
        )
    )


class EbusdNumber(EbusdBaseEntity, NumberEntity):
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: EbusdCoordinator, desc: FieldDesc) -> None:
        super().__init__(coordinator, desc)
        self._attr_unique_id = f"{DOMAIN}_{desc.uid}_set"
        if desc.unit:
            self._attr_native_unit_of_measurement = desc.unit
        if desc.min_value is not None:
            self._attr_native_min_value = desc.min_value
        if desc.max_value is not None:
            self._attr_native_max_value = desc.max_value
        if desc.step is not None:
            self._attr_native_step = desc.step

    @property
    def native_value(self) -> float | None:
        value = self._value
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    async def async_set_native_value(self, value: float) -> None:
        out: object = int(value) if float(value).is_integer() else value
        await self.coordinator.client.write(
            self._desc.circuit, self._desc.message, out
        )
        # Nach dem Schreiben frisch lesen, sonst bleibt der (nicht gepollte)
        # Sollwert in /data leer -> Entity würde "nicht verfügbar".
        try:
            await self.coordinator.client.read(
                self._desc.circuit, self._desc.message
            )
        except EbusdError:
            pass
        await self.coordinator.async_request_refresh()
