"""Binary-Sensor-Plattform: nicht-schreibbare On/Off-Felder."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import EbusdCoordinator
from .entity import EbusdBaseEntity
from .model import FieldDesc, is_binary, value_is_on


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: EbusdCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        EbusdBinarySensor(coordinator, d)
        for d in coordinator.fields
        if not d.writable
        and is_binary(d)
        and coordinator.included(d)
        and coordinator.data.get(d.key) is not None
    )


class EbusdBinarySensor(EbusdBaseEntity, BinarySensorEntity):
    def __init__(self, coordinator: EbusdCoordinator, desc: FieldDesc) -> None:
        super().__init__(coordinator, desc)
        self._attr_unique_id = f"{DOMAIN}_{desc.uid}"

    @property
    def is_on(self) -> bool | None:
        return value_is_on(self._value)
