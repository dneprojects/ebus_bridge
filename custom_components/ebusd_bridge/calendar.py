"""Calendar-Plattform: Vaillant-Wochen-Zeitprogramme als Kalender (read-only).

Timer-Nachrichten heißen `<Prefix>Timer_<Wochentag><Slot>` und enthalten je ein
Fenster: `htm` (von), `htm_1` (bis), optional `slottemp` (Soll-Temperatur).
Je (Kreis, Prefix) entsteht ein Kalender (z. B. ctlv3/Z1, ctlv3/Hwc).
"""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta

import homeassistant.util.dt as dt_util
from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import EbusdCoordinator
from .entity import _device_name

_WEEKDAY = {
    "Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3,
    "Friday": 4, "Saturday": 5, "Sunday": 6,
}
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


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: EbusdCoordinator = hass.data[DOMAIN][entry.entry_id]

    # (circuit, prefix) -> Liste (Wochentag, Nachrichtenname)
    schedules: dict[tuple[str, str], list[tuple[int, str]]] = {}
    seen: set[tuple[str, str]] = set()
    for d in coordinator.fields:
        if (d.circuit, d.message) in seen:
            continue
        m = _TIMER_RE.match(d.message)
        if not m:
            continue
        seen.add((d.circuit, d.message))
        schedules.setdefault((d.circuit, m.group("prefix")), []).append(
            (_WEEKDAY[m.group("day")], d.message)
        )

    async_add_entities(
        EbusdCalendar(coordinator, circuit, prefix, slots)
        for (circuit, prefix), slots in schedules.items()
    )


class EbusdCalendar(CoordinatorEntity[EbusdCoordinator], CalendarEntity):
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: EbusdCoordinator,
        circuit: str,
        prefix: str,
        slots: list[tuple[int, str]],
    ) -> None:
        super().__init__(coordinator)
        self._circuit = circuit
        self._slots = slots  # (weekday, message)
        self._attr_name = f"{prefix} Zeitprogramm"
        self._attr_unique_id = f"{DOMAIN}_{circuit}_{prefix}_timer".lower()
        meta = coordinator.device_meta.get(circuit, {})
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, circuit)},
            name=_device_name(circuit, meta.get("model")),
            manufacturer=meta.get("manufacturer", "Vaillant"),
            model=meta.get("model"),
            sw_version=meta.get("sw"),
            hw_version=meta.get("hw"),
        )

    def _events_for_day(self, day: date) -> list[CalendarEvent]:
        events: list[CalendarEvent] = []
        tz = dt_util.get_default_time_zone()
        for weekday, msg in self._slots:
            if weekday != day.weekday():
                continue
            start_t = _parse_hm(self.coordinator.data.get((self._circuit, msg, "htm")))
            end_t = _parse_hm(self.coordinator.data.get((self._circuit, msg, "htm_1")))
            if start_t is None or end_t is None or start_t == end_t:
                continue  # leerer/ungültiger Slot (z. B. 00:00-00:00)
            start = datetime.combine(day, start_t, tzinfo=tz)
            end = datetime.combine(day, end_t, tzinfo=tz)
            if end <= start:
                end += timedelta(days=1)  # über Mitternacht
            temp = self.coordinator.data.get((self._circuit, msg, "slottemp"))
            try:
                summary = f"{float(temp):g} °C"
            except (TypeError, ValueError):
                summary = "ein"
            events.append(CalendarEvent(start=start, end=end, summary=summary))
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
        for offset in range(8):  # aktuelles bzw. nächstes Fenster (max. 1 Woche)
            upcoming.extend(self._events_for_day((now + timedelta(days=offset)).date()))
        upcoming.sort(key=lambda e: e.start)
        for ev in upcoming:
            if ev.end > now:
                return ev
        return None
