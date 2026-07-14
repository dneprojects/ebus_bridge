"""Water-heater-Plattform: Warmwasser (Hwc) als echte HA-water_heater-Entity.

Kuratierter Vaillant-Overlay: erkennt die sensoCOMFORT-WW-Register
(`HwcTempDesired` / `HwcStorageTemp` / `HwcOpMode`) und bildet daraus ein
water_heater ab. Fehlen die Nachrichten (Nicht-Vaillant), entsteht kein Gerät.
Die rohen Einzel-Entitäten bleiben zusätzlich bestehen.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.water_heater import (
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client import EbusdError
from .const import DOMAIN
from .coordinator import EbusdCoordinator
from .entity import build_device_info
from .model import FieldDesc

_TARGET = "HwcTempDesired"
_CURRENT = "HwcStorageTemp"
_OPMODE = "HwcOpMode"


def _find(fields: list[FieldDesc], circuit: str, message: str) -> FieldDesc | None:
    for d in fields:
        if d.circuit == circuit and d.message == message:
            return d
    return None


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: EbusdCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for circuit in {d.circuit for d in coordinator.fields}:
        target = _find(coordinator.fields, circuit, _TARGET)
        if target is None or not target.writable:
            continue  # ohne schreibbaren Sollwert kein sinnvolles water_heater
        entities.append(
            EbusdWaterHeater(
                coordinator,
                circuit,
                target,
                _find(coordinator.fields, circuit, _CURRENT),
                _find(coordinator.fields, circuit, _OPMODE),
            )
        )
    async_add_entities(entities)


class EbusdWaterHeater(CoordinatorEntity[EbusdCoordinator], WaterHeaterEntity):
    _attr_has_entity_name = True
    _attr_name = "Warmwasser"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_min_temp = 35
    _attr_max_temp = 70

    def __init__(
        self,
        coordinator: EbusdCoordinator,
        circuit: str,
        target: FieldDesc,
        current: FieldDesc | None,
        opmode: FieldDesc | None,
    ) -> None:
        super().__init__(coordinator)
        self._circuit = circuit
        self._target = target
        self._current = current
        self._opmode = opmode
        self._attr_unique_id = f"{DOMAIN}_{circuit}_water_heater".lower()
        self._attr_device_info = build_device_info(coordinator, circuit)
        if target.step is not None:
            self._attr_target_temperature_step = target.step
        feature = WaterHeaterEntityFeature.TARGET_TEMPERATURE
        if opmode and opmode.values:
            self._attr_operation_list = list(dict.fromkeys(opmode.values.values()))
            feature |= WaterHeaterEntityFeature.OPERATION_MODE
        self._attr_supported_features = feature

    def _val(self, desc: FieldDesc | None) -> Any:
        return self.coordinator.data.get(desc.key) if desc else None

    @property
    def current_temperature(self) -> float | None:
        try:
            return float(self._val(self._current))
        except (TypeError, ValueError):
            return None

    @property
    def target_temperature(self) -> float | None:
        try:
            return float(self._val(self._target))
        except (TypeError, ValueError):
            return None

    @property
    def current_operation(self) -> str | None:
        if not self._opmode:
            return None
        value = self._val(self._opmode)
        if value in (self._attr_operation_list or []):
            return value
        return (self._opmode.values or {}).get(str(value))

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temp = kwargs.get("temperature")
        if temp is None:
            return
        out: object = int(temp) if float(temp).is_integer() else temp
        await self._write(self._target, out)

    async def async_set_operation_mode(self, operation_mode: str) -> None:
        if self._opmode:
            await self._write(self._opmode, operation_mode)

    async def _write(self, desc: FieldDesc, value: object) -> None:
        try:
            await self.coordinator.client.write(desc.circuit, desc.message, value)
        except EbusdError as err:
            raise HomeAssistantError(f"WW-Write fehlgeschlagen: {err}") from err
        try:
            await self.coordinator.client.read(desc.circuit, desc.message)
        except EbusdError:
            pass
        await self.coordinator.async_request_refresh()
