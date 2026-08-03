"""Select entities used to drive the map/list filter (fuel type, brand)."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ANY_BRAND,
    CONF_EXCLUDED_BRANDS,
    CONF_FUEL_TYPES,
    DOMAIN,
    SELECT_FUEL_TYPE,
    SELECT_PREFERRED_BRAND,
    SELECT_SORT_ORDER,
    SIGNAL_SELECTION_CHANGED,
    SORT_DISTANCE,
    SORT_PRICE,
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    provider = data["provider"]
    selection = data["selection"]

    fuel_type_keys = entry.data.get(CONF_FUEL_TYPES, [])
    fuel_labels = provider.fuel_types

    excluded = {b.lower() for b in entry.data.get(CONF_EXCLUDED_BRANDS, [])}
    brand_options = [ANY_BRAND] + sorted(
        b for b in provider.brands.values() if b.lower() not in excluded
    )

    async_add_entities(
        [
            FuelTypeSelect(entry, selection, fuel_type_keys, fuel_labels),
            PreferredBrandSelect(entry, selection, brand_options),
            SortOrderSelect(entry, selection),
        ]
    )


class _BaseFuelSelect(SelectEntity):
    _attr_has_entity_name = True

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Fuel Price Map",
        )


class FuelTypeSelect(_BaseFuelSelect):
    """Which fuel type is shown on the map / lowest-price list."""

    _attr_name = "Fuel type"
    _attr_icon = "mdi:gas-station"

    def __init__(self, entry, selection, fuel_type_keys, fuel_labels) -> None:
        super().__init__(entry)
        self._selection = selection
        self._key_to_label = {k: fuel_labels.get(k, k) for k in fuel_type_keys}
        self._label_to_key = {v: k for k, v in self._key_to_label.items()}
        self._attr_unique_id = f"{entry.entry_id}_select_fuel_type"
        self._attr_options = list(self._key_to_label.values())
        if selection.fuel_type not in self._key_to_label:
            selection.fuel_type = next(iter(self._key_to_label), "")

    @property
    def current_option(self) -> str | None:
        return self._key_to_label.get(self._selection.fuel_type)

    async def async_select_option(self, option: str) -> None:
        key = self._label_to_key.get(option)
        if key is None:
            return
        self._selection.fuel_type = key
        self.async_write_ha_state()
        async_dispatcher_send(self.hass, SIGNAL_SELECTION_CHANGED)


class PreferredBrandSelect(_BaseFuelSelect):
    """Optional brand filter for the sidebar list / map ('Any' = no filter)."""

    _attr_name = "Preferred brand"
    _attr_icon = "mdi:gas-station-outline"

    def __init__(self, entry, selection, brand_options: list[str]) -> None:
        super().__init__(entry)
        self._selection = selection
        self._attr_unique_id = f"{entry.entry_id}_select_preferred_brand"
        self._attr_options = brand_options

    @property
    def current_option(self) -> str | None:
        return self._selection.brand

    async def async_select_option(self, option: str) -> None:
        self._selection.brand = option
        self.async_write_ha_state()
        async_dispatcher_send(self.hass, SIGNAL_SELECTION_CHANGED)


class SortOrderSelect(_BaseFuelSelect):
    """Whether the map's rank_1..N sensors are cheapest-first or nearest-first.

    Only affects the map's rank sensors, not the price-sorted 'cheapest
    nearby' list, which stays price-sorted since that's what it's for.
    """

    _attr_name = "Map sort order"
    _attr_icon = "mdi:sort"

    _LABELS = {SORT_PRICE: "Cheapest first", SORT_DISTANCE: "Nearest first"}
    _REVERSE = {v: k for k, v in _LABELS.items()}

    def __init__(self, entry, selection) -> None:
        super().__init__(entry)
        self._selection = selection
        self._attr_unique_id = f"{entry.entry_id}_select_sort_order"
        self._attr_options = list(self._LABELS.values())

    @property
    def current_option(self) -> str | None:
        return self._LABELS.get(self._selection.sort_order)

    async def async_select_option(self, option: str) -> None:
        key = self._REVERSE.get(option)
        if key is None:
            return
        self._selection.sort_order = key
        self.async_write_ha_state()
        async_dispatcher_send(self.hass, SIGNAL_SELECTION_CHANGED)
