"""Gemeinsame Basisklasse für alle ebusd-Direct-Entities."""
from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
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


class EbusdBaseEntity(CoordinatorEntity[EbusdCoordinator]):
    """Bindet eine Entity an einen Feld-Deskriptor + Coordinator."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: EbusdCoordinator, desc: FieldDesc) -> None:
        super().__init__(coordinator)
        self._desc = desc
        self._attr_name = desc.label
        self._attr_device_info = build_device_info(coordinator, desc.circuit)

    @property
    def _value(self) -> Any:
        return self.coordinator.data.get(self._desc.key)

    @property
    def available(self) -> bool:
        return super().available and self._value is not None
