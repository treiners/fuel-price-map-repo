"""Pure FuelWatch timing helpers."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

PERTH_TZ = ZoneInfo("Australia/Perth")
TOMORROW_FEED_START_HOUR = 14


def perth_now(now: datetime | None = None) -> datetime:
    """Return the current time in Perth, regardless of HA host timezone."""
    if now is None:
        return datetime.now(PERTH_TZ)
    if now.tzinfo is None:
        now = now.replace(tzinfo=PERTH_TZ)
    return now.astimezone(PERTH_TZ)


def perth_today(now: datetime | None = None) -> date:
    return perth_now(now).date()


def tomorrow_feed_allowed(now: datetime | None = None) -> bool:
    """FuelWatch's tomorrow feed is expected after 14:00 Perth time."""
    return perth_now(now).hour >= TOMORROW_FEED_START_HOUR


def expected_tomorrow_date(now: datetime | None = None) -> date:
    return perth_today(now) + timedelta(days=1)


def feed_date_is_tomorrow(feed_date: str, now: datetime | None = None) -> bool:
    """Validate the feed's date field instead of trusting request timing."""
    try:
        return date.fromisoformat(feed_date[:10]) == expected_tomorrow_date(now)
    except (TypeError, ValueError):
        return False
