"""RFC 5545 calendar download, using UTC instants and a stable booking UID."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo


def instant(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value


def escape(value):
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\n", "\\n")
        .replace(";", "\\;")
        .replace(",", "\\,")
    )


def fold(line):
    chunks, current = [], ""
    for char in line:
        if len((current + char).encode("utf-8")) > 75:
            chunks.append(current)
            current = " "
        current += char
    chunks.append(current)
    return "\r\n".join(chunks)


def local_time(value, zone):
    return instant(value).astimezone(ZoneInfo(zone)).strftime("%a, %d %b %Y %H:%M %Z (%z)")


def calendar_file(booking):
    snapshot = booking["snapshot"]
    start, end = instant(booking["start_at"]), instant(booking["end_at"])
    stamp = instant(booking.get("updated_at", booking.get("created_at", booking["start_at"])))
    meeting = booking.get("meet_url") or snapshot["location"]
    description = (
        f"Booked with {snapshot['host_name']}.\n"
        f"Your time: {local_time(start, booking['invitee_timezone'])} "
        f"[{booking['invitee_timezone']}].\n"
        f"Host time: {local_time(start, snapshot['host_timezone'])} "
        f"[{snapshot['host_timezone']}]."
    )
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//PetCalendar AI//Booking//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{booking['id']}@petitecalendar",
        f"SEQUENCE:{booking['revision']}",
        "DTSTAMP:" + stamp.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ"),
        "DTSTART:" + start.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ"),
        "DTEND:" + end.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ"),
        "SUMMARY:" + escape(snapshot["title"]),
        "LOCATION:" + escape(meeting),
        "DESCRIPTION:" + escape(description),
        "STATUS:CANCELLED" if booking["status"] == "cancelled" else "STATUS:CONFIRMED",
        "CLASS:PRIVATE",
        "TRANSP:OPAQUE",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return ("\r\n".join(fold(line) for line in lines) + "\r\n").encode("utf-8")
