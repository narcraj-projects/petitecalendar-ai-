"""Explicit demo adapter; no live calendar or Supabase data is claimed."""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.domain.availability import Interval, Occupancy, Rules, Window

RULES = Rules(
    timezone="Asia/Kolkata",
    windows=tuple(Window(day, time(9), time(18)) for day in range(5)),
)


def get_demo_occupancy(start: date, end: date) -> Occupancy:
    zone = ZoneInfo(RULES.timezone)
    busy, focus = [], []
    cursor = start - timedelta(days=2)
    while cursor <= end + timedelta(days=2):
        if cursor.weekday() < 5:
            focus.append(
                Interval(
                    datetime.combine(cursor, time(9), zone),
                    datetime.combine(cursor, time(11), zone),
                )
            )
            busy.append(
                Interval(
                    datetime.combine(cursor, time(13), zone),
                    datetime.combine(cursor, time(14), zone),
                )
            )
            if cursor.weekday() == 4:
                focus.append(
                    Interval(
                        datetime.combine(cursor, time(14), zone),
                        datetime.combine(cursor, time(18), zone),
                    )
                )
        cursor += timedelta(days=1)
    return Occupancy(busy=tuple(busy), focus=tuple(focus))
