"""ebusd-Client: Lesen/Definitionen via HTTP-JSON (8889), Schreiben via TCP (8888)."""
from __future__ import annotations

import asyncio
from typing import Any

import aiohttp

from .model import FieldDesc, parse_definitions, parse_device_meta, parse_values


class EbusdError(Exception):
    """Fehler bei der Kommunikation mit ebusd."""


class EbusdClient:
    def __init__(
        self,
        host: str,
        port: int,
        http_port: int,
        session: aiohttp.ClientSession,
    ) -> None:
        self._host = host
        self._port = port  # TCP-Kommandoport (Schreiben)
        self._http_port = http_port  # HTTP-JSON (Lesen/Def)
        self._session = session

    # ---- HTTP-JSON (Lesen) -------------------------------------------------
    async def _get(self, query: str) -> dict[str, Any]:
        url = f"http://{self._host}:{self._http_port}/data{query}"
        try:
            async with self._session.get(
                url, timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                resp.raise_for_status()
                return await resp.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
            raise EbusdError(f"HTTP {url}: {err}") from err

    async def get_definitions(
        self,
    ) -> tuple[list[FieldDesc], dict[str, dict[str, str]]]:
        data = await self._get("?def&write&verbose")
        return parse_definitions(data), parse_device_meta(data)

    async def get_values(self) -> dict[tuple[str, str, str], Any]:
        return parse_values(await self._get(""))

    async def get_data(self) -> dict[str, Any]:
        """Rohes /data (Werte + globaler Abschnitt).

        `full` liefert zusätzlich `lastup` je Nachricht -> Grundlage dafür,
        selbst zu erkennen, welche Werte der Bus ohnehin frisch hält.
        Nicht `verbose`: das schaltet nur Einheiten und Kommentare zu
        (mainloop.cpp; `lastup` hängt an OF_ALL_ATTRS, also an `full`).
        """
        return await self._get("?full")

    async def refresh(self, circuit: str, message: str, max_age: int) -> None:
        """Nachricht direkt vom Bus lesen, falls der Cache älter als `max_age` ist.

        ebusd führt den Bus-Read dabei blockierend aus (mainloop.cpp: readFromBus),
        deshalb nur für wenige, wirklich zeitkritische Nachrichten verwenden.
        """
        await self._get(f"/{circuit}/{message}?exact=1&required=1&maxage={max_age}")

    # ---- TCP (Schreiben + Verbindungstest) ---------------------------------
    async def _command(self, cmd: str) -> list[str]:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, self._port), timeout=10
            )
        except (OSError, asyncio.TimeoutError) as err:
            raise EbusdError(f"TCP connect {self._host}:{self._port}: {err}") from err
        try:
            writer.write((cmd + "\n").encode())
            await writer.drain()
            lines: list[str] = []
            while True:
                raw = await asyncio.wait_for(reader.readline(), timeout=15)
                if raw == b"":
                    break
                line = raw.decode(errors="replace").rstrip("\r\n")
                if line == "":
                    break
                lines.append(line)
            return lines
        except (OSError, asyncio.TimeoutError) as err:
            raise EbusdError(f"TCP command {cmd!r}: {err}") from err
        finally:
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), timeout=5)
            except (OSError, asyncio.TimeoutError):
                pass

    async def write(self, circuit: str, message: str, value: object) -> None:
        await self._command(f"write -c {circuit} {message} {value}")

    async def read(self, circuit: str, message: str) -> None:
        """Erzwingt einen frischen Read vom Bus (aktualisiert ebusds Cache -> /data)."""
        await self._command(f"read -f -c {circuit} {message}")

    async def test(self) -> None:
        """Prüft beide Ports (HTTP lesen + TCP erreichbar)."""
        await self._get("")  # HTTP 8889
        await self._command("info")  # TCP 8888
