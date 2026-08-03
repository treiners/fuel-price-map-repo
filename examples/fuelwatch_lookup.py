#!/usr/bin/env python3
"""
fuelwatch_lookup.py - look up WA FuelWatch fuel prices from the terminal.

No dependencies beyond the Python standard library - just run it with
python3. Data source: https://www.fuelwatch.wa.gov.au (public RSS feed,
free, no API key required).

Examples:
    python3 fuelwatch_lookup.py
    python3 fuelwatch_lookup.py --suburb Hilton --brand Caltex --fuel ulp
    python3 fuelwatch_lookup.py --suburb Fremantle --brand any --fuel diesel
    python3 fuelwatch_lookup.py --suburb Hilton --brand Caltex --no-surrounding
"""
from __future__ import annotations

import argparse
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

BASE_URL = "https://www.fuelwatch.wa.gov.au/fuelwatch/fuelWatchRSS"

FUEL_TYPES = {
    "ulp": "1",
    "premium": "2",
    "diesel": "4",
    "lpg": "5",
    "98": "6",
    "e85": "10",
    "branddiesel": "11",
}


def fetch_prices(suburb: str, product_code: str, surrounding: bool) -> list[dict]:
    """Fetch and parse the raw FuelWatch RSS feed into a list of field dicts."""
    params = {
        "Product": product_code,
        "Suburb": suburb,
        "Surrounding": "Yes" if surrounding else "No",
        "Day": "today",  # only "today" actually works - see note below
    }
    url = f"{BASE_URL}?{urllib.parse.urlencode(params)}"

    req = urllib.request.Request(url, headers={"User-Agent": "fuelwatch-lookup/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = resp.read()

    root = ET.fromstring(body)
    stations = []
    for item in root.iter("item"):
        fields: dict[str, str] = {}
        for child in item:
            tag = child.tag.lower().replace("-", "_")
            fields[tag] = (child.text or "").strip()
        stations.append(fields)
    return stations


def main() -> int:
    parser = argparse.ArgumentParser(description="Look up WA FuelWatch prices from the terminal.")
    parser.add_argument("--suburb", default="Hilton", help="Suburb to search (default: Hilton)")
    parser.add_argument(
        "--brand",
        default="Caltex",
        help="Brand to filter by, case-insensitive (default: Caltex). Use 'any' for no filter.",
    )
    parser.add_argument(
        "--fuel", default="ulp", choices=sorted(FUEL_TYPES), help="Fuel type (default: ulp)"
    )
    parser.add_argument(
        "--no-surrounding",
        action="store_true",
        help="Only the exact suburb, not neighbouring suburbs (default includes neighbours)",
    )
    args = parser.parse_args()

    try:
        stations = fetch_prices(
            args.suburb, FUEL_TYPES[args.fuel], surrounding=not args.no_surrounding
        )
    except Exception as exc:  # network error, bad XML, etc.
        print(f"Error fetching FuelWatch data: {exc}", file=sys.stderr)
        return 1

    if args.brand.lower() != "any":
        stations = [s for s in stations if s.get("brand", "").lower() == args.brand.lower()]

    if not stations:
        print(f"No {args.brand} stations found for {args.fuel.upper()} near {args.suburb}.")
        return 0

    stations.sort(key=lambda s: float(s.get("price", "999")))

    title = f"{args.brand} - {args.fuel.upper()} - near {args.suburb}"
    print(title)
    print("-" * len(title))
    for s in stations:
        price = s.get("price", "?")
        name = s.get("trading_name") or s.get("title", "Unknown")
        address = s.get("address", "")
        suburb = s.get("location", "")
        print(f"{price:>6}\u00a2  {name}")
        print(f"          {address}, {suburb}")
    print("-" * len(title))
    print(f"{len(stations)} station(s) found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
