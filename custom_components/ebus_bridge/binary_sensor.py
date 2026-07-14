"""Binary-Sensor-Plattform: nicht-schreibbare On/Off-Felder + Bus-Signal."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

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
    if "signal" in coordinator.global_data:
        async_add_entities([EbusdSignalSensor(coordinator)])


class EbusdBinarySensor(EbusdBaseEntity, BinarySensorEntity):
    def __init__(self, coordinator: EbusdCoordinator, desc: FieldDesc) -> None:
        super().__init__(coordinator, desc)
        self._attr_unique_id = f"{DOMAIN}_{desc.uid}"

    @property
    def is_on(self) -> bool | None:
        return value_is_on(self._value)


class EbusdSignalSensor(CoordinatorEntity[EbusdCoordinator], BinarySensorEntity):
    """Bus-Signal des Adapters (globaler ebusd-Abschnitt), hängt an der Bridge."""

    _attr_has_entity_name = True
    _attr_name = "Signal"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: EbusdCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_{coordinator.entry_id}_global_signal"
        self._attr_device_info = DeviceInfo(identifiers={coordinator.bridge_id})

    @property
    def is_on(self) -> bool | None:
        value = self.coordinator.global_data.get("signal")
        return bool(value) if value is not None else None
