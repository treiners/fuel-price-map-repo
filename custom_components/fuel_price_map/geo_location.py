"""Geo-location entities for the map: all in-radius stations for the
currently selected fuel type (+ optional brand filter).

These use HA's `geo_location` platform, the same mechanism built-in feeds
(e.g. GeoNet, GDACS) use for showing many transient points on a map without
each one being a persisted/recorded sensor. Entities are created/removed as
stations enter/leave the current filter instead of existing permanently.
"""
from __future__ import annotations

import logging

from homeassistant.components.geo_location import GeolocationEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfLength
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ANY_BRAND,
    CONF_MAX_STATIONS,
    DEFAULT_MAX_STATIONS,
    DOMAIN,
    SIGNAL_SELECTION_CHANGED,
    SIGNAL_STATIONS_UPDATED,
)
from .providers import StationPrice

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    manager = StationGeoManager(hass, entry, data["coordinator"], data["selection"], async_add_entities)
    manager.async_start()
    data["geo_manager"] = manager


class StationGeoManager:
    """Keeps geo_location entities in sync with coordinator data + UI selection."""

    def __init__(self, hass, entry, coordinator, selection, async_add_entities) -> None:
        self.hass = hass
        self.entry = entry
        self.coordinator = coordinator
        self.selection = selection
        self._async_add_entities = async_add_entities
        self._entities: dict[str, "FuelStationLocation"] = {}
        self._unsub = []

    def async_start(self) -> None:
        self._unsub.append(
            async_dispatcher_connect(self.hass, SIGNAL_STATIONS_UPDATED, self._async_refresh)
        )
        self._unsub.append(
            async_dispatcher_connect(self.hass, SIGNAL_SELECTION_CHANGED, self._async_refresh)
        )
        self._async_refresh()

    def async_unload(self) -> None:
        for unsub in self._unsub:
            unsub()

    @callback
    def _async_refresh(self, *_args) -> None:
        fuel_type = self.selection.fuel_type
        stations: list[StationPrice] = self.coordinator.data.get(fuel_type, [])
        if self.selection.brand and self.selection.brand != ANY_BRAND:
            stations = [s for s in stations if s.brand == self.selection.brand]

        max_stations = self.coordinator.options.get(CONF_MAX_STATIONS, DEFAULT_MAX_STATIONS)
        stations = stations[:max_stations]

        current_ids = set(self._entities.keys())
        new_ids = {s.station_id for s in stations}

        # Remove stations no longer in range/filter
        for stale_id in current_ids - new_ids:
            entity = self._entities.pop(stale_id)
            self.hass.async_create_task(entity.async_remove(force_remove=True))

        # Add or update
        to_add = []
        for station in stations:
            existing = self._entities.get(station.station_id)
            if existing is None:
                entity = FuelStationLocation(self.entry.entry_id, station)
                self._entities[station.station_id] = entity
                to_add.append(entity)
            else:
                existing.update_from_station(station)

        if to_add:
            self._async_add_entities(to_add)


class FuelStationLocation(GeolocationEvent):
    """A single fuel station marker on the map."""

    _attr_should_poll = False
    _attr_unit_of_measurement = UnitOfLength.KILOMETERS
    _attr_icon = "mdi:gas-station"

    def __init__(self, entry_id: str, station: StationPrice) -> None:
        self._entry_id = entry_id
        self._station = station
        self._attr_unique_id = f"{entry_id}_geo_{station.station_id}_{station.fuel_type}"

    def update_from_station(self, station: StationPrice) -> None:
        self._station = station
        self.async_write_ha_state()

    @property
    def source(self) -> str:
        return DOMAIN

    @property
    def name(self) -> str:
        station = self._station
        if station.discount_cents:
            price_part = f"{station.effective_price_cents:.1f}\u00a2 eff."
        else:
            price_part = f"{station.price_cents:.1f}\u00a2"

        trend = station.trend_cents
        trend_part = ""
        if trend is not None and abs(trend) >= 0.05:
            sign = "+" if trend > 0 else ""
            trend_part = f", {sign}{trend:.1f}\u00a2 tmrw"

        return f"{station.name} ({price_part}{trend_part})"

    @property
    def latitude(self) -> float:
        return self._station.latitude

    @property
    def longitude(self) -> float:
        return self._station.longitude

    @property
    def distance(self) -> float | None:
        return self._station.distance_km

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "price": self._station.price_cents,
            "discount_cents": self._station.discount_cents,
            "effective_price": self._station.effective_price_cents,
            "trend_cents": self._station.trend_cents,
            "brand": self._station.brand,
            "address": self._station.address,
            "suburb": self._station.suburb,
            "fuel_type": self._station.fuel_type,
            "updated": self._station.updated,
            "distance_km": round(self._station.distance_km, 2) if self._station.distance_km else None,
        }
