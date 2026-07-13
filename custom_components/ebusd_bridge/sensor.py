"""Sensor-Plattform: lesbare Felder (nicht schreibbar), je Feld eine Entity."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import EbusdCoordinator
from .entity import EbusdBaseEntity
from .model import FieldDesc, is_binary


def _classes(desc: FieldDesc):
    """device_class + state_class aus der Einheit (fehlerfrei kombiniert)."""
    unit = desc.unit
    if unit == "°C":
        return SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT
    if unit in ("kW", "W"):
        return SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT
    if unit == "kWh":
        return SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING
    if unit == "bar":
        return SensorDeviceClass.PRESSURE, SensorStateClass.MEASUREMENT
    if unit == "%":
        return None, SensorStateClass.MEASUREMENT
    if desc.numeric:
        return None, SensorStateClass.MEASUREMENT
    return None, None


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: EbusdCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        EbusdSensor(coordinator, d)
        for d in coordinator.fields
        if not d.writable
        and not is_binary(d)
        and coordinator.included(d)
        and coordinator.data.get(d.key) is not None
    )


class EbusdSensor(EbusdBaseEntity, SensorEntity):
    def __init__(self, coordinator: EbusdCoordinator, desc: FieldDesc) -> None:
        super().__init__(coordinator, desc)
        self._attr_unique_id = f"{DOMAIN}_{desc.uid}"
        if desc.unit:
            self._attr_native_unit_of_measurement = desc.unit
        self._attr_device_class, self._attr_state_class = _classes(desc)

    @property
    def native_value(self):
        value = self._value
        if value is None:
            return None
        if self._desc.numeric:
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
        return value  # Enum-/Text-Wert (z. B. "auto", "off")
