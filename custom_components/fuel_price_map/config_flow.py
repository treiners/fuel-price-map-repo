"""Config flow for Fuel Price Map."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TimeSelector,
)

from .const import (
    CONF_BRAND_DISCOUNTS,
    CONF_EXCLUDED_BRANDS,
    CONF_FUEL_TYPES,
    CONF_HISTORY_DAYS,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_MAP_MARKER_COUNT,
    CONF_MAX_STATIONS,
    CONF_PROVIDER,
    CONF_RADIUS_KM,
    CONF_UPDATE_TIMES,
    DEFAULT_BRAND_DISCOUNTS,
    DEFAULT_EXCLUDED_BRANDS,
    DEFAULT_HISTORY_DAYS,
    DEFAULT_MAP_MARKER_COUNT,
    DEFAULT_MAX_STATIONS,
    DEFAULT_RADIUS_KM,
    DEFAULT_UPDATE_TIMES,
    DOMAIN,
    PROVIDER_FUELWATCH_WA,
    PROVIDERS,
)
from .providers.fuelwatch import BRANDS as FUELWATCH_BRANDS
from .providers.fuelwatch import FUEL_TYPE_LABELS as FUELWATCH_FUEL_TYPES


def _provider_fuel_types(provider_id: str) -> dict[str, str]:
    if provider_id == PROVIDER_FUELWATCH_WA:
        return FUELWATCH_FUEL_TYPES
    return {}


def _provider_brand_names(provider_id: str) -> list[str]:
    if provider_id == PROVIDER_FUELWATCH_WA:
        return sorted(FUELWATCH_BRANDS.values())
    return []


class FuelPriceMapConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the initial setup."""

    VERSION = 1

    def __init__(self) -> None:
        self._provider: str = PROVIDER_FUELWATCH_WA

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            self._provider = user_input[CONF_PROVIDER]
            return await self.async_step_location()

        schema = vol.Schema(
            {
                vol.Required(CONF_PROVIDER, default=PROVIDER_FUELWATCH_WA): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {"value": k, "label": v} for k, v in PROVIDERS.items()
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_location(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            self._location_data = user_input
            return await self.async_step_fuel()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_LATITUDE, default=self.hass.config.latitude
                ): vol.Coerce(float),
                vol.Required(
                    CONF_LONGITUDE, default=self.hass.config.longitude
                ): vol.Coerce(float),
                # No suburb needed -- the provider resolves which suburbs/
                # regions to query internally from the coordinate + radius.
                vol.Required(CONF_RADIUS_KM, default=DEFAULT_RADIUS_KM): vol.Coerce(float),
            }
        )
        return self.async_show_form(step_id="location", data_schema=schema, errors=errors)

    async def async_step_fuel(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        fuel_options = _provider_fuel_types(self._provider)
        brand_options = _provider_brand_names(self._provider)

        if user_input is not None:
            data = {
                CONF_PROVIDER: self._provider,
                **self._location_data,
                CONF_FUEL_TYPES: user_input[CONF_FUEL_TYPES],
                CONF_EXCLUDED_BRANDS: user_input.get(CONF_EXCLUDED_BRANDS, []),
                CONF_MAX_STATIONS: DEFAULT_MAX_STATIONS,
                CONF_UPDATE_TIMES: DEFAULT_UPDATE_TIMES,
                CONF_HISTORY_DAYS: DEFAULT_HISTORY_DAYS,
            }
            lat = self._location_data[CONF_LATITUDE]
            lon = self._location_data[CONF_LONGITUDE]
            title = f"Fuel Price Map ({lat:.3f}, {lon:.3f})"
            return self.async_create_entry(title=title, data=data)

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_FUEL_TYPES, default=list(fuel_options.keys())
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {"value": k, "label": v} for k, v in fuel_options.items()
                        ],
                        multiple=True,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    CONF_EXCLUDED_BRANDS, default=DEFAULT_EXCLUDED_BRANDS
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=brand_options, multiple=True, mode=SelectSelectorMode.DROPDOWN
                    )
                ),
            }
        )
        return self.async_show_form(step_id="fuel", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return FuelPriceMapOptionsFlow()


class FuelPriceMapOptionsFlow(config_entries.OptionsFlow):
    """Adjust general settings and manage per-brand discounts.

    Structure: async_step_init shows a MENU (general / discounts / finish)
    rather than a form. Choosing a menu option calls the matching
    async_step_<option>() with no input - that's just how HA's menu step
    works. All edits accumulate in self._pending (a plain dict, seeded once
    from the current entry) across as many round trips through the menu as
    needed; nothing is actually saved until "Finish" calls async_create_entry
    - exactly once, for the whole flow. This is the standard HA pattern for
    "manage a repeatable list of things" options flows.

    Note: no config_entry stored here - since HA 2025.12, self.config_entry
    is provided automatically by the base class, and manually assigning it
    raises AttributeError (it's a read-only property now).
    """

    def __init__(self) -> None:
        self._pending: dict[str, Any] | None = None

    def _ensure_pending(self) -> dict[str, Any]:
        if self._pending is None:
            self._pending = {**self.config_entry.data, **self.config_entry.options}
            self._pending.setdefault(CONF_BRAND_DISCOUNTS, dict(DEFAULT_BRAND_DISCOUNTS))
        return self._pending

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        self._ensure_pending()
        return self.async_show_menu(
            step_id="init",
            menu_options=["general", "discounts", "finish"],
        )

    async def async_step_finish(self, user_input: dict[str, Any] | None = None):
        return self.async_create_entry(title="", data=self._ensure_pending())

    # ------------------------------------------------------------------
    # General settings (the original single form, unchanged in content -
    # just reads/writes self._pending instead of current/create_entry
    # directly, and returns to the menu instead of finishing the flow).
    # ------------------------------------------------------------------
    async def async_step_general(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        current = self._ensure_pending()
        provider = current.get(CONF_PROVIDER, PROVIDER_FUELWATCH_WA)
        brand_options = _provider_brand_names(provider)

        if user_input is not None:
            times = [user_input["update_time_1"][:5]]
            if user_input.get("update_time_2"):
                times.append(user_input["update_time_2"][:5])
            self._pending.update(
                {
                    CONF_RADIUS_KM: user_input[CONF_RADIUS_KM],
                    CONF_EXCLUDED_BRANDS: user_input.get(CONF_EXCLUDED_BRANDS, []),
                    CONF_MAX_STATIONS: user_input[CONF_MAX_STATIONS],
                    CONF_MAP_MARKER_COUNT: user_input[CONF_MAP_MARKER_COUNT],
                    CONF_UPDATE_TIMES: times,
                    CONF_HISTORY_DAYS: user_input[CONF_HISTORY_DAYS],
                }
            )
            return await self.async_step_init()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_RADIUS_KM, default=current.get(CONF_RADIUS_KM, DEFAULT_RADIUS_KM)
                ): vol.Coerce(float),
                vol.Optional(
                    CONF_EXCLUDED_BRANDS,
                    default=current.get(CONF_EXCLUDED_BRANDS, DEFAULT_EXCLUDED_BRANDS),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=brand_options, multiple=True, mode=SelectSelectorMode.DROPDOWN
                    )
                ),
                vol.Required(
                    CONF_MAX_STATIONS,
                    default=current.get(CONF_MAX_STATIONS, DEFAULT_MAX_STATIONS),
                ): vol.Coerce(int),
                vol.Required(
                    CONF_MAP_MARKER_COUNT,
                    default=current.get(CONF_MAP_MARKER_COUNT, DEFAULT_MAP_MARKER_COUNT),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=50)),
                vol.Required(
                    "update_time_1",
                    default=current.get(CONF_UPDATE_TIMES, DEFAULT_UPDATE_TIMES)[0],
                ): TimeSelector(),
                vol.Optional(
                    "update_time_2",
                    default=(
                        current.get(CONF_UPDATE_TIMES, DEFAULT_UPDATE_TIMES)[1]
                        if len(current.get(CONF_UPDATE_TIMES, DEFAULT_UPDATE_TIMES)) > 1
                        else DEFAULT_UPDATE_TIMES[1]
                    ),
                ): TimeSelector(),
                vol.Required(
                    CONF_HISTORY_DAYS,
                    default=current.get(CONF_HISTORY_DAYS, DEFAULT_HISTORY_DAYS),
                ): vol.Coerce(int),
            }
        )
        return self.async_show_form(step_id="general", data_schema=schema, errors=errors)

    # ------------------------------------------------------------------
    # Brand discounts: menu (summary + add/remove/back) + two sub-forms.
    # ------------------------------------------------------------------
    async def async_step_discounts(self, user_input: dict[str, Any] | None = None):
        discounts: dict = self._ensure_pending().setdefault(CONF_BRAND_DISCOUNTS, {})
        summary = (
            ", ".join(f"{brand}: {cents:g}\u00a2" for brand, cents in discounts.items())
            if discounts
            else "None configured yet"
        )
        menu_options = ["discounts_add"]
        if discounts:
            menu_options.append("discounts_remove")
        menu_options.append("init")
        return self.async_show_menu(
            step_id="discounts",
            menu_options=menu_options,
            description_placeholders={"current": summary},
        )

    async def async_step_discounts_add(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        pending = self._ensure_pending()
        discounts: dict = pending.setdefault(CONF_BRAND_DISCOUNTS, {})
        provider = pending.get(CONF_PROVIDER, PROVIDER_FUELWATCH_WA)
        available = [b for b in _provider_brand_names(provider) if b not in discounts]

        if not available:
            # Every known brand already has a discount configured.
            return await self.async_step_discounts()

        if user_input is not None:
            discounts[user_input["brand"]] = float(user_input["discount_cents"])
            return await self.async_step_discounts()

        schema = vol.Schema(
            {
                vol.Required("brand"): SelectSelector(
                    SelectSelectorConfig(options=available, mode=SelectSelectorMode.DROPDOWN)
                ),
                vol.Required("discount_cents", default=4.0): NumberSelector(
                    NumberSelectorConfig(mode="box", step=0.1, unit_of_measurement="\u00a2/L")
                ),
            }
        )
        return self.async_show_form(step_id="discounts_add", data_schema=schema, errors=errors)

    async def async_step_discounts_remove(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        discounts: dict = self._ensure_pending().setdefault(CONF_BRAND_DISCOUNTS, {})

        if not discounts:
            return await self.async_step_discounts()

        if user_input is not None:
            discounts.pop(user_input["brand"], None)
            return await self.async_step_discounts()

        schema = vol.Schema(
            {
                vol.Required("brand"): SelectSelector(
                    SelectSelectorConfig(
                        options=list(discounts.keys()), mode=SelectSelectorMode.DROPDOWN
                    )
                ),
            }
        )
        return self.async_show_form(step_id="discounts_remove", data_schema=schema, errors=errors)
