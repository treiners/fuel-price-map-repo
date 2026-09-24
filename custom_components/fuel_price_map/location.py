"""Location selection helpers."""
from __future__ import annotations

from typing import Any, Mapping


def normalize_optional_entity(value: Any) -> str | None:
    """Return a usable entity ID, or omit an unset selector value."""
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def location_icon(tracker_active: bool) -> str:
    """Return the dashboard icon for the effective search-location mode."""
    return "mdi:crosshairs-gps" if tracker_active else "mdi:home-map-marker"


def entity_coordinates(state: object | None) -> tuple[float, float] | None:
    """Return valid coordinates for an available HA location state.

    Home Assistant person/device_tracker entities can expose coordinates in a
    few shapes depending on the integration: plain latitude/longitude
    attributes, a nested `location` dict, or state attributes as strings.
    """
    if state is None or getattr(state, "state", None) in {"unknown", "unavailable"}:
        return None
    attributes: Mapping[str, object] = getattr(state, "attributes", {})
    raw_lat = attributes.get("latitude")
    raw_lon = attributes.get("longitude")
    if raw_lat is None or raw_lon is None:
        location = attributes.get("location")
        if isinstance(location, Mapping):
            raw_lat = location.get("latitude")
            raw_lon = location.get("longitude")
    try:
        latitude = float(raw_lat)
        longitude = float(raw_lon)
    except (TypeError, ValueError):
        return None
    if -90 <= latitude <= 90 and -180 <= longitude <= 180:
        return latitude, longitude
    return None
