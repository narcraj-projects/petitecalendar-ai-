"""Compose saved scheduling inputs; never reserve a slot in this preview service."""

from datetime import date, time

from app.domain.availability import Occupancy, Rules, Window, get_slot_report


def schedule_rules(payload, event):
    def window(row, weekday=None):
        return Window(
            row.get("weekday", weekday if weekday is not None else 0),
            time.fromisoformat(row["start"]),
            time.fromisoformat(row["end"]),
        )

    return Rules(
        timezone=payload["timezone"],
        windows=tuple(window(w) for w in payload["weekly"]),
        focus_windows=tuple(window(w) for w in payload["focus"]),
        overrides={
            date.fromisoformat(o["date"]): tuple(window(w) for w in o["windows"])
            for o in payload["overrides"]
        },
        increment_minutes=payload["increment_minutes"],
        buffer_before_minutes=event["buffer_before"],
        buffer_after_minutes=event["buffer_after"],
        notice_minutes=event["notice_minutes"],
        horizon_days=event["horizon_days"],
        event_daily_cap=event["max_per_day"],
        host_daily_cap=payload["host_daily_cap"],
        weekly_cap_minutes=payload["weekly_cap_minutes"],
        prefer_cluster=payload["prefer_cluster"],
    )


def public_slots(row, *, start_date, end_date, timezone, duration, now, occupancy=None):
    payload = row["payload"]
    if not payload or not payload["enabled"]:
        return {
            "mode": "published",
            "timezone": timezone,
            "duration": duration,
            "slots": [],
            "explanations": ["availability_paused" if payload else "availability_not_configured"],
        }
    rules = schedule_rules(payload, row)
    report = get_slot_report(
        rules,
        occupancy or Occupancy(),
        start_date=start_date,
        end_date=end_date,
        invitee_timezone=timezone,
        duration_minutes=duration,
        now=now,
    )
    from zoneinfo import ZoneInfo

    zone = ZoneInfo(timezone)
    return {
        "mode": "published",
        "timezone": timezone,
        "host_timezone": rules.timezone,
        "duration": duration,
        "explanations": sorted(report.excluded),
        "slots": [
            {
                "start": s.start.isoformat(),
                "end": s.end.isoformat(),
                "date": s.start.astimezone(zone).date().isoformat(),
                "recommended": s.start in report.recommended,
            }
            for s in report.slots
        ],
    }
