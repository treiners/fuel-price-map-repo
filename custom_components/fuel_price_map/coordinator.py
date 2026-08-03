"""Fetch scheduling, filtering and history recording for Fuel Price Map."""
from __future__ import annotations

import logging
from datetime import date, timedelta
from datetime import time as dt_time
from math import asin, cos, radians, sin, sqrt

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_BRAND_DISCOUNTS,
    CONF_EXCLUDED_BRANDS,
    CONF_FUEL_TYPES,
    CONF_HISTORY_DAYS,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_RADIUS_KM,
    CONF_UPDATE_TIMES,
    DOMAIN,
    SIGNAL_STATIONS_UPDATED,
)
from .providers import FuelPriceProvider, StationPrice
from .storage import PriceHistoryStore

_LOGGER = logging.getLogger(__name__)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * r * asin(sqrt(a))


class FuelPriceCoordinator(DataUpdateCoordinator[dict[str, list[StationPrice]]]):
    """Owns the scheduled fetch and the current filtered/sorted station lists.

    self.data is a dict: fuel_type -> list[StationPrice], sorted cheapest first,
    already filtered to the configured radius and excluding configured brands.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry,
        provider: FuelPriceProvider,
        history_store: PriceHistoryStore,
    ) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN)
        self.entry = entry
        self.provider = provider
        self.history_store = history_store
        self._unsub_time_triggers: list[callable] = []
        self.data = {}
        # Cached "tomorrow" prices from the ~2:30pm-11:59pm FuelWatch window,
        # keyed by fuel_type -> {station_id: price_cents}, plus which actual
        # calendar date that cache is valid for. Checked against date.today()
        # at read time in _async_update_data, so it auto-invalidates at
        # midnight without needing an explicit clear step.
        self._tomorrow_prices: dict[str, dict[str, float]] = {}
        self._tomorrow_valid_date: date | None = None

    @property
    def options(self) -> dict:
        return {**self.entry.data, **self.entry.options}

    @property
    def fuel_types(self) -> list[str]:
        return self.options.get(CONF_FUEL_TYPES, list(self.provider.fuel_types.keys()))

    @property
    def home_coords(self) -> tuple[float, float]:
        opts = self.options
        return (
            opts.get(CONF_LATITUDE, self.hass.config.latitude),
            opts.get(CONF_LONGITUDE, self.hass.config.longitude),
        )

    def async_setup_schedule(self) -> None:
        """Register the (max two) configured daily fetch times."""
        for unsub in self._unsub_time_triggers:
            unsub()
        self._unsub_time_triggers = []

        times = self.options.get(CONF_UPDATE_TIMES, ["07:00", "16:00"])
        for time_str in times[:2]:
            try:
                hour, minute = (int(p) for p in time_str.split(":"))
            except ValueError:
                _LOGGER.warning("Invalid update time '%s', skipping", time_str)
                continue
            unsub = async_track_time_change(
                self.hass, self._scheduled_refresh, hour=hour, minute=minute, second=0
            )
            self._unsub_time_triggers.append(unsub)

        # Dedicated trigger for tomorrow's prices - FuelWatch only publishes
        # these from ~2:30pm WA time, so this is fixed and separate from the
        # user-configurable today-price schedule above, not folded into it.
        unsub = async_track_time_change(
            self.hass, self._scheduled_tomorrow_refresh, hour=14, minute=35, second=0
        )
        self._unsub_time_triggers.append(unsub)

    def async_unload(self) -> None:
        for unsub in self._unsub_time_triggers:
            unsub()
        self._unsub_time_triggers = []

    async def _scheduled_refresh(self, _now) -> None:
        await self.async_refresh()

    async def _scheduled_tomorrow_refresh(self, _now) -> None:
        await self.async_refresh_tomorrow_now()

    async def async_refresh_tomorrow_now(self) -> None:
        """Public entry point for manually triggering the tomorrow-price fetch,
        e.g. via the fuel_price_map.refresh_tomorrow_prices service - lets you
        test immediately instead of waiting for the daily 14:35 trigger."""
        await self._async_fetch_tomorrow()
        # Push the newly-cached trend data out to entities immediately,
        # rather than waiting for the next regularly-scheduled today-fetch.
        await self.async_request_refresh()

    async def _async_fetch_tomorrow(self) -> None:
        """Best-effort fetch of tomorrow's prices, with real validation.

        FuelWatch only publishes these from ~2:30pm-11:59pm WA time; outside
        that window the feed silently returns today's data again instead of
        an error. So rather than trust the 14:35 trigger timing alone, this
        checks that the returned data's own date field actually says
        tomorrow before caching anything.
        """
        session = async_get_clientsession(self.hass)
        opts = self.options
        radius_km = opts.get(CONF_RADIUS_KM, 10)
        home_lat, home_lon = self.home_coords
        expected_date = (date.today() + timedelta(days=1)).isoformat()

        any_valid = False
        for fuel_type in self.fuel_types:
            try:
                stations = await self.provider.async_fetch_area(
                    session=session,
                    fuel_type=fuel_type,
                    latitude=home_lat,
                    longitude=home_lon,
                    radius_km=radius_km,
                    day="tomorrow",
                )
            except Exception as err:  # defensive - this is a best-effort extra fetch
                _LOGGER.warning("Tomorrow-price fetch failed for %s: %s", fuel_type, err)
                continue

            if not stations:
                continue

            if not any(s.updated == expected_date for s in stations):
                _LOGGER.warning(
                    "Tomorrow-price data for %s doesn't look like tomorrow's data "
                    "yet (date field didn't match %s) - skipping. Probably outside "
                    "the ~2:30pm-11:59pm window FuelWatch publishes it in.",
                    fuel_type, expected_date,
                )
                continue

            self._tomorrow_prices[fuel_type] = {s.station_id: s.price_cents for s in stations}
            any_valid = True

        if any_valid:
            self._tomorrow_valid_date = date.today() + timedelta(days=1)
            _LOGGER.info("Tomorrow's prices fetched and validated for %s", self._tomorrow_valid_date)

    async def _async_update_data(self) -> dict[str, list[StationPrice]]:
        session = async_get_clientsession(self.hass)
        opts = self.options
        radius_km = opts.get(CONF_RADIUS_KM, 10)
        excluded_brands = {b.lower() for b in opts.get(CONF_EXCLUDED_BRANDS, [])}
        history_days = opts.get(CONF_HISTORY_DAYS, 14)
        brand_discounts = {
            b.lower(): float(v) for b, v in opts.get(CONF_BRAND_DISCOUNTS, {}).items()
        }
        home_lat, home_lon = self.home_coords
        tomorrow_is_valid = self._tomorrow_valid_date == date.today() + timedelta(days=1)

        result: dict[str, list[StationPrice]] = {}

        for fuel_type in self.fuel_types:
            stations = await self.provider.async_fetch_area(
                session=session,
                fuel_type=fuel_type,
                latitude=home_lat,
                longitude=home_lon,
                radius_km=radius_km,
            )

            tomorrow_prices = self._tomorrow_prices.get(fuel_type, {}) if tomorrow_is_valid else {}

            in_range: list[StationPrice] = []
            for s in stations:
                if s.brand.lower() in excluded_brands:
                    continue
                dist = _haversine_km(home_lat, home_lon, s.latitude, s.longitude)
                if dist <= radius_km:
                    s.distance_km = dist  # type: ignore[attr-defined]
                    s.discount_cents = brand_discounts.get(s.brand.lower(), 0.0)
                    s.tomorrow_price_cents = tomorrow_prices.get(s.station_id)
                    in_range.append(s)

            # Sort by effective (post-discount) price - the raw pump price
            # (price_cents) is still what's displayed, discount is shown
            # alongside it rather than baked invisibly into "the" price.
            in_range.sort(key=lambda s: s.effective_price_cents)
            result[fuel_type] = in_range

            if in_range:
                cheapest = in_range[0]
                await self.history_store.async_add_reading(
                    fuel_type,
                    price=cheapest.price_cents,
                    discount_cents=cheapest.discount_cents,
                    station=cheapest.name,
                    brand=cheapest.brand,
                    address=cheapest.address,
                    latitude=cheapest.latitude,
                    longitude=cheapest.longitude,
                    history_days=history_days,
                )

        async_dispatcher_send(self.hass, SIGNAL_STATIONS_UPDATED)
        return result
