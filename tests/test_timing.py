from datetime import datetime
import importlib.util
import json
from pathlib import Path
import unittest
import yaml

_TIMING_PATH = (
    Path(__file__).parents[1]
    / "custom_components"
    / "fuel_price_map"
    / "timing.py"
)
_SPEC = importlib.util.spec_from_file_location("fuel_price_map_timing", _TIMING_PATH)
assert _SPEC and _SPEC.loader
_TIMING = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_TIMING)

expected_tomorrow_date = _TIMING.expected_tomorrow_date
feed_date_is_tomorrow = _TIMING.feed_date_is_tomorrow
tomorrow_feed_allowed = _TIMING.tomorrow_feed_allowed

_LOCATION_SPEC = importlib.util.spec_from_file_location(
    "fuel_price_map_location",
    Path(__file__).parents[1] / "custom_components" / "fuel_price_map" / "location.py",
)
assert _LOCATION_SPEC and _LOCATION_SPEC.loader
_LOCATION = importlib.util.module_from_spec(_LOCATION_SPEC)
_LOCATION_SPEC.loader.exec_module(_LOCATION)


class FuelWatchTimingTests(unittest.TestCase):
    def test_feed_window_uses_perth_time(self):
        just_before = datetime.fromisoformat("2026-09-23T13:59:00+08:00")
        at_threshold = datetime.fromisoformat("2026-09-23T14:00:00+08:00")
        before = datetime.fromisoformat("2026-09-23T13:05:00+08:00")
        after = datetime.fromisoformat("2026-09-23T14:05:00+08:00")
        self.assertFalse(tomorrow_feed_allowed(just_before))
        self.assertTrue(tomorrow_feed_allowed(at_threshold))
        self.assertFalse(tomorrow_feed_allowed(before))
        self.assertTrue(tomorrow_feed_allowed(after))

    def test_host_timezone_does_not_change_expected_date(self):
        perth_evening = datetime.fromisoformat("2026-09-23T23:05:00+08:00")
        utc_same_instant = datetime.fromisoformat("2026-09-23T15:05:00+00:00")
        self.assertEqual(expected_tomorrow_date(perth_evening), expected_tomorrow_date(utc_same_instant))

    def test_feed_date_must_match_perth_tomorrow(self):
        now = datetime.fromisoformat("2026-09-23T14:05:00+08:00")
        self.assertTrue(feed_date_is_tomorrow("2026-09-24", now))
        self.assertTrue(feed_date_is_tomorrow("2026-09-24T00:00:00+08:00", now))
        self.assertFalse(feed_date_is_tomorrow("2026-09-23", now))
        self.assertFalse(feed_date_is_tomorrow("not-a-date", now))

    def test_location_coordinates_require_available_valid_state(self):
        state = type(
            "State",
            (),
            {"state": "home", "attributes": {"latitude": "-31.95", "longitude": "115.86"}},
        )()
        self.assertEqual(_LOCATION.entity_coordinates(state), (-31.95, 115.86))
        nested = type(
            "State",
            (),
            {"state": "home", "attributes": {"location": {"latitude": -31.95, "longitude": 115.86}}},
        )()
        self.assertEqual(_LOCATION.entity_coordinates(nested), (-31.95, 115.86))
        unavailable = type("State", (), {"state": "unknown", "attributes": {}})()
        self.assertIsNone(_LOCATION.entity_coordinates(unavailable))
        invalid = type("State", (), {"state": "home", "attributes": {"latitude": 91}})()
        self.assertIsNone(_LOCATION.entity_coordinates(invalid))

    def test_location_state_values_are_stable(self):
        state = type(
            "State",
            (),
            {"state": "home", "attributes": {"latitude": -31.95, "longitude": 115.86}},
        )()
        self.assertEqual(_LOCATION.entity_coordinates(state), (-31.95, 115.86))

    def test_optional_location_entity_is_omitted_when_unset(self):
        self.assertIsNone(_LOCATION.normalize_optional_entity(None))
        self.assertIsNone(_LOCATION.normalize_optional_entity(""))
        self.assertEqual(
            _LOCATION.normalize_optional_entity(" device_tracker.car "),
            "device_tracker.car",
        )
        self.assertEqual(_LOCATION.location_icon(False), "mdi:home-map-marker")
        self.assertEqual(_LOCATION.location_icon(True), "mdi:crosshairs-gps")

    def test_dashboard_uses_stable_select_ids_and_sections(self):
        dashboard = yaml.safe_load(
            (
                Path(__file__).parents[1] / "examples" / "example_dashboard.yaml"
            ).read_text()
        )
        fuel_view = dashboard["views"][0]
        self.assertEqual(fuel_view["type"], "panel")
        self.assertEqual(len(fuel_view["cards"]), 1)
        layout = fuel_view["cards"][0]
        self.assertEqual(layout["type"], "custom:layout-card")
        self.assertEqual(layout["layout"]["grid-template-columns"], "repeat(12, minmax(0, 1fr))")
        self.assertIn("(max-width: 700px)", layout["layout"]["mediaquery"])
        self.assertEqual(layout["cards"][0]["view_layout"]["grid-area"], "header")
        self.assertEqual(layout["cards"][2]["view_layout"]["grid-area"], "list")
        self.assertEqual(layout["cards"][3]["view_layout"]["grid-area"], "map")
        self.assertEqual(layout["cards"][4]["view_layout"]["grid-area"], "popup")
        settings = layout["cards"][4]["cards"][0]
        self.assertEqual(settings["type"], "custom:auto-entities")
        self.assertEqual(
            settings["filter"]["include"][0],
            {"integration": "fuel_price_map", "domain": "select"},
        )
        manifest = json.loads(
            (
                Path(__file__).parents[1]
                / "custom_components"
                / "fuel_price_map"
                / "manifest.json"
            ).read_text()
        )
        self.assertEqual(manifest["version"], "0.9.0")
        services = yaml.safe_load(
            (
                Path(__file__).parents[1]
                / "custom_components"
                / "fuel_price_map"
                / "services.yaml"
            ).read_text()
        )
        self.assertIn("toggle_location", services)
        init_source = (
            Path(__file__).parents[1]
            / "custom_components"
            / "fuel_price_map"
            / "__init__.py"
        ).read_text()
        self.assertIn("async def async_setup(", init_source)
        self.assertIn("_register_services(hass)", init_source)
        self.assertIn("_migrate_select_entity_ids(hass, entry)", init_source)
        self.assertIn("_async_migrate_select_entity_ids(hass, entry)", init_source)
        self.assertIn("item.config_entry_id == entry.entry_id", init_source)
        dashboard_text = (
            Path(__file__).parents[1] / "examples" / "example_dashboard.yaml"
        ).read_text()
        self.assertIn("entity: sensor.fuel_price_map_active_location", dashboard_text)
        self.assertNotIn("entity: sensor.fuel_price_map_rank_1\n                icon: mdi:crosshairs-gps", dashboard_text)
        sensor_source = (
            Path(__file__).parents[1]
            / "custom_components"
            / "fuel_price_map"
            / "sensor.py"
        ).read_text()
        location_source = (
            Path(__file__).parents[1]
            / "custom_components"
            / "fuel_price_map"
            / "location.py"
        ).read_text()
        self.assertIn("mdi:home-map-marker", location_source)
        self.assertIn("mdi:crosshairs-gps", location_source)
        self.assertIn("async_track_state_change_event", sensor_source)


if __name__ == "__main__":
    unittest.main()
