"""The Fuel Price Map integration."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall

from .const import (
    CONF_FUEL_TYPES,
    CONF_PROVIDER,
    DEFAULT_SORT_ORDER,
    DOMAIN,
    PLATFORMS,
    PROVIDER_FUELWATCH_WA,
    SELECT_FUEL_TYPE,
    SELECT_PREFERRED_BRAND,
    SELECT_SORT_ORDER,
    ANY_BRAND,
)
from .coordinator import FuelPriceCoordinator
from .providers.fuelwatch import FuelWatchProvider
from .providers.suburb_lookup import preload_suburb_coords
from .storage import PriceHistoryStore

_LOGGER = logging.getLogger(__name__)


class SelectionState:
    """Holds the currently selected fuel type / preferred brand for the UI.

    Kept separate from the coordinator so the select entities can update it
    synchronously without needing a full data refresh.
    """

    def __init__(self, default_fuel_type: str) -> None:
        self.fuel_type = default_fuel_type
        self.brand = ANY_BRAND
        self.sort_order = DEFAULT_SORT_ORDER


def _build_provider(entry: ConfigEntry):
    provider_id = entry.data.get(CONF_PROVIDER, PROVIDER_FUELWATCH_WA)
    if provider_id == PROVIDER_FUELWATCH_WA:
        return FuelWatchProvider()
    raise ValueError(f"Unknown provider '{provider_id}'")


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    manifest = await hass.async_add_executor_job(
        lambda: json.loads((Path(__file__).parent / "manifest.json").read_text())
    )
    _LOGGER.info("Setting up Fuel Price Map v%s", manifest.get("version", "unknown"))

    provider = _build_provider(entry)
    await hass.async_add_executor_job(preload_suburb_coords)
    history_store = PriceHistoryStore(hass, entry.entry_id)
    await history_store.async_load()

    coordinator = FuelPriceCoordinator(hass, entry, provider, history_store)
    await coordinator.async_config_entry_first_refresh()
    coordinator.async_setup_schedule()

    fuel_types = entry.data.get(CONF_FUEL_TYPES, [])
    selection = SelectionState(fuel_types[0] if fuel_types else "")

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "provider": provider,
        "history_store": history_store,
        "selection": selection,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    if not hass.services.has_service(DOMAIN, "refresh_tomorrow_prices"):

        async def _handle_refresh_tomorrow(call: ServiceCall) -> None:
            for entry_data in hass.data.get(DOMAIN, {}).values():
                await entry_data["coordinator"].async_refresh_tomorrow_now()

        hass.services.async_register(DOMAIN, "refresh_tomorrow_prices", _handle_refresh_tomorrow)

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    # A full reload (not just a coordinator refresh) is needed because some
    # options - e.g. map_marker_count - change how many entities get
    # created, not just what data they show.
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        data["coordinator"].async_unload()
    return unload_ok
