"""eBUS Bridge – native HA-Integration über ebusds HTTP-JSON + TCP (ohne MQTT)."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import EbusdClient, EbusdError
from .const import (
    CONF_EXCLUDE,
    CONF_FAST,
    CONF_HOST,
    CONF_HTTP_PORT,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    DEFAULT_EXCLUDE,
    DEFAULT_FAST,
    DEFAULT_HTTP_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .coordinator import EbusdCoordinator
from .services import async_setup_services, async_unload_services

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    "binary_sensor", "calendar", "climate", "sensor", "number", "select",
    "switch", "water_heater",
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    client = EbusdClient(
        entry.data[CONF_HOST],
        entry.data[CONF_PORT],
        entry.data.get(CONF_HTTP_PORT, DEFAULT_HTTP_PORT),
        async_get_clientsession(hass),
    )

    try:
        fields, device_meta = await client.get_definitions()
    except EbusdError as err:
        raise ConfigEntryNotReady(f"ebusd-Definitionen: {err}") from err

    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    exclude = [
        p.strip().lower()
        for p in entry.options.get(CONF_EXCLUDE, DEFAULT_EXCLUDE).split(",")
        if p.strip()
    ]

    fast = [
        p.strip().lower()
        for p in entry.options.get(CONF_FAST, DEFAULT_FAST).split(",")
        if p.strip()
    ]

    host = entry.data[CONF_HOST]
    coordinator = EbusdCoordinator(
        hass, client, fields, device_meta, scan_interval, exclude,
        entry.entry_id, host, fast,
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # Bridge-Elterngerät: die eBUS-Kreise hängen per via_device darunter.
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name="eBUS Bridge",
        manufacturer="ebusd",
        model="eBUS ↔ Home Assistant",
        sw_version=coordinator.global_data.get("version"),
        configuration_url=f"http://{host}:{entry.data.get(CONF_HTTP_PORT, DEFAULT_HTTP_PORT)}/data",
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await async_setup_services(hass)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Bei geänderten Optionen die Integration neu laden."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
        async_unload_services(hass)
    return unloaded
