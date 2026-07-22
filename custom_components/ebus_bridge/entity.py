"""Gemeinsame Basisklasse für alle ebusd-Direct-Entities."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import EbusdCoordinator
from .model import FieldDesc

# Produktnamen für bekannte Vaillant-Scan-IDs. Bewusst OHNE die WP-Modelle
# (HMU00/V32): dort ist das gescannte Modell der Koppler bzw. wenig sprechend,
# der Nutzer-Kreis (wp0/wp1) ist aussagekräftiger.
_PRODUCT_NAMES = {
    "CTLV3": "sensoCOMFORT",
    "VR_71": "VR 71",
    "VR_70": "VR 70",
    "VR630": "VR 630",
}


def _device_name(circuit: str, model: str | None) -> str:
    if model and model in _PRODUCT_NAMES:
        return _PRODUCT_NAMES[model]
    return circuit.replace("_", " ").upper()  # "vr_71" -> "VR 71", "wp0" -> "WP0"


# Icon-Heuristik: EINHEIT zuerst. Temperaturen (°C/K) -> Thermometer-Variante je
# Kontext; sonst Gerätesymbol nach Namens-Stichwort, zuletzt Einheit.
_TEMP_UNITS = {"°C", "K"}

_NONTEMP_KEYWORD: list[tuple[str, str]] = [
    ("pump", "mdi:pump"),
    ("valve", "mdi:pipe-valve"),
    ("compressor", "mdi:heat-pump"),
    ("fan", "mdi:fan"),
    ("curve", "mdi:chart-bell-curve"),
    ("cool", "mdi:snowflake"),
    ("heat", "mdi:radiator"),
    ("mode", "mdi:tune-variant"),
    ("status", "mdi:information-outline"),
    ("pressure", "mdi:gauge"),
    ("energy", "mdi:lightning-bolt"),
    ("power", "mdi:flash"),
    ("time", "mdi:clock-outline"),
]
_ICON_BY_UNIT: dict[str, str] = {
    "%": "mdi:percent",
    "bar": "mdi:gauge",
    "kWh": "mdi:lightning-bolt",
    "Wh": "mdi:lightning-bolt",
    "kW": "mdi:flash",
    "W": "mdi:flash",
    "V": "mdi:flash-triangle",
    "A": "mdi:current-ac",
    "h": "mdi:clock-outline",
    "min": "mdi:clock-outline",
}


def _temp_icon(text: str, unit: str) -> str:
    if "cool" in text:
        return "mdi:snowflake-thermometer"
    if "room" in text:
        return "mdi:home-thermometer"
    if any(k in text for k in ("flow", "water", "dhw", "hwc", "cylinder")):
        return "mdi:thermometer-water"
    if any(k in text for k in ("outside", "outdoor", "ambient", "extern")):
        return "mdi:sun-thermometer"
    if unit == "K":
        return "mdi:thermometer-lines"
    return "mdi:thermometer"


def _icon_for(desc: FieldDesc) -> str | None:
    text = f"{desc.message} {desc.field}".lower()
    unit = desc.unit or ""
    if unit in _TEMP_UNITS:
        return _temp_icon(text, unit)
    for keyword, icon in _NONTEMP_KEYWORD:
        if keyword in text:
            return icon
    return _ICON_BY_UNIT.get(unit)


def build_device_info(coordinator: EbusdCoordinator, circuit: str) -> DeviceInfo:
    """Gerät je eBUS-Kreis – Klarname (kein „ebusd"), hängt als Kind an der Bridge."""
    meta = coordinator.device_meta.get(circuit, {})
    return DeviceInfo(
        identifiers={(DOMAIN, circuit)},
        name=_device_name(circuit, meta.get("model")),
        manufacturer=meta.get("manufacturer", "Vaillant"),
        model=meta.get("model"),
        sw_version=meta.get("sw"),
        hw_version=meta.get("hw"),
        via_device=coordinator.bridge_id,
    )


def add_fields_dynamically(
    coordinator: EbusdCoordinator,
    async_add_entities: AddEntitiesCallback,
    matches: Callable[[FieldDesc], bool],
    build: Callable[[FieldDesc], Any],
) -> Callable[[], None]:
    """Entities anlegen, sobald ein Feld erstmals einen Wert hat.

    ebusds Cache ist nach einem Neustart leer und füllt sich erst nach und nach.
    Würde man nur beim Setup prüfen, fehlte dauerhaft alles, was zu diesem
    Zeitpunkt noch keinen Wert hatte -- und der Nutzer müsste neu laden. Felder
    ohne Wert legen umgekehrt keine Karteileichen an (nicht bestückte Hardware).

    Rückgabe: Abmelde-Funktion für den Coordinator-Listener.
    """
    known: set[tuple[str, str, str]] = set()

    @callback
    def _sync() -> None:
        new = []
        for desc in coordinator.fields:
            if desc.key in known or not matches(desc):
                continue
            if coordinator.data.get(desc.key) is None:
                continue
            known.add(desc.key)
            new.append(build(desc))
        if new:
            async_add_entities(new)

    _sync()
    return coordinator.async_add_listener(_sync)


class EbusdBaseEntity(CoordinatorEntity[EbusdCoordinator]):
    """Bindet eine Entity an einen Feld-Deskriptor + Coordinator."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: EbusdCoordinator, desc: FieldDesc) -> None:
        super().__init__(coordinator)
        self._desc = desc
        self._attr_name = desc.label
        self._attr_icon = _icon_for(desc)
        self._attr_device_info = build_device_info(coordinator, desc.circuit)
        # Passiv mitgehörte Kommando-Felder (z. B. SetMode) sind Diagnose und
        # standardmäßig aus -- sonst fluten sie die Geräte. Der Nutzer aktiviert
        # gezielt, was er braucht (etwa releasebackup).
        if desc.passive and not desc.writable:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
            self._attr_entity_registry_enabled_default = False

    @property
    def _value(self) -> Any:
        return self.coordinator.data.get(self._desc.key)

    @property
    def available(self) -> bool:
        return super().available and self._value is not None
