"""DataUpdateCoordinator: Definitionen einmalig, Werte zyklisch (HTTP-JSON)."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import EbusdClient, EbusdError
from .const import DOMAIN
from .model import FieldDesc, parse_global, parse_values

_LOGGER = logging.getLogger(__name__)


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

    async def _refresh_fast(self) -> None:
        """Zeitkritische Nachrichten vor dem Sammel-Abruf frisch vom Bus holen."""
        for circuit, message in self._fast:
            try:
                await self.client.refresh(circuit, message, self._max_age)
            except EbusdError as err:  # einzelne Nachricht nicht lesbar -> weiter
                _LOGGER.debug("Direktes Lesen von %s/%s: %s", circuit, message, err)

    async def _async_update_data(self) -> dict[tuple[str, str, str], Any]:
        await self._refresh_fast()
        try:
            data = await self.client.get_data()
        except EbusdError as err:
            raise UpdateFailed(f"ebusd: {err}") from err
        self.global_data = parse_global(data)
        values = parse_values(data)
        _LOGGER.debug("ebusd: %d Felder mit Wert", len(values))
        return values
