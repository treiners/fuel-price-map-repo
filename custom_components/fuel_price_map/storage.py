"""Lightweight rolling history store for the cheapest price per fuel type.

We deliberately do NOT rely on the HA recorder/long-term-statistics for this,
because that would mean either (a) one recorded entity per station (too many),
or (b) losing the per-reading station identity (name/brand/address) that the
history card wants to show. Instead we keep a small hand-rolled JSON store,
capped at `max_points` per fuel type, which comfortably covers "14 days,
max 2 measurements per day" (28 points) with negligible storage cost.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN

STORAGE_VERSION = 1


class PriceHistoryStore:
    """Persists rolling price history per fuel type across HA restarts."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store = Store(hass, STORAGE_VERSION, f"{DOMAIN}_{entry_id}_history")
        self._data: dict[str, list[dict[str, Any]]] = {}
        self._loaded = False

    async def async_load(self) -> None:
        stored = await self._store.async_load()
        self._data = stored or {}
        self._loaded = True

    def get_history(self, fuel_type: str) -> list[dict[str, Any]]:
        return list(self._data.get(fuel_type, []))

    async def async_add_reading(
        self,
        fuel_type: str,
        *,
        price: float,
        station: str,
        brand: str,
        address: str,
        latitude: float,
        longitude: float,
        history_days: int,
        discount_cents: float = 0.0,
        max_per_day: int = 2,
    ) -> None:
        """Append a reading, trimming to `history_days` and `max_per_day`."""
        now = datetime.now()
        entry = {
            "ts": now.isoformat(timespec="seconds"),
            "price": price,
            "discount_cents": discount_cents,
            "station": station,
            "brand": brand,
            "address": address,
            "latitude": latitude,
            "longitude": longitude,
        }

        readings = self._data.setdefault(fuel_type, [])

        today_str = now.date().isoformat()
        today_count = sum(1 for r in readings if r["ts"].startswith(today_str))
        if today_count >= max_per_day:
            # Replace the most recent reading for today instead of appending
            for i in range(len(readings) - 1, -1, -1):
                if readings[i]["ts"].startswith(today_str):
                    readings[i] = entry
                    break
        else:
            readings.append(entry)

        cutoff = now - timedelta(days=history_days)
        readings[:] = [r for r in readings if datetime.fromisoformat(r["ts"]) >= cutoff]
        readings.sort(key=lambda r: r["ts"])

        await self._store.async_save(self._data)
