"""Constants for the Fuel Price Map integration."""
from __future__ import annotations

DOMAIN = "fuel_price_map"

PLATFORMS = ["sensor", "select", "geo_location"]

# ---------------------------------------------------------------------------
# Config / options keys
# ---------------------------------------------------------------------------
CONF_PROVIDER = "provider"
CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"
CONF_RADIUS_KM = "radius_km"
CONF_FUEL_TYPES = "fuel_types"
CONF_EXCLUDED_BRANDS = "excluded_brands"
CONF_MAX_STATIONS = "max_stations"
CONF_UPDATE_TIMES = "update_times"  # list of "HH:MM" strings, max 2/day
CONF_HISTORY_DAYS = "history_days"
CONF_MAP_MARKER_COUNT = "map_marker_count"
DEFAULT_MAP_MARKER_COUNT = 10
CONF_BRAND_DISCOUNTS = "brand_discounts"  # dict[str, float] - brand name -> cents/L
DEFAULT_BRAND_DISCOUNTS: dict = {}

DEFAULT_RADIUS_KM = 10
DEFAULT_MAX_STATIONS = 25
DEFAULT_UPDATE_TIMES = ["07:00", "16:00"]
DEFAULT_HISTORY_DAYS = 14
DEFAULT_EXCLUDED_BRANDS = ["Costco"]

PROVIDER_FUELWATCH_WA = "fuelwatch_wa"
PROVIDERS = {
    PROVIDER_FUELWATCH_WA: "FuelWatch (Western Australia)",
}

# ---------------------------------------------------------------------------
# FuelWatch WA reference data
# Source: https://www.fuelwatch.wa.gov.au (public RSS feed), field codes taken
# from published FuelWatch RSS docs / open-source clients.
# ---------------------------------------------------------------------------
FUELWATCH_PRODUCTS = {
    "1": "Unleaded Petrol",
    "2": "Premium Unleaded",
    "4": "Diesel",
    "5": "LPG",
    "6": "98 RON",
    "10": "E85",
    "11": "Brand Diesel",
}

FUELWATCH_BRANDS = {
    "2": "Ampol",
    "3": "Better Choice",
    "4": "BOC",
    "5": "BP",
    "6": "Caltex",
    "7": "Gull",
    "8": "Kleenheat",
    "9": "Kwikfuel",
    "10": "Liberty",
    "11": "Mobil",
    "13": "Peak",
    "14": "Shell",
    "15": "Independent",
    "19": "Caltex Woolworths",
    "20": "Coles Express",
    "23": "United",
    "24": "Eagle",
    "25": "FastFuel 24/7",
    "26": "Puma",
    "27": "Vibe",
    "29": "7-Eleven",
    "30": "Metro Petroleum",
    "31": "WA Fuels",
    "32": "Costco",
    "33": "Mogas",
    "34": "Atlas",
    "35": "EG Ampol",
    "36": "CGL Fuel",
    "37": "X Convenience",
    "38": "Phoenix",
    "39": "Burk",
    "40": "Petro Fuels",
    "41": "Astron",
    "42": "OTR",
    "43": "Reddy Express",
    "44": "Dunning's",
    "45": "Perrys",
    "46": "UGO",
    "47": "Maisey Fuels",
}

SIGNAL_STATIONS_UPDATED = f"{DOMAIN}_stations_updated"
SIGNAL_SELECTION_CHANGED = f"{DOMAIN}_selection_changed"

ATTR_BRAND = "brand"
ATTR_ADDRESS = "address"
ATTR_SUBURB = "suburb"
ATTR_PRICE = "price"
ATTR_FUEL_TYPE = "fuel_type"
ATTR_UPDATED = "updated"
ATTR_HISTORY = "history"
ATTR_STATION_ID = "station_id"
ATTR_DISTANCE_KM = "distance_km"
ATTR_DISCOUNT_CENTS = "discount_cents"
ATTR_EFFECTIVE_PRICE = "effective_price"
ATTR_TREND_CENTS = "trend_cents"

SELECT_FUEL_TYPE = "fuel_type"
SELECT_PREFERRED_BRAND = "preferred_brand"
SELECT_SORT_ORDER = "sort_order"
ANY_BRAND = "Any"

SORT_PRICE = "price"
SORT_DISTANCE = "distance"
DEFAULT_SORT_ORDER = SORT_PRICE
