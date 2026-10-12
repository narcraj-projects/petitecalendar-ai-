"""Host notification without the guest's private management link."""

from html import escape
from urllib.parse import urlparse

from app.integrations.email import EmailError
from app.services.icalendar import local_time


def host_notification_payload(booking, recipient, settings):
    base = urlparse(settings.app_base_url)
    if (
        not base.hostname
        or (base.scheme != "https" and base.hostname not in ("localhost", "127.0.0.1"))
        or base.path not in ("", "/")
        or base.query
        or base.fragment
        or base.username
        or base.password
    ):
        raise EmailError("configuration_required", permanent=True)
    if not recipient:
        raise EmailError("host_contact_unavailable", permanent=True)
    snapshot = booking["snapshot"]
    title = snapshot["title"].replace("\r", " ").replace("\n", " ")
    link = settings.app_base_url.rstrip("/") + "/app/bookings"
    lines = [
        f"Hi {snapshot['host_name']},",
        "You have a new booking.",
        title,
        f"Guest: {booking['invitee_name']} ({booking['invitee_email']})",
        "Your time: "
        + local_time(booking["start_at"], snapshot["host_timezone"])
        + f" [{snapshot['host_timezone']}]",
        "Guest time: "
        + local_time(booking["start_at"], booking["invitee_timezone"])
        + f" [{booking['invitee_timezone']}]",
        f"Duration: {booking['duration']} minutes",
        "Location: " + (booking.get("meet_url") or snapshot["location"]),
        "View and manage this booking in your host dashboard: " + link,
        "Sign in with your host account. Your guest received a separate confirmation.",
        "PetiteCalendar-ai",
    ]
    body = "".join(f"<p>{escape(line)}</p>" for line in lines[:-3])
    body += f'<p><a href="{escape(link, quote=True)}">Open your host dashboard</a></p>'
    body += "<p>Sign in with your host account. Your guest received a separate confirmation.</p>"
    return {
        "from": settings.email_from,
        "to": [recipient],
        "subject": "New booking: " + title,
        "text": "\n\n".join(lines),
        "html": '<div style="font-family:Arial,sans-serif;max-width:560px">'
        "<h1>PetiteCalendar-ai</h1>" + body + "</div>",
    }
