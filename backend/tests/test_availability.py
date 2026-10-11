from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from app.domain.availability import Interval, Occupancy, Rules, Window, get_available_slots

DAY = date(2026, 10, 13)  # Tuesday.
NOW = datetime(2026, 10, 11, tzinfo=UTC)
BASE = Rules(
    timezone="Asia/Kolkata",
    windows=(Window(1, time(9), time(12)),),
    buffer_before_minutes=0,
    buffer_after_minutes=0,
    notice_minutes=0,
)


def generate(rules=BASE, occupancy=Occupancy(), **kwargs):
    return get_available_slots(
        rules,
        occupancy,
        start_date=kwargs.pop("start_date", DAY),
        end_date=kwargs.pop("end_date", DAY),
        invitee_timezone=kwargs.pop("zone", "Asia/Kolkata"),
        duration_minutes=kwargs.pop("duration", 45),
        now=kwargs.pop("now", NOW),
        **kwargs,
    )


def local_interval(start: int, end: int):
    zone = ZoneInfo("Asia/Kolkata")
    return Interval(
        datetime.combine(DAY, time(start), zone), datetime.combine(DAY, time(end), zone)
    )


def test_duration_and_half_open_boundaries():
    short, long = generate(duration=30), generate(duration=60)
    assert len(short) == 11
    assert len(long) == 9
    assert short[0].start == datetime(2026, 10, 13, 3, 30, tzinfo=UTC)
    assert short[-1].end == datetime(2026, 10, 13, 6, 30, tzinfo=UTC)


@pytest.mark.parametrize("field", ["busy", "reservations", "focus", "invitee_busy"])
def test_each_exclusion_blocks_overlap_but_allows_touching(field):
    blocker = local_interval(10, 11)
    slots = generate(occupancy=Occupancy(**{field: (blocker,)}), duration=30)
    assert slots
    assert all(not slot.overlaps(blocker) for slot in slots)
    assert any(slot.end == blocker.start for slot in slots)
    assert any(slot.start == blocker.end for slot in slots)


def test_buffers_fit_working_hours_and_avoid_busy_periods():
    rules = replace(BASE, buffer_before_minutes=10, buffer_after_minutes=15)
    busy = local_interval(10, 11)
    slots = generate(rules, Occupancy(busy=(busy,)), duration=30)
    assert slots[0].start == datetime(2026, 10, 13, 3, 45, tzinfo=UTC)
    for slot in slots:
        blocked = Interval(slot.start - timedelta(minutes=10), slot.end + timedelta(minutes=15))
        assert not blocked.overlaps(busy)
        assert blocked.end <= datetime(2026, 10, 13, 6, 30, tzinfo=UTC)


def test_notice_boundary_is_inclusive():
    rules = replace(BASE, notice_minutes=60)
    now = datetime(2026, 10, 13, 3, 30, tzinfo=UTC)
    slots = generate(rules, now=now)
    assert slots[0].start == now + timedelta(hours=1)


@pytest.mark.parametrize(
    "occupancy",
    [
        Occupancy(event_counts={DAY: 3}),
        Occupancy(host_counts={DAY: 4}),
        Occupancy(week_minutes={date(2026, 10, 12): 700}),
    ],
)
def test_caps_hide_slots(occupancy):
    assert generate(occupancy=occupancy) == []


def test_weekly_cap_accepts_exact_limit():
    assert generate(occupancy=Occupancy(week_minutes={date(2026, 10, 12): 675}))


def test_horizon_checks_end_not_only_start():
    assert generate(replace(BASE, horizon_days=1)) == []


def test_kathmandu_quarter_hour_offset_does_not_shift_instant():
    slots = generate(zone="Asia/Kathmandu")
    assert slots == generate()
    assert slots[0].start.astimezone(ZoneInfo("Asia/Kathmandu")).strftime("%H:%M") == "09:15"


def test_request_dates_use_invitee_zone_at_day_boundary():
    rules = replace(BASE, timezone="Asia/Kathmandu", windows=(Window(1, time(0), time(1)),))
    monday = date(2026, 10, 12)
    slots = generate(
        rules, start_date=monday, end_date=monday, zone="America/New_York", duration=30
    )
    assert slots
    assert all(
        slot.start.astimezone(ZoneInfo("America/New_York")).date() == monday for slot in slots
    )
    assert all(slot.start.astimezone(ZoneInfo("Asia/Kathmandu")).date() == DAY for slot in slots)


def test_spring_dst_gap_is_skipped():
    day = date(2026, 3, 8)
    rules = replace(BASE, timezone="America/New_York", windows=(Window(6, time(1), time(4)),))
    slots = generate(
        rules,
        start_date=day,
        end_date=day,
        zone=rules.timezone,
        duration=30,
        now=datetime(2026, 3, 7, tzinfo=UTC),
    )
    assert slots
    assert all(slot.start.astimezone(ZoneInfo(rules.timezone)).hour != 2 for slot in slots)
    assert len({slot.start for slot in slots}) == len(slots)


def test_fall_dst_fold_keeps_distinct_real_instants():
    day = date(2026, 11, 1)
    rules = replace(BASE, timezone="America/New_York", windows=(Window(6, time(1), time(3)),))
    slots = generate(
        rules,
        start_date=day,
        end_date=day,
        zone=rules.timezone,
        duration=30,
        now=datetime(2026, 10, 31, tzinfo=UTC),
    )
    ones = [
        slot.start for slot in slots if slot.start.astimezone(ZoneInfo(rules.timezone)).hour == 1
    ]
    assert len(ones) == 8
    assert len(set(ones)) == 8
    assert {instant.astimezone(ZoneInfo(rules.timezone)).fold for instant in ones} == {0, 1}


def test_duplicate_schedule_windows_do_not_duplicate_slots():
    assert generate(replace(BASE, windows=BASE.windows * 2)) == generate()


@pytest.mark.parametrize(
    "changes",
    [
        {"end_date": date(2026, 10, 12)},
        {"end_date": date(2027, 1, 1)},
        {"now": datetime(2026, 10, 11)},
        {"duration": 0},
    ],
)
def test_invalid_inputs(changes):
    with pytest.raises(ValueError):
        generate(**changes)
