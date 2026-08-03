"""Provider abstraction so other state/national fuel price APIs can be added later.

Each provider is responsible only for talking to its upstream API and returning a
flat list of StationPrice records for the requested fuel type(s). Everything else
(radius filtering, brand exclusion, sorting, history) is handled generically by
the coordinator so it works the same regardless of provider.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(slots=True)
class StationPrice:
    """A single station/fuel-type price reading, normalised across providers."""

    station_id: str
    name: str
    brand: str
    address: str
    suburb: str
    latitude: float
    longitude: float
    fuel_type: str  # normalised key, e.g. "unleaded", "diesel"
    price_cents: float
    updated: str  # ISO date/time as supplied by provider
    distance_km: float | None = None  # filled in by the coordinator
    discount_cents: float = 0.0  # filled in by the coordinator, from configured brand discounts
    tomorrow_price_cents: float | None = None  # filled in by the coordinator, from the ~2:30pm feed

    @property
    def effective_price_cents(self) -> float:
        """Price after any configured brand discount - what ranking/sorting uses.
        native display (the actual pump price) should still use price_cents."""
        return self.price_cents - self.discount_cents

    @property
    def trend_cents(self) -> float | None:
        """Tomorrow's price minus today's, or None if no valid tomorrow data yet."""
        if self.tomorrow_price_cents is None:
            return None
        return round(self.tomorrow_price_cents - self.price_cents, 2)


class FuelPriceProvider(Protocol):
    """Interface every provider module must implement."""

    provider_id: str
    #: normalised_fuel_type -> human readable label, shown in config flow / select
    fuel_types: dict[str, str]
    #: brand_id -> human readable brand name (for exclude-brand UI)
    brands: dict[str, str]

    async def async_fetch(
        self,
        *,
        session,
        fuel_type: str,
        suburb: str | None = None,
        surrounding: bool = True,
        day: str = "today",
    ) -> list[StationPrice]:
        """Fetch current prices for a single normalised fuel type."""
        ...

    async def async_fetch_area(
        self,
        *,
        session,
        fuel_type: str,
        latitude: float,
        longitude: float,
        radius_km: float,
        day: str = "today",
    ) -> list[StationPrice]:
        """Fetch prices covering a lat/lon + radius, however the provider needs to.

        This is what the coordinator calls -- it stays provider-agnostic. A
        suburb/region-based feed (FuelWatch) resolves and merges several
        queries internally here; a provider with native geo/radius search
        would just call its API directly with latitude/longitude/radius_km.
        The coordinator still applies its own exact-radius trim afterwards,
        so providers may return a slightly wider set than requested.
        """
        ...
