"""Climate-Plattform: Heizkreise (Zonen) als HA-climate-Entities.

Kuratierter Vaillant-Overlay: erkennt die Zonen-Register
`Z<n>DayTemp` / `Z<n>RoomTemp` / `Z<n>OpMode` und bildet je **aktive** Zone ein
Thermostat ab: Ziel = Komfort-Sollwert (`Z<n>DayTemp`), Ist = `Z<n>RoomTemp`,
Modi aus `Z<n>OpMode` (off→OFF, auto→AUTO, sonst HEAT + Preset). Fehlen die
Register (Nicht-Vaillant), entsteht kein Gerät. Rohe Entitäten bleiben zusätzlich.
"""
from __future__ import annotations

import re
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
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

_ROLE = {"DayTemp": "day", "RoomTemp": "room", "OpMode": "op"}
_ZONE_RE = re.compile(r"^Z(\d+)(DayTemp|RoomTemp|OpMode)$")


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: EbusdCoordinator = hass.data[DOMAIN][entry.entry_id]
    zones: dict[tuple[str, int], dict[str, FieldDesc]] = {}
    for d in coordinator.fields:
        m = _ZONE_RE.match(d.message)
        if m:
            zones.setdefault((d.circuit, int(m.group(1))), {})[_ROLE[m.group(2)]] = d

    entities = []
    for (circuit, n), parts in sorted(zones.items()):
        day = parts.get("day")
        if day is None or not day.writable:
            continue  # ohne schreibbaren Komfort-Sollwert kein Thermostat
        # nur aktive Zonen (mit tatsächlichen Daten) anlegen
        if not any(coordinator.data.get(p.key) is not None for p in parts.values()):
            continue
        entities.append(
            EbusdZoneClimate(
                coordinator, circuit, n, day, parts.get("room"), parts.get("op")
            )
        )
    async_add_entities(entities)


class EbusdZoneClimate(CoordinatorEntity[EbusdCoordinator], ClimateEntity):
    _attr_has_entity_name = True
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_min_temp = 5
    _attr_max_temp = 30
    _attr_target_temperature_step = 0.5

    def __init__(
        self,
        coordinator: EbusdCoordinator,
        circuit: str,
        zone: int,
        day: FieldDesc,
        room: FieldDesc | None,
        opmode: FieldDesc | None,
    ) -> None:
        super().__init__(coordinator)
        self._day = day
        self._room = room
        self._op = opmode if (opmode and opmode.writable and opmode.values) else None
        self._attr_name = f"Heizkreis {zone}"
        self._attr_unique_id = f"{DOMAIN}_{circuit}_z{zone}_climate".lower()
        self._attr_device_info = build_device_info(coordinator, circuit)

        names = list((self._op.values or {}).values()) if self._op else []
        low = {v.lower(): v for v in names}
        self._off = low.get("off")
        self._auto = low.get("auto")
        self._presets = [v for v in names if v.lower() not in ("off", "auto")]
        self._heat_default = low.get("day") or (self._presets[0] if self._presets else None)

        modes = [HVACMode.HEAT]
        if self._off:
            modes.insert(0, HVACMode.OFF)
        if self._auto:
            modes.append(HVACMode.AUTO)
        self._attr_hvac_modes = modes

        feature = ClimateEntityFeature.TARGET_TEMPERATURE
        if self._off:
            feature |= ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
        if self._presets:
            self._attr_preset_modes = self._presets
            feature |= ClimateEntityFeature.PRESET_MODE
        self._attr_supported_features = feature

    def _val(self, desc: FieldDesc | None) -> Any:
        return self.coordinator.data.get(desc.key) if desc else None

    @property
    def current_temperature(self) -> float | None:
        try:
            return float(self._val(self._room))
        except (TypeError, ValueError):
            return None

    @property
    def target_temperature(self) -> float | None:
        try:
            return float(self._val(self._day))
        except (TypeError, ValueError):
            return None

    @property
    def hvac_mode(self) -> HVACMode:
        value = self._val(self._op)
        low = str(value).lower() if value is not None else ""
        if low == "off":
            return HVACMode.OFF
        if low == "auto":
            return HVACMode.AUTO
        return HVACMode.HEAT

    @property
    def preset_mode(self) -> str | None:
        value = self._val(self._op)
        return value if value in (self._presets or []) else None

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temp = kwargs.get("temperature")
        if temp is None:
            return
        out: object = int(temp) if float(temp).is_integer() else temp
        await self._write(self._day, out)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if not self._op:
            return
        if hvac_mode == HVACMode.OFF and self._off:
            await self._write(self._op, self._off)
        elif hvac_mode == HVACMode.AUTO and self._auto:
            await self._write(self._op, self._auto)
        elif hvac_mode == HVACMode.HEAT and self._heat_default:
            await self._write(self._op, self._heat_default)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        if self._op and preset_mode in (self._presets or []):
            await self._write(self._op, preset_mode)

    async def async_turn_off(self) -> None:
        if self._op and self._off:
            await self._write(self._op, self._off)

    async def async_turn_on(self) -> None:
        if self._op and self._heat_default:
            await self._write(self._op, self._heat_default)

    async def _write(self, desc: FieldDesc, value: object) -> None:
        try:
            await self.coordinator.client.write(desc.circuit, desc.message, value)
        except EbusdError as err:
            raise HomeAssistantError(f"Zonen-Write fehlgeschlagen: {err}") from err
        try:
            await self.coordinator.client.read(desc.circuit, desc.message)
        except EbusdError:
            pass
        await self.coordinator.async_request_refresh()
