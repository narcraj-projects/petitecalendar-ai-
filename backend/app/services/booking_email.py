import base64
import json
from html import escape
from urllib.parse import urlparse

from app.integrations.email import EmailError
from app.services.icalendar import calendar_file, local_time


def confirmation_payload(booking, capability, settings, event_type="booking_confirmed"):
    parsed = urlparse(settings.app_base_url)
    if (parsed.scheme != "https" and parsed.hostname not in ("localhost", "127.0.0.1")) or (
        parsed.query or parsed.fragment or parsed.username or parsed.password
    ):
        raise EmailError("configuration_required", permanent=True)
    link = settings.app_base_url.rstrip("/") + f"/booking/{booking['id']}#{capability}"
    snapshot = booking["snapshot"]
    outcome = {
        "booking_confirmed": "confirmed",
        "booking_rescheduled": "rescheduled",
        "booking_cancelled": "cancelled",
    }[event_type]
    details = [
        f"Your booking with {snapshot['host_name']} is {outcome}.",
        snapshot["title"],
        "Your time: "
        + local_time(booking["start_at"], booking["invitee_timezone"])
        + f" [{booking['invitee_timezone']}]",
        "Host time: "
        + local_time(booking["start_at"], snapshot["host_timezone"])
        + f" [{snapshot['host_timezone']}]",
        f"Duration: {booking['duration']} minutes",
        "Location: " + (booking.get("meet_url") or snapshot["location"]),
    ]
    if not booking.get("meet_url"):
        details.append("Open your private booking link for the latest calendar and Meet status.")
    details += [
        "Private booking link: " + link,
        "Keep this link private; it grants booking access.",
    ]
    if not capability:
        details = details[:-2] + [
            "Use the private booking link from your original confirmation "
            "to view the latest details."
        ]
    body_html = "".join(
        "<p>" + escape(line) + "</p>" for line in (details[:-2] if capability else details)
    )
    if capability:
        body_html += (
            f'<p><a href="{escape(link, quote=True)}">View your private booking</a></p>'
            "<p>Keep this link private; it grants booking access.</p>"
        )
    return {
        "from": settings.email_from,
        "to": [booking["invitee_email"]],
        "subject": f"Booking {outcome}: " + snapshot["title"].replace("\r", " ").replace("\n", " "),
        "text": "\n\n".join(details),
        "html": body_html,
        "attachments": [
            {
                "filename": "booking.ics",
                "content": base64.b64encode(calendar_file(booking)).decode(),
            }
        ],
    }


def payload_text(payload):
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
