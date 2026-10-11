"""UTC slot generation from local recurring schedules, without I/O."""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Interval:
    start: datetime
    end: datetime

    def overlaps(self, other: "Interval") -> bool:
        return self.start < other.end and other.start < self.end


@dataclass(frozen=True)
class Window:
    weekday: int
    start: time
    end: time


@dataclass(frozen=True)
class Rules:
    timezone: str
    windows: tuple[Window, ...]
    increment_minutes: int = 15
    buffer_before_minutes: int = 10
    buffer_after_minutes: int = 15
    notice_minutes: int = 12 * 60
    horizon_days: int = 60
    event_daily_cap: int = 3
    host_daily_cap: int = 4
    weekly_cap_minutes: int = 12 * 60
    overrides: dict[date, tuple[Window, ...]] = field(default_factory=dict)
    focus_windows: tuple[Window, ...] = ()
    prefer_cluster: bool = False


@dataclass(frozen=True)
class Occupancy:
    busy: tuple[Interval, ...] = ()
    reservations: tuple[Interval, ...] = ()  # Already include stored buffer snapshots.
    focus: tuple[Interval, ...] = ()
    invitee_busy: tuple[Interval, ...] = ()
    event_counts: dict[date, int] = field(default_factory=dict)
    host_counts: dict[date, int] = field(default_factory=dict)
    week_minutes: dict[date, int] = field(default_factory=dict)


def resolve_wall_time(local: datetime, zone: ZoneInfo) -> tuple[datetime, ...]:
    """Return both real UTC instants for folds, or none for a spring-forward gap."""
    instants = set()
    for fold in (0, 1):
        instant = local.replace(tzinfo=zone, fold=fold).astimezone(UTC)
        if instant.astimezone(zone).replace(tzinfo=None) == local:
            instants.add(instant)
    return tuple(sorted(instants))


def resolve_focus_boundary(local: datetime, zone: ZoneInfo) -> tuple[datetime, ...]:
    # A focus boundary in a DST gap resumes at the first real wall minute.
    # Fold boundaries protect both occurrences conservatively.
    for offset in range(1441):
        values = resolve_wall_time(local + timedelta(minutes=offset), zone)
        if values:
            return values
    return ()


@dataclass(frozen=True)
class SlotReport:
    slots: tuple[Interval, ...]
    excluded: dict[str, int]
    recommended: tuple[datetime, ...] = ()


def get_slot_report(
    rules: Rules,
    occupancy: Occupancy,
    *,
    start_date: date,
    end_date: date,
    invitee_timezone: str,
    duration_minutes: int,
    now: datetime,
) -> SlotReport:
    """Return valid slots whose start falls in inclusive invitee-local dates.

    Buffers must fit inside working windows. Caps use the host-local day and
    Monday-based week. Each candidate is hypothetical, not a reservation.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must include a timezone")
    if end_date < start_date or (end_date - start_date).days > 41:
        raise ValueError("request between 1 and 42 days")
    if start_date.year < 2 or end_date.year > 9998:
        raise ValueError("Dates are outside the supported range.")
    if duration_minutes <= 0 or rules.increment_minutes <= 0:
        raise ValueError("duration and increment must be positive")
    host_zone = ZoneInfo(rules.timezone)
    invitee_zone = ZoneInfo(invitee_timezone)
    lower = datetime.combine(start_date, time.min, invitee_zone).astimezone(UTC)
    upper = datetime.combine(end_date + timedelta(days=1), time.min, invitee_zone).astimezone(UTC)
    now = now.astimezone(UTC)
    earliest = now + timedelta(minutes=rules.notice_minutes)
    latest = now + timedelta(days=rules.horizon_days)
    host_date = lower.astimezone(host_zone).date()
    final_host_date = upper.astimezone(host_zone).date()
    exclusions = occupancy.busy + occupancy.reservations + occupancy.focus + occupancy.invitee_busy
    result: dict[datetime, Interval] = {}
    excluded: dict[str, int] = {}

    def explain(reason):
        excluded[reason] = excluded.get(reason, 0) + 1

    while host_date <= final_host_date:
        day_start = resolve_focus_boundary(datetime.combine(host_date, time.min), host_zone)
        day_end = resolve_focus_boundary(
            datetime.combine(host_date + timedelta(days=1), time.min), host_zone
        )
        if not day_start or not day_end or min(day_start) >= upper or max(day_end) <= lower:
            host_date += timedelta(days=1)
            continue
        week = host_date - timedelta(days=host_date.weekday())
        capped = (
            occupancy.event_counts.get(host_date, 0) >= rules.event_daily_cap
            or occupancy.host_counts.get(host_date, 0) >= rules.host_daily_cap
            or occupancy.week_minutes.get(week, 0) + duration_minutes > rules.weekly_cap_minutes
        )
        windows = rules.overrides.get(
            host_date, tuple(w for w in rules.windows if w.weekday == host_date.weekday())
        )
        focus = list(occupancy.focus)
        for window in rules.focus_windows:
            if window.weekday == host_date.weekday():
                starts = resolve_focus_boundary(
                    datetime.combine(host_date, window.start), host_zone
                )
                ends = resolve_focus_boundary(datetime.combine(host_date, window.end), host_zone)
                if starts and ends:
                    focus.append(Interval(min(starts), max(ends)))
        if capped:
            explain("meeting_limits")
        elif not windows:
            explain("closed_days")
        else:
            for window in windows:
                local_start = datetime.combine(host_date, window.start)
                local_end = datetime.combine(host_date, window.end)
                boundaries_start = resolve_focus_boundary(local_start, host_zone)
                boundaries_end = resolve_focus_boundary(local_end, host_zone)
                if not boundaries_start or not boundaries_end:
                    continue
                local_cursor = local_start
                while local_cursor < local_end:
                    for candidate in resolve_wall_time(local_cursor, host_zone):
                        end = candidate + timedelta(minutes=duration_minutes)
                        blocked = Interval(
                            candidate - timedelta(minutes=rules.buffer_before_minutes),
                            end + timedelta(minutes=rules.buffer_after_minutes),
                        )
                        if not lower <= candidate < upper:
                            continue
                        if candidate < earliest:
                            explain("minimum_notice")
                        elif end > latest:
                            explain("booking_horizon")
                        elif blocked.start < min(boundaries_start) or blocked.end > max(
                            boundaries_end
                        ):
                            explain("duration_and_buffers")
                        elif any(blocked.overlaps(interval) for interval in focus):
                            explain("focus_blocks")
                        elif any(blocked.overlaps(interval) for interval in exclusions):
                            explain("occupied_times")
                        else:
                            result[candidate] = Interval(candidate, end)
                    local_cursor += timedelta(minutes=rules.increment_minutes)
        host_date += timedelta(days=1)
    slots = tuple(result[key] for key in sorted(result))
    recommended = []
    if rules.prefer_cluster:
        for day in sorted({slot.start.astimezone(host_zone).date() for slot in slots}):
            meetings = [
                i
                for i in occupancy.busy + occupancy.reservations
                if i.start.astimezone(host_zone).date() == day
            ]
            if meetings:
                candidates = [
                    slot for slot in slots if slot.start.astimezone(host_zone).date() == day
                ]
                candidates.sort(
                    key=lambda s: (
                        min(
                            min(
                                abs((s.start - i.end).total_seconds()),
                                abs((i.start - s.end).total_seconds()),
                            )
                            for i in meetings
                        ),
                        s.start,
                    )
                )
                recommended.extend(s.start for s in candidates[:3])
    return SlotReport(slots, excluded, tuple(recommended))


def get_available_slots(*args, **kwargs) -> list[Interval]:
    return list(get_slot_report(*args, **kwargs).slots)
