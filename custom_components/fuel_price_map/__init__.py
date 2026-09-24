"""The Fuel Price Map integration."""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er

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
    SIGNAL_LOCATION_CHANGED,
)
from .coordinator import FuelPriceCoordinator
from .providers.fuelwatch import FuelWatchProvider
from .providers.suburb_lookup import preload_suburb_coords
from .storage import PriceHistoryStore

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register services before config entries are loaded."""
    _register_services(hass)
    return True


def _register_services(hass: HomeAssistant) -> None:
    """Register integration-wide services once per Home Assistant instance."""
    if not hass.services.has_service(DOMAIN, "refresh_tomorrow_prices"):

        async def _handle_refresh_tomorrow(call: ServiceCall) -> None:
            for entry_data in hass.data.get(DOMAIN, {}).values():
                await entry_data["coordinator"].async_refresh_tomorrow_now()

        hass.services.async_register(
            DOMAIN, "refresh_tomorrow_prices", _handle_refresh_tomorrow
        )

    if not hass.services.has_service(DOMAIN, "toggle_location"):

        async def _handle_toggle_location(call: ServiceCall) -> None:
            requested_entry = call.data.get("entry_id")
            for entry_id, entry_data in hass.data.get(DOMAIN, {}).items():
                if requested_entry and requested_entry != entry_id:
                    continue
                if not await entry_data["coordinator"].async_toggle_location():
                    _LOGGER.warning(
                        "Fuel Price Map location toggle could not activate tracker "
                        "for entry %s",
                        entry_id,
                    )

        hass.services.async_register(
            DOMAIN,
            "toggle_location",
            _handle_toggle_location,
            schema=vol.Schema({vol.Optional("entry_id"): cv.string}),
        )


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
    _register_services(hass)
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
    _migrate_select_entity_ids(hass, entry)
    # Entity platforms may finish registry writes on the next loop turn.
    hass.async_create_task(_async_migrate_select_entity_ids(hass, entry))
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


def _migrate_select_entity_ids(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Move legacy coordinate-derived select IDs to stable IDs when possible."""
    registry = er.async_get(hass)
    migrations = {
        f"{entry.entry_id}_select_fuel_type": "select.fuel_price_map_fuel_type",
        f"{entry.entry_id}_select_preferred_brand": (
            "select.fuel_price_map_preferred_brand"
        ),
        f"{entry.entry_id}_select_sort_order": "select.fuel_price_map_sort_order",
    }
    entries = list(registry.entities.values())
    for unique_id, desired_id in migrations.items():
        current = next(
            (
                item
                for item in entries
                if item.config_entry_id == entry.entry_id
                and item.domain == "select"
                and item.platform == DOMAIN
                and (
                    item.unique_id == unique_id
                    or item.unique_id.endswith(unique_id.split("_", 1)[1])
                )
            ),
            None,
        )
        if current is None or current.entity_id == desired_id:
            continue
        existing = registry.async_get(desired_id)
        if existing is not None and existing.entity_id != current.entity_id:
            _LOGGER.warning(
                "Cannot migrate Fuel Price Map select %s to %s: target is already "
                "registered to %s",
                current.entity_id,
                desired_id,
                existing.unique_id,
            )
            continue
        try:
            registry.async_update_entity(current.entity_id, new_entity_id=desired_id)
            _LOGGER.info(
                "Migrated Fuel Price Map select entity %s to %s",
                current.entity_id,
                desired_id,
            )
        except (ValueError, KeyError) as err:
            _LOGGER.error(
                "Could not migrate Fuel Price Map select entity %s to %s: %s",
                current.entity_id,
                desired_id,
                err,
            )


async def _async_migrate_select_entity_ids(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Retry registry migration after all platform tasks have yielded."""
    await asyncio.sleep(0)
    _migrate_select_entity_ids(hass, entry)


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
