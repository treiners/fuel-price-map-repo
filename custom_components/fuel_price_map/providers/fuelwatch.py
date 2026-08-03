"""FuelWatch (Western Australia) provider.

Public RSS/XML feed, no API key required. Docs (JS-rendered, but parameters are
stable and documented by several open-source clients):
https://www.fuelwatch.wa.gov.au/tools/rss

Feed base: https://www.fuelwatch.wa.gov.au/fuelwatch/fuelWatchRSS
Params used here: Product, Suburb, Surrounding, Day
"""
from __future__ import annotations

import asyncio
import logging
import xml.etree.ElementTree as ET
from datetime import date

import aiohttp
import async_timeout

from . import StationPrice
from .suburb_lookup import nearby_suburbs

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://www.fuelwatch.wa.gov.au/fuelwatch/fuelWatchRSS"

# Maps FuelWatch's numeric Product code -> our normalised fuel_type key.
# Normalised keys are what config flow / select entities show to the user.
PRODUCT_CODE_TO_KEY = {
    "1": "unleaded",
    "2": "premium_unleaded",
    "4": "diesel",
    "5": "lpg",
    "6": "98_ron",
    "10": "e85",
    "11": "brand_diesel",
}
KEY_TO_PRODUCT_CODE = {v: k for k, v in PRODUCT_CODE_TO_KEY.items()}

FUEL_TYPE_LABELS = {
    "unleaded": "Unleaded Petrol (ULP)",
    "premium_unleaded": "Premium Unleaded",
    "diesel": "Diesel",
    "lpg": "LPG",
    "98_ron": "98 RON",
    "e85": "E85",
    "brand_diesel": "Brand Diesel",
}

# Brand id -> name, used only to pre-populate the exclude-brand list in the UI.
BRANDS = {
    "2": "Ampol", "3": "Better Choice", "4": "BOC", "5": "BP", "6": "Caltex",
    "7": "Gull", "8": "Kleenheat", "9": "Kwikfuel", "10": "Liberty",
    "11": "Mobil", "13": "Peak", "14": "Shell", "15": "Independent",
    "19": "Caltex Woolworths", "20": "Coles Express", "23": "United",
    "24": "Eagle", "25": "FastFuel 24/7", "26": "Puma", "27": "Vibe",
    "29": "7-Eleven", "30": "Metro Petroleum", "31": "WA Fuels",
    "32": "Costco", "33": "Mogas", "34": "Atlas", "35": "EG Ampol",
    "36": "CGL Fuel", "37": "X Convenience", "38": "Phoenix", "39": "Burk",
    "40": "Petro Fuels", "41": "Astron", "42": "OTR", "43": "Reddy Express",
    "44": "Dunning's", "45": "Perrys", "46": "UGO", "47": "Maisey Fuels",
}

REQUEST_TIMEOUT = 30


class FuelWatchProvider:
    """Client for the FuelWatch WA RSS feed."""

    provider_id = "fuelwatch_wa"
    fuel_types = FUEL_TYPE_LABELS
    brands = BRANDS

    def __init__(self, suburb: str | None = None) -> None:
        self._suburb = suburb

    async def async_fetch(
        self,
        *,
        session: aiohttp.ClientSession,
        fuel_type: str,
        suburb: str | None = None,
        surrounding: bool = True,
        day: str = "today",
    ) -> list[StationPrice]:
        product_code = KEY_TO_PRODUCT_CODE.get(fuel_type)
        if product_code is None:
            raise ValueError(f"Unknown fuel_type '{fuel_type}' for FuelWatch provider")

        params = {
            "Product": product_code,
            "Day": day,
        }
        use_suburb = suburb or self._suburb
        if use_suburb:
            params["Suburb"] = use_suburb
            params["Surrounding"] = "Yes" if surrounding else "No"

        try:
            async with async_timeout.timeout(REQUEST_TIMEOUT):
                async with session.get(BASE_URL, params=params) as resp:
                    resp.raise_for_status()
                    body = await resp.read()
        except (aiohttp.ClientError, TimeoutError) as err:
            _LOGGER.error("Error fetching FuelWatch feed: %s", err)
            return []

        return self._parse(body, fuel_type)

    async def async_fetch_area(
        self,
        *,
        session: aiohttp.ClientSession,
        fuel_type: str,
        latitude: float,
        longitude: float,
        radius_km: float,
        day: str = "today",
    ) -> list[StationPrice]:
        """Resolve which WA suburbs cover this area, fetch each, merge & dedupe.

        FuelWatch has no native radius query, so we use the bundled suburb
        coordinate dataset to work out which suburbs actually fall within
        radius_km (+small buffer) of the given point, then query each of
        those directly (Surrounding=No -- we're already covering the area
        ourselves, so we don't need FuelWatch's own adjacency expansion).
        """
        suburbs = nearby_suburbs(latitude, longitude, radius_km)
        if not suburbs:
            _LOGGER.warning(
                "No known FuelWatch suburbs found within %.1f km of %.5f,%.5f",
                radius_km, latitude, longitude,
            )
            return []
        if len(suburbs) > 40:
            _LOGGER.info(
                "%d suburbs in range (%.1f km) - consider a smaller radius for dense "
                "metro areas to reduce request count",
                len(suburbs), radius_km,
            )

        semaphore = asyncio.Semaphore(8)

        async def _fetch_one(suburb_name: str) -> list[StationPrice]:
            async with semaphore:
                return await self.async_fetch(
                    session=session,
                    fuel_type=fuel_type,
                    suburb=suburb_name,
                    surrounding=False,
                    day=day,
                )

        results = await asyncio.gather(
            *(_fetch_one(s) for s in suburbs), return_exceptions=True
        )

        merged: dict[str, StationPrice] = {}
        for suburb_name, res in zip(suburbs, results):
            if isinstance(res, Exception):
                _LOGGER.warning("FuelWatch fetch failed for suburb '%s': %s", suburb_name, res)
                continue
            for station in res:
                merged[station.station_id] = station

        return list(merged.values())

    def _parse(self, body: bytes, fuel_type: str) -> list[StationPrice]:
        stations: list[StationPrice] = []
        try:
            root = ET.fromstring(body)
        except ET.ParseError as err:
            _LOGGER.error("Could not parse FuelWatch XML: %s", err)
            return stations

        for item in root.iter("item"):
            fields: dict[str, str] = {}
            for child in item:
                tag = child.tag.lower().replace("-", "_")
                fields[tag] = (child.text or "").strip()

            try:
                lat = float(fields.get("latitude", ""))
                lon = float(fields.get("longitude", ""))
                price = float(fields.get("price", ""))
            except ValueError:
                # Skip malformed / incomplete entries rather than failing the batch
                continue

            name = fields.get("trading_name") or fields.get("title", "Unknown station")
            brand = fields.get("brand", "Unknown")
            suburb_name = fields.get("location", "")
            address = fields.get("address", "")
            updated = fields.get("date", date.today().isoformat())
            station_id = f"{name}_{suburb_name}".lower().replace(" ", "_")

            stations.append(
                StationPrice(
                    station_id=station_id,
                    name=name,
                    brand=brand,
                    address=address,
                    suburb=suburb_name,
                    latitude=lat,
                    longitude=lon,
                    fuel_type=fuel_type,
                    price_cents=price,
                    updated=updated,
                )
            )

        return stations
