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
from .model import (
    FieldDesc,
    parse_ages,
    parse_decode_errors,
    parse_global,
    parse_values,
)

_LOGGER = logging.getLogger(__name__)

# Ab diesem Alter wird eine Nachricht erzwungen nachgelesen. Bewusst SEHR großzügig:
# per Top-up geholt werden nur Werte, die KEIN Master abfragt -- Konfig/Zähler,
# die sich kaum ändern. Zu niedrig gewählt gelten dauerhaft hunderte Werte als
# "verharzt", der Nachhol-Rückstand ist dann staendig voll und das Zeitbudget je
# Zyklus erschoepft ("Zeitbudget ... erschoepft" im Log) -> der Aufbau bleibt zaeh.
# Bei 30 min schrumpft der Rueckstand auf fast null; statische Werte 30 min alt zu
# haben ist unkritisch. Live-Werte laufen ueber `fast`/nativen Verkehr und bleiben
# ohnehin juenger, werden also nie per Top-up angefasst.
_SELF_MAINTAINED_S = 1800
# Erzwungene Bus-Reads je Zyklus: viele, solange ein Rückstand aufzuholen ist,
# danach nur noch die Grundlast. ebusd führt sie blockierend aus, deshalb gedeckelt.
_TOPUP_MAX = 20
_TOPUP_MIN = 8
_TOPUP_PER_BACKLOG = 20  # je so viele offene Nachrichten ein Read mehr
# So oft die Definitionen neu abgeglichen werden. Neu in ebusd geladene
# Nachrichten (nach Config-Änderung) werden dann von allein aufgenommen --
# ohne Integrations-Reload.
_DEF_REFRESH_S = 600
# Nachrichten, die so oft hintereinander einen Decode-Fehler liefern (Antwort da,
# passt aber nicht zur CSV-Definition), werden aus der Top-up-Rotation genommen:
# sie kosten sonst jeden Zyklus einen erfolglosen Read + Log-Fehler. Bewusst auf
# das Decode-Fehler-Flag gestützt (deterministisch), NICHT auf "kein Wert" -- ein
# Koppler-Timeout (wp1) liefert keinen Wert, ist aber KEIN Decode-Fehler und darf
# eine echte Nachricht nicht aussortieren.
_MAX_DECODE_FAILS = 3
# So oft werden aussortierte ("tote") Nachrichten erneut gelesen. Dekodiert eine
# wieder (z. B. weil die CSV-Definition korrigiert wurde), wird sie automatisch
# wiederbelebt -- ohne Integrations-Reload.
_REVIVE_S = 3600
# Lesbare Nachrichten, die ebusd noch NIE gelesen hat (kein lastup, kein Wert),
# werden aktiv angestossen -- mit kleiner, GARANTIERTER Quote je Zyklus (vor dem
# Stale-Top-up). Klein, weil erzwungene Bus-Reads blockierend sind und Timeouts
# (Koppler/nicht implementiert) sonst den Bus ausbremsen; garantiert, weil das
# Auffuellen sonst verhungert, sobald _stale (veraltete Werte) den Zyklus fuellt.
# Nach wenigen erfolglosen Versuchen wird aufgegeben.
_UNREAD_MAX_TRIES = 3
_UNREAD_PER_CYCLE = 3


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
        self._warned_ages = False
        self._last_def_refresh: float | None = None
        self._decode_fails: dict[tuple[str, str], int] = {}
        self._dead: set[tuple[str, str]] = set()
        self._last_revive: float | None = None
        self._unread_tries: dict[tuple[str, str], int] = {}
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
            if now - lastup > limit
            and self.included_key(key)
            and key not in self._dead
        ]
        stale.sort(key=lambda item: item[1])  # älteste zuerst
        return [key for key, _ in stale]

    def included_key(self, key: tuple[str, str]) -> bool:
        """Wie `included`, aber auf (Kreis, Nachricht) statt auf ein Feld."""
        name = key[1].lower()
        return not any(pattern in name for pattern in self._exclude)

    async def _maybe_refresh_definitions(self) -> None:
        """Neue ebusd-Nachrichten von allein aufnehmen (kein Reload nötig).

        ebusd kann nach einer Config-Änderung neue Nachrichten kennen, die es
        beim Setup noch nicht gab. Nur ergänzen, nie entfernen; geänderte
        Definitionen (z. B. neue Werte-Tabelle) brauchen weiter einen Reload.
        """
        loop = asyncio.get_running_loop()
        if self._last_def_refresh is None:  # Setup hat gerade frisch geholt
            self._last_def_refresh = loop.time()
            return
        if loop.time() - self._last_def_refresh < _DEF_REFRESH_S:
            return
        self._last_def_refresh = loop.time()
        try:
            fields, device_meta = await self.client.get_definitions()
        except EbusdError as err:
            _LOGGER.debug("Definitions-Abgleich fehlgeschlagen: %s", err)
            return
        known = {d.key for d in self.fields}
        new = [d for d in fields if d.key not in known]
        if new:
            self.fields = self.fields + new
            self.device_meta = device_meta
            _LOGGER.info("%d neue ebusd-Nachricht(en) übernommen", len(new))

    def _track_decode_errors(self, errs: set[tuple[str, str]]) -> None:
        """Dauerhaft nicht dekodierbare Nachrichten aus der Rotation nehmen.

        Zählt aufeinanderfolgende Decode-Fehler je Nachricht; nach `_MAX_DECODE_FAILS`
        wird sie als tot markiert und weder per Top-up noch per `fast` gelesen.
        Verschwindet der Fehler (z. B. korrigierte CSV nach Reload), wird der Zähler
        zurückgesetzt und die Nachricht wieder freigegeben.
        """
        for key in list(self._decode_fails):
            if key not in errs:  # dekodiert wieder -> vergessen und wiederbeleben
                del self._decode_fails[key]
                self._dead.discard(key)
        for key in errs:
            n = self._decode_fails.get(key, 0) + 1
            self._decode_fails[key] = n
            if n >= _MAX_DECODE_FAILS and key not in self._dead:
                self._dead.add(key)
                _LOGGER.info(
                    "%s/%s liefert wiederholt undekodierbare Daten -> aus der "
                    "Lese-Rotation genommen (CSV-Definition prüfen)", *key
                )

    def _revive_probe(self) -> list[tuple[str, str]]:
        """Tote Nachrichten in großen Abständen einmal erneut lesen.

        Der erzwungene Read löst einen frischen Dekodier-Versuch aus; klappt er
        (korrigierte Definition), nimmt `_track_decode_errors` die Nachricht von
        allein wieder auf. Sonst bleibt sie tot bis zum nächsten Versuch.
        """
        if not self._dead:
            return []
        loop = asyncio.get_running_loop()
        if self._last_revive is None:
            self._last_revive = loop.time()
            return []
        if loop.time() - self._last_revive < _REVIVE_S:
            return []
        self._last_revive = loop.time()
        _LOGGER.debug("Selbstheilung: %d tote Nachricht(en) erneut probiert", len(self._dead))
        return list(self._dead)

    def _unread(self) -> list[tuple[str, str]]:
        """Lesbare Nachrichten ohne jeden bisherigen Wert einmalig anstossen.

        `_stale` deckt nur Nachrichten mit vorhandenem Zeitstempel ab. Ein
        `r`-Register, das weder ebusd pollt noch ein anderer Master abfragt, hat
        aber nie einen `lastup` -> es fiele durch und bliebe ewig ohne Wert
        ("nicht verfügbar"). Solche hier ein paar Mal aktiv lesen; sobald ein
        Wert kommt, greift danach `_stale`.
        """
        if not self._ages:  # ohne lastup ist die Frische-Logik ohnehin aus
            return []
        valued = {(c, m) for (c, m, _f), v in (self.data or {}).items() if v is not None}
        out: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for desc in self.fields:
            key = (desc.circuit, desc.message)
            if key in seen or desc.writable:  # reine Schreibnachrichten nie lesen
                continue
            if (key not in self._ages and key not in valued
                    and key not in self._dead and key not in self._fast
                    and self.included_key(key)
                    and self._unread_tries.get(key, 0) < _UNREAD_MAX_TRIES):
                seen.add(key)
                out.append(key)
        return out

    async def _async_update_data(self) -> dict[tuple[str, str, str], Any]:
        await self._maybe_refresh_definitions()
        # Erzwungen lesen: erst die vom Nutzer benannten, dann die verharzten
        # reihum -- begrenzt, damit der Bus nicht geflutet wird.
        targets = [key for key in self._fast if key not in self._dead]
        targets += self._revive_probe()
        # Erstwerte VOR dem Stale-Top-up: kleine garantierte Quote, damit das
        # Auffuellen nie verhungert, wenn _stale den Zyklus fuellt. Klein gehalten,
        # damit die blockierenden Erst-Reads (v. a. Timeouts) den Bus nicht bremsen.
        unread = self._unread()
        if unread:
            take = min(_UNREAD_PER_CYCLE, len(unread))
            for key in unread[:take]:
                self._unread_tries[key] = self._unread_tries.get(key, 0) + 1
            targets += unread[:take]
            _LOGGER.debug("%d ungelesene Nachricht(en), stosse %d an", len(unread), take)
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
        self._track_decode_errors(parse_decode_errors(data))
        values = parse_values(data)
        if values and not self._ages and not self._warned_ages:
            # Ohne `lastup` liesse sich nicht erkennen, was der Bus selbst pflegt
            # -- es wuerde dann still gar nichts mehr nachgeholt.
            self._warned_ages = True
            _LOGGER.warning(
                "ebusd liefert kein 'lastup' je Nachricht; Werte werden nicht "
                "nachgeholt. Unterstützt diese ebusd-Version den Parameter 'full'?"
            )
        _LOGGER.debug("ebusd: %d Felder mit Wert", len(values))
        return values
