"""Sensor-Plattform: lesbare Felder (nicht schreibbar), je Feld eine Entity."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
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
from .model import FieldDesc, is_binary

# Bridge-Diagnose aus dem globalen ebusd-Abschnitt.
# (key, Name, Einheit, Icon, state_class, standardmäßig aktiviert)
_M = SensorStateClass.MEASUREMENT
_GLOBAL_SENSORS: list[tuple] = [
    ("symbolrate", "Symbolrate", "Sym/s", "mdi:speedometer", _M, True),
    ("maxsymbolrate", "Max. Symbolrate", "Sym/s", "mdi:speedometer-medium", _M, True),
    ("reconnects", "Reconnects", None, "mdi:connection", SensorStateClass.TOTAL_INCREASING, True),
    ("masters", "Master am Bus", None, "mdi:sitemap-outline", _M, True),
    ("qq", "ebusd-Adresse (QQ)", None, "mdi:identifier", None, True),
    ("messages", "Bekannte Nachrichten", None, "mdi:message-text-outline", _M, True),
    # Enhanced-Timing – Diagnose, standardmäßig deaktiviert
    ("minarbitrationmicros", "Arbitrierung min", "µs", "mdi:timer-outline", _M, False),
    ("maxarbitrationmicros", "Arbitrierung max", "µs", "mdi:timer-outline", _M, False),
    ("minsymbollatency", "Symbol-Latenz min", None, "mdi:timer-sand", _M, False),
    ("maxsymbollatency", "Symbol-Latenz max", None, "mdi:timer-sand", _M, False),
]


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
    async_add_entities(
        EbusdGlobalSensor(coordinator, *spec)
        for spec in _GLOBAL_SENSORS
        if spec[0] in coordinator.global_data
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


class EbusdGlobalSensor(CoordinatorEntity[EbusdCoordinator], SensorEntity):
    """Bus-/Adapter-Diagnose (globaler ebusd-Abschnitt), hängt an der Bridge."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: EbusdCoordinator,
        key: str,
        name: str,
        unit: str | None,
        icon: str,
        state_class: SensorStateClass | None,
        enabled: bool,
    ) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_name = name
        self._attr_native_unit_of_measurement = unit
        self._attr_icon = icon
        self._attr_state_class = state_class
        self._attr_entity_registry_enabled_default = enabled
        self._attr_unique_id = f"{DOMAIN}_{coordinator.entry_id}_global_{key}"
        self._attr_device_info = DeviceInfo(identifiers={coordinator.bridge_id})

    @property
    def native_value(self):
        return self.coordinator.global_data.get(self._key)
