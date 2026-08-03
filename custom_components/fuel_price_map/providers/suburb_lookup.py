"""Resolve which FuelWatch suburbs fall within a radius of a coordinate.

Uses a bundled WA suburb-centroid dataset (public domain, sourced from
matthewproctor/australianpostcodes, filtered/matched to FuelWatch's own
suburb list) so no runtime geocoding calls are needed. This lets the
integration take just a raw lat/lon + radius as input -- useful now, and
means a future "current device_tracker location" source or another
state/national provider can reuse the same resolution logic.
"""
from __future__ import annotations

import json
from functools import lru_cache
from math import asin, cos, radians, sin, sqrt
from pathlib import Path

DATA_FILE = Path(__file__).parent.parent / "data" / "wa_suburb_coords.json"

# Suburbs are matched by centroid distance, but a suburb's actual area can
# extend beyond its centroid -- pad the search radius so edge suburbs aren't
# dropped just because their centroid sits slightly outside it.
DEFAULT_BUFFER_KM = 5.0


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * r * asin(sqrt(a))


@lru_cache(maxsize=1)
def _load_suburb_coords() -> dict[str, tuple[float, float]]:
    with DATA_FILE.open(encoding="utf-8") as f:
        raw = json.load(f)
    return {name: (coords[0], coords[1]) for name, coords in raw.items()}


def preload_suburb_coords() -> None:
    """Force-load and cache the suburb data. Call this via hass.async_add_executor_job
    during integration setup, so the (synchronous) file read happens off the event
    loop. Every subsequent call - including from within async code - then just
    reads the in-memory cache, not the file, which is why it's safe to call
    nearby_suburbs() directly from an async method after this has run once.
    """
    _load_suburb_coords()


def nearby_suburbs(
    latitude: float,
    longitude: float,
    radius_km: float,
    buffer_km: float = DEFAULT_BUFFER_KM,
) -> list[str]:
    """Return FuelWatch suburb names whose centroid is within radius+buffer."""
    coords = _load_suburb_coords()
    search_radius = radius_km + buffer_km
    matches = [
        name
        for name, (lat, lon) in coords.items()
        if _haversine_km(latitude, longitude, lat, lon) <= search_radius
    ]
    return matches
