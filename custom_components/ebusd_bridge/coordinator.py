"""DataUpdateCoordinator: Definitionen einmalig, Werte zyklisch (HTTP-JSON)."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import EbusdClient, EbusdError
from .const import DOMAIN
from .model import FieldDesc

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

    def included(self, desc: FieldDesc) -> bool:
        """False, wenn der Nachrichtenname ein Ausschluss-Muster enthält."""
        name = desc.message.lower()
        return not any(pattern in name for pattern in self._exclude)

    async def _async_update_data(self) -> dict[tuple[str, str, str], Any]:
        try:
            values = await self.client.get_values()
        except EbusdError as err:
            raise UpdateFailed(f"ebusd: {err}") from err
        _LOGGER.debug("ebusd: %d Felder mit Wert", len(values))
        return values
