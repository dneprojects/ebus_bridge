"""Calendar-Plattform: Vaillant-Wochen-Zeitprogramme.

Lesen: pro Slot eine Nachricht `<Prefix>Timer_<Wochentag><Slot>` mit `htm` (von),
`htm_1` (bis), optional `slottemp`. Je (Kreis, Prefix) ein Kalender.

Schreiben (nur wenn ebusd eine schreibbare Tages-Nachricht `<Prefix>Timer_<Tag>`
anbietet – sonst read-only): ebusds offizielle Timer-Konvention ist ein Write pro
Tag mit `slotIndex;slotCount;von;bis[;temp]`. Wir reichen das über den TCP-`write`
durch. Bearbeiten gilt immer für das **ganze** Wochen-Fenster (das Gerät kennt
keine Einzeltag-Ausnahme). `slotCount`-Semantik ist best-effort und wird auf einem
System mit schreibbaren Timern final verifiziert.
"""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from typing import Any

import homeassistant.util.dt as dt_util
from homeassistant.components.calendar import (
    CalendarEntity,
    CalendarEntityFeature,
    CalendarEvent,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client import EbusdError
from .const import DOMAIN
from .coordinator import EbusdCoordinator
from .entity import build_device_info

_WEEKDAY_NAMES = [
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
]
_WEEKDAY = {name: idx for idx, name in enumerate(_WEEKDAY_NAMES)}
_TIMER_RE = re.compile(
    r"^(?P<prefix>.+?)Timer_(?P<day>" + "|".join(_WEEKDAY) + r")(?P<slot>\d+)$"
)


def _parse_hm(value: object) -> time | None:
    if not isinstance(value, str) or ":" not in value:
        return None
    try:
        h, m = value.split(":")[:2]
        return time(int(h), int(m))
    except ValueError:
        return None


def _parse_temp(summary: str | None) -> float | None:
    if not summary:
        return None
    m = re.search(r"-?\d+(?:[.,]\d+)?", summary)
    return float(m.group().replace(",", ".")) if m else None


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: EbusdCoordinator = hass.data[DOMAIN][entry.entry_id]
    writable_msgs = {d.message for d in coordinator.fields if d.writable}

    # (circuit, prefix) -> Liste (weekday, slot, read_message)
    schedules: dict[tuple[str, str], list[tuple[int, int, str]]] = {}
    has_temp: dict[tuple[str, str], bool] = {}
    seen: set[tuple[str, str]] = set()
    for d in coordinator.fields:
        m = _TIMER_RE.match(d.message)
        if not m:
            continue
        pkey = (d.circuit, m.group("prefix"))
        if d.field == "slottemp":  # dieses Wochenprogramm hat eine Soll-Temperatur
            has_temp[pkey] = True
        if (d.circuit, d.message) in seen:
            continue
        seen.add((d.circuit, d.message))
        schedules.setdefault(pkey, []).append(
            (_WEEKDAY[m.group("day")], int(m.group("slot")), d.message)
        )

    entities = []
    for (circuit, prefix), slots in schedules.items():
        # schreibbar, wenn die Tages-Write-Nachricht für einen der Tage existiert
        writable = any(
            f"{prefix}Timer_{_WEEKDAY_NAMES[wd]}" in writable_msgs
            for wd, _, _ in slots
        )
        entities.append(
            EbusdCalendar(
                coordinator, circuit, prefix, slots,
                writable=writable, has_temp=has_temp.get((circuit, prefix), False),
            )
        )
    async_add_entities(entities)


class EbusdCalendar(CoordinatorEntity[EbusdCoordinator], CalendarEntity):
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: EbusdCoordinator,
        circuit: str,
        prefix: str,
        slots: list[tuple[int, int, str]],
        writable: bool,
        has_temp: bool,
    ) -> None:
        super().__init__(coordinator)
        self._circuit = circuit
        self._prefix = prefix
        self._has_temp = has_temp
        # weekday -> sortierte Liste (slot, read_message)
        self._by_day: dict[int, list[tuple[int, str]]] = {}
        for weekday, slot, msg in slots:
            self._by_day.setdefault(weekday, []).append((slot, msg))
        for day_slots in self._by_day.values():
            day_slots.sort()
        self._attr_name = f"{prefix} Zeitprogramm"
        self._attr_unique_id = f"{DOMAIN}_{circuit}_{prefix}_timer".lower()
        if writable:
            self._attr_supported_features = (
                CalendarEntityFeature.CREATE_EVENT
                | CalendarEntityFeature.UPDATE_EVENT
                | CalendarEntityFeature.DELETE_EVENT
            )
        self._attr_device_info = build_device_info(coordinator, circuit)

    # ---- Lesen -------------------------------------------------------------
    def _slot_value(self, read_msg: str) -> tuple[time | None, time | None, object]:
        get = self.coordinator.data.get
        frm = _parse_hm(get((self._circuit, read_msg, "htm")))
        to = _parse_hm(get((self._circuit, read_msg, "htm_1")))
        temp = get((self._circuit, read_msg, "slottemp"))
        return frm, to, temp

    def _uid(self, weekday: int, slot: int, day: date) -> str:
        return f"{self._circuit}|{self._prefix}|{weekday}|{slot}|{day.isoformat()}"

    def _events_for_day(self, day: date) -> list[CalendarEvent]:
        events: list[CalendarEvent] = []
        tz = dt_util.get_default_time_zone()
        for slot, msg in self._by_day.get(day.weekday(), []):
            frm, to, temp = self._slot_value(msg)
            if frm is None or to is None or frm == to:
                continue  # leerer/ungültiger Slot
            start = datetime.combine(day, frm, tzinfo=tz)
            end = datetime.combine(day, to, tzinfo=tz)
            if end <= start:
                end += timedelta(days=1)  # über Mitternacht
            try:
                summary = f"{float(temp):g} °C"
            except (TypeError, ValueError):
                summary = "ein"
            events.append(
                CalendarEvent(
                    start=start, end=end, summary=summary,
                    uid=self._uid(day.weekday(), slot, day),
                )
            )
        return events

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        events: list[CalendarEvent] = []
        day = start_date.date()
        while day <= end_date.date():
            events.extend(self._events_for_day(day))
            day += timedelta(days=1)
        return events

    @property
    def event(self) -> CalendarEvent | None:
        now = dt_util.now()
        upcoming: list[CalendarEvent] = []
        for offset in range(8):
            upcoming.extend(self._events_for_day((now + timedelta(days=offset)).date()))
        upcoming.sort(key=lambda e: e.start)
        for ev in upcoming:
            if ev.end > now:
                return ev
        return None

    # ---- Schreiben ---------------------------------------------------------
    def _active_slots(self, weekday: int) -> int:
        count = 0
        for _slot, msg in self._by_day.get(weekday, []):
            frm, to, _ = self._slot_value(msg)
            if frm is not None and to is not None and frm != to:
                count += 1
        return count

    async def _write_slot(
        self,
        weekday: int,
        slot: int,
        frm: str,
        to: str,
        temp: float | None,
        count: int,
    ) -> None:
        msg = f"{self._prefix}Timer_{_WEEKDAY_NAMES[weekday]}"
        parts = [str(slot), str(max(count, 0)), frm, to]
        if self._has_temp:
            parts.append(f"{float(temp if temp is not None else 0):g}")
        value = ";".join(parts)
        try:
            await self.coordinator.client.write(self._circuit, msg, value)
        except EbusdError as err:
            raise HomeAssistantError(f"Timer-Write fehlgeschlagen: {err}") from err
        # betroffene Lese-Slots frisch lesen, damit der Kalender aktuell ist
        for _slot, read_msg in self._by_day.get(weekday, []):
            try:
                await self.coordinator.client.read(self._circuit, read_msg)
            except EbusdError:
                pass
        await self.coordinator.async_request_refresh()

    @staticmethod
    def _hm(value: datetime) -> str:
        return dt_util.as_local(value).strftime("%H:%M")

    def _decode_uid(self, uid: str) -> tuple[int, int]:
        try:
            parts = uid.split("|")
            return int(parts[2]), int(parts[3])
        except (IndexError, ValueError) as err:
            raise HomeAssistantError(f"Ungültige Termin-ID: {uid}") from err

    async def async_create_event(self, **kwargs: Any) -> None:
        start = kwargs.get("dtstart")
        end = kwargs.get("dtend")
        if not isinstance(start, datetime) or not isinstance(end, datetime):
            raise HomeAssistantError("Zeitprogramm-Fenster brauchen eine Uhrzeit.")
        weekday = dt_util.as_local(start).weekday()
        # ersten leeren Slot des Tages suchen
        free = None
        for slot, msg in self._by_day.get(weekday, []):
            frm, to, _ = self._slot_value(msg)
            if frm is None or frm == to:
                free = slot
                break
        if free is None:
            raise HomeAssistantError("Für diesen Wochentag sind alle Slots belegt.")
        await self._write_slot(
            weekday, free, self._hm(start), self._hm(end),
            _parse_temp(kwargs.get("summary")), self._active_slots(weekday) + 1,
        )

    async def async_update_event(
        self,
        uid: str,
        event: dict[str, Any],
        recurrence_id: str | None = None,
        recurrence_range: str | None = None,
    ) -> None:
        weekday, slot = self._decode_uid(uid)
        start = event.get("dtstart")
        end = event.get("dtend")
        if not isinstance(start, datetime) or not isinstance(end, datetime):
            raise HomeAssistantError("Zeitprogramm-Fenster brauchen eine Uhrzeit.")
        await self._write_slot(
            weekday, slot, self._hm(start), self._hm(end),
            _parse_temp(event.get("summary")), self._active_slots(weekday),
        )

    async def async_delete_event(
        self,
        uid: str,
        recurrence_id: str | None = None,
        recurrence_range: str | None = None,
    ) -> None:
        weekday, slot = self._decode_uid(uid)
        # Slot leeren: Fenster auf 00:00-00:00, Slotzahl verringern
        await self._write_slot(
            weekday, slot, "00:00", "00:00", 0,
            max(self._active_slots(weekday) - 1, 0),
        )
