"""DataUpdateCoordinator: Definitionen einmalig, Werte zyklisch (HTTP-JSON)."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import EbusdClient, EbusdError
from .const import DOMAIN
from .model import FieldDesc, parse_ages, parse_global, parse_values

_LOGGER = logging.getLogger(__name__)

# Werte, die der Bus binnen dieser Zeit von allein nachliefert (fremde Master,
# die ebusd passiv mithört), brauchen kein erzwungenes Lesen.
_SELF_MAINTAINED_S = 90
# Erzwungene Bus-Reads je Zyklus: viele, solange ein Rückstand aufzuholen ist,
# danach nur noch die Grundlast. ebusd führt sie blockierend aus, deshalb gedeckelt.
_TOPUP_MAX = 20
_TOPUP_MIN = 8
_TOPUP_PER_BACKLOG = 20  # je so viele offene Nachrichten ein Read mehr


class EbusdCoordinator(DataUpdateCoordinator[dict[tuple[str, str, str], Any]]):
    """`fields` = Deskriptoren (fix), `data` = aktuelle Werte je Feld."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: EbusdClient,
        fields: list[FieldDesc],
        device_meta: dict[str, dict[str, str]],
        scan_interval: int,
        exclude: list[str],
        entry_id: str,
        host: str,
        fast: list[str] | None = None,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self.fields = fields
        self.device_meta = device_meta
        self._exclude = exclude
        self.entry_id = entry_id
        self.host = host
        self.global_data: dict[str, Any] = {}
        self._max_age = scan_interval
        self._ages: dict[tuple[str, str], int] = {}
        self._cursor = 0
        self._fast = self._collect_fast(fields, fast or [])
        if self._fast:
            _LOGGER.info(
                "Direkt vom Bus je %d s: %s",
                scan_interval,
                ", ".join(f"{c}/{m}" for c, m in self._fast),
            )

    def _collect_fast(
        self, fields: list[FieldDesc], patterns: list[str]
    ) -> list[tuple[str, str]]:
        """Nachrichten, die je Zyklus erzwungen gelesen werden (Namens-Teilstrings)."""
        if not patterns:
            return []
        out: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for desc in fields:
            key = (desc.circuit, desc.message)
            if key in seen or not self.included(desc):
                continue
            if any(p in desc.message.lower() for p in patterns):
                seen.add(key)
                out.append(key)
        return out

    @property
    def bridge_id(self) -> tuple[str, str]:
        """Identifier des Bridge-Elterngeräts (via_device-Ziel der Kreise)."""
        return (DOMAIN, self.entry_id)

    def included(self, desc: FieldDesc) -> bool:
        """False, wenn der Nachrichtenname ein Ausschluss-Muster enthält."""
        name = desc.message.lower()
        return not any(pattern in name for pattern in self._exclude)

    async def _refresh(self, targets: list[tuple[str, str]]) -> None:
        """Nachrichten direkt vom Bus nachholen (ebusd liest dabei blockierend).

        Zeitbremse: antwortet ein Gerät nicht, läuft der Read in ebusds eigenen
        Timeout. Ohne Deckel könnten wenige solcher Nachrichten den Zyklus
        überziehen und die aktuellen Werte ausbremsen.
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + max(5.0, self._max_age * 0.5)
        for circuit, message in targets:
            if loop.time() > deadline:
                _LOGGER.debug("Zeitbudget fürs Nachholen erschöpft, Rest folgt")
                return
            try:
                await self.client.refresh(circuit, message, self._max_age)
            except EbusdError as err:  # einzelne Nachricht nicht lesbar -> weiter
                _LOGGER.debug("Direktes Lesen von %s/%s: %s", circuit, message, err)

    def _stale(self) -> list[tuple[str, str]]:
        """Nachrichten, die der Bus nicht von allein frisch hält, älteste zuerst.

        Bezugspunkt ist ebusds eigene Uhr (jüngster Zeitstempel der Antwort),
        damit eine Zeitabweichung zwischen HA und ebusd nichts verfälscht.
        """
        if not self._ages:
            return []
        now = max(self._ages.values())
        limit = max(3 * self._max_age, _SELF_MAINTAINED_S)
        stale = [
            (key, lastup)
            for key, lastup in self._ages.items()
            if now - lastup > limit and self.included_key(key)
        ]
        stale.sort(key=lambda item: item[1])  # älteste zuerst
        return [key for key, _ in stale]

    def included_key(self, key: tuple[str, str]) -> bool:
        """Wie `included`, aber auf (Kreis, Nachricht) statt auf ein Feld."""
        name = key[1].lower()
        return not any(pattern in name for pattern in self._exclude)

    async def _async_update_data(self) -> dict[tuple[str, str, str], Any]:
        # Erzwungen lesen: erst die vom Nutzer benannten, dann die verharzten
        # reihum -- begrenzt, damit der Bus nicht geflutet wird.
        targets = list(self._fast)
        stale = self._stale()
        if stale:
            take = min(_TOPUP_MAX, max(_TOPUP_MIN, len(stale) // _TOPUP_PER_BACKLOG))
            self._cursor %= len(stale)
            targets += stale[self._cursor : self._cursor + take]
            self._cursor += take
            _LOGGER.debug("%d Nachrichten verharzt, hole %d nach", len(stale), take)
        if targets:
            await self._refresh(targets)

        try:
            data = await self.client.get_data()
        except EbusdError as err:
            raise UpdateFailed(f"ebusd: {err}") from err
        self.global_data = parse_global(data)
        self._ages = parse_ages(data)
        values = parse_values(data)
        _LOGGER.debug("ebusd: %d Felder mit Wert", len(values))
        return values
