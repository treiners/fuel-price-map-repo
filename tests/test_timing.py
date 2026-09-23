from datetime import datetime
import importlib.util
from pathlib import Path
import unittest

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


class FuelWatchTimingTests(unittest.TestCase):
    def test_feed_window_uses_perth_time(self):
        before = datetime.fromisoformat("2026-09-23T13:05:00+08:00")
        after = datetime.fromisoformat("2026-09-23T14:05:00+08:00")
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


if __name__ == "__main__":
    unittest.main()
