"""Sensors: one per configured fuel type = current cheapest price in radius.

This is the ONLY entity type that carries persisted history, and there is one
per fuel type (not per station), so entity count stays small regardless of how
many stations are in range. The rolling 14-day/2x-daily history lives in the
`history` attribute and is what a future "tap for past 14 days" card reads.
"""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ANY_BRAND,
    ATTR_ADDRESS,
    ATTR_BRAND,
    ATTR_DISCOUNT_CENTS,
    ATTR_DISTANCE_KM,
    ATTR_EFFECTIVE_PRICE,
    ATTR_HISTORY,
    ATTR_STATION_ID,
    ATTR_SUBURB,
    ATTR_TREND_CENTS,
    ATTR_UPDATED,
    CONF_FUEL_TYPES,
    CONF_MAP_MARKER_COUNT,
    DEFAULT_MAP_MARKER_COUNT,
    DOMAIN,
    SIGNAL_SELECTION_CHANGED,
    SIGNAL_STATIONS_UPDATED,
    SORT_DISTANCE,
)
from .coordinator import FuelPriceCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: FuelPriceCoordinator = data["coordinator"]
    provider = data["provider"]
    history_store = data["history_store"]

    fuel_types = entry.data.get(CONF_FUEL_TYPES, [])
    entities = [
        LowestFuelPriceSensor(coordinator, entry, ft, provider.fuel_types.get(ft, ft), history_store)
        for ft in fuel_types
    ]

    selection = data["selection"]
    marker_count = entry.options.get(
        CONF_MAP_MARKER_COUNT, entry.data.get(CONF_MAP_MARKER_COUNT, DEFAULT_MAP_MARKER_COUNT)
    )
    entities += [
        RankedStationSensor(hass, entry, coordinator, selection, rank)
        for rank in range(1, marker_count + 1)
    ]

    async_add_entities(entities)


class LowestFuelPriceSensor(CoordinatorEntity[FuelPriceCoordinator], SensorEntity):
    """Cheapest currently-known price for one fuel type within the radius."""

    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = "c/L"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:currency-usd"

    def __init__(self, coordinator, entry: ConfigEntry, fuel_type: str, label: str, history_store) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._fuel_type = fuel_type
        self._history_store = history_store
        self._attr_name = f"{label} lowest price"
        self._attr_unique_id = f"{entry.entry_id}_{fuel_type}_lowest_price"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Fuel Price Map",
        )

    @property
    def _cheapest(self):
        stations = self.coordinator.data.get(self._fuel_type) or []
        return stations[0] if stations else None

    @property
    def native_value(self):
        station = self._cheapest
        return station.price_cents if station else None

    @property
    def extra_state_attributes(self) -> dict:
        station = self._cheapest
        attrs: dict = {
            ATTR_HISTORY: self._history_store.get_history(self._fuel_type),
        }
        if station:
            attrs.update(
                {
                    ATTR_STATION_ID: station.station_id,
                    "station_name": station.name,
                    ATTR_BRAND: station.brand,
                    ATTR_DISCOUNT_CENTS: station.discount_cents,
                    ATTR_EFFECTIVE_PRICE: station.effective_price_cents,
                    ATTR_ADDRESS: station.address,
                    ATTR_SUBURB: station.suburb,
                    "latitude": station.latitude,
                    "longitude": station.longitude,
                    ATTR_DISTANCE_KM: round(station.distance_km, 2) if station.distance_km else None,
                    ATTR_UPDATED: station.updated,
                }
            )
        return attrs


class RankedStationSensor(SensorEntity):
    """One of a small fixed set of 'live' map-marker sensors.

    Entity IDs are fixed (sensor.<domain>_rank_1, _rank_2, ...) regardless of
    which fuel type or brand is currently selected -- only the *values*
    change. This lets a static map card config (e.g. ha-map-card, which
    takes a fixed `entities:` list) show multiple nearby stations without
    needing to be reconfigured every time the fuel type dropdown changes,
    and without creating one sensor per station.
    """

    _attr_should_poll = False
    _attr_native_unit_of_measurement = "c/L"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:map-marker"

    def __init__(self, hass, entry: ConfigEntry, coordinator, selection, rank: int) -> None:
        self.hass = hass
        self._entry = entry
        self._coordinator = coordinator
        self._selection = selection
        self._rank = rank
        self._station = None
        self._attr_unique_id = f"{entry.entry_id}_rank_{rank}"
        self.entity_id = f"sensor.{DOMAIN}_rank_{rank}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Fuel Price Map",
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_STATIONS_UPDATED, self._handle_update)
        )
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_SELECTION_CHANGED, self._handle_update)
        )
        self._refresh()

    @callback
    def _handle_update(self, *_args) -> None:
        self._refresh()
        self.async_write_ha_state()

    def _refresh(self) -> None:
        stations = list(self._coordinator.data.get(self._selection.fuel_type) or [])
        if self._selection.brand and self._selection.brand != ANY_BRAND:
            stations = [s for s in stations if s.brand == self._selection.brand]
        if self._selection.sort_order == SORT_DISTANCE:
            stations.sort(key=lambda s: s.distance_km if s.distance_km is not None else float("inf"))
        # else: already price-sorted by the coordinator
        self._station = stations[self._rank - 1] if len(stations) >= self._rank else None

    @property
    def name(self) -> str:
        if self._station:
            # Don't prepend brand - FuelWatch trading names (station.name)
            # usually already include it (e.g. "OMG Metro Yangebup"),
            # which caused duplicated names like "#2 OMG Metro OMG Metro
            # Yangebup". Brand is still available as its own attribute.
            return f"#{self._rank} {self._station.name}"
        return f"Map marker {self._rank} (no station)"

    def _build_map_label(self) -> str:
        station = self._station
        label = f"{station.effective_price_cents:.1f}\u00a2"
        if station.discount_cents:
            label += "*"
        trend = station.trend_cents
        if trend is not None and abs(trend) >= 0.05:
            label += " \u25b2" if trend > 0 else " \u25bc"  # up-triangle / down-triangle
        return label

    @property
    def native_value(self):
        return self._station.price_cents if self._station else None

    @property
    def extra_state_attributes(self) -> dict:
        if not self._station:
            return {"latitude": None, "longitude": None, "rank": self._rank}
        return {
            "latitude": self._station.latitude,
            "longitude": self._station.longitude,
            "price": self._station.price_cents,
            ATTR_DISCOUNT_CENTS: self._station.discount_cents,
            ATTR_EFFECTIVE_PRICE: self._station.effective_price_cents,
            ATTR_TREND_CENTS: self._station.trend_cents,
            "map_label": self._build_map_label(),
            ATTR_BRAND: self._station.brand,
            ATTR_ADDRESS: self._station.address,
            ATTR_SUBURB: self._station.suburb,
            ATTR_DISTANCE_KM: round(self._station.distance_km, 2) if self._station.distance_km else None,
            ATTR_UPDATED: self._station.updated,
            "fuel_type": self._station.fuel_type,
            "rank": self._rank,
        }
