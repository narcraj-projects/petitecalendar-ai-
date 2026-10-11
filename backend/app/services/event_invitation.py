"""A public scheduling invitation, without a reservation or private booking capability."""
# ruff: noqa: E501 -- keep email table markup and inline styles together.

from html import escape
from urllib.parse import urlparse

from app.integrations.email import EmailError


def invitation_payload(profile, event, recipient, settings):
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
    link = settings.app_base_url.rstrip("/") + f"/{profile['username']}/{event['slug']}"
    host, title = profile["display_name"], event["title"]
    durations = ", ".join(str(n) for n in event["durations"]) + " minutes"
    text = (
        f"Hi,\n\n{host} would love to find a time to connect with you.\n\n"
        f"You're invited: {title}\nDuration options: {durations}\n"
        "Choose a time that works for you. You'll review it in your current timezone "
        "before confirming.\n\n"
        f"Choose a time: {link}\n\n"
        "No account needed. Enter your own name and email when you book. "
        "This invitation has not reserved a time.\n\n"
        f"PetCalendar AI\nYou're receiving this because {host} shared this event with your address."
    )
    body = f"""<!doctype html><html><body style="margin:0;background:#0d0f14;color:#eef0f4;font-family:Arial,sans-serif">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:32px 16px">
      <table role="presentation" width="560" cellpadding="0" cellspacing="0" style="width:100%;max-width:560px;background:#151922;border:1px solid #343a48;border-radius:20px">
      <tr><td style="padding:32px"><p style="margin:0 0 28px;color:#c8f25c;font-size:14px;font-weight:bold;letter-spacing:1px">PETCALENDAR AI</p>
      <h1 style="margin:0 0 20px;font-size:28px;line-height:1.3;color:#eef0f4">A conversation worth making time for.</h1>
      <p style="font-size:16px;line-height:1.7;color:#eef0f4">Hi,<br><strong>{escape(host)}</strong> would love to find a time to connect with you.</p>
      <table role="presentation" width="100%" style="background:#1e2330;border-radius:12px"><tr><td style="padding:20px">
      <p style="margin:0 0 10px;font-size:20px;font-weight:bold;color:#eef0f4">{escape(title)}</p>
      <p style="margin:0;color:#9aa1ae;line-height:1.6">Duration options: {escape(durations)}</p></td></tr></table>
      <p style="font-size:16px;line-height:1.7;color:#eef0f4">Choose a time that works for you. You'll review it in your current timezone before confirming.</p>
      <table role="presentation" cellpadding="0" cellspacing="0"><tr><td bgcolor="#c8f25c" style="border-radius:12px">
      <a href="{escape(link, quote=True)}" style="display:inline-block;padding:16px 26px;font-size:16px;font-weight:bold;color:#0d0f14;text-decoration:none">Choose a time</a></td></tr></table>
      <p style="margin-top:24px;color:#9aa1ae;font-size:13px;line-height:1.7">No account needed. Enter your own name and email when you book. This invitation has not reserved a time.</p>
      <p style="color:#9aa1ae;font-size:12px;line-height:1.7">Button not opening? <a href="{escape(link, quote=True)}" style="color:#c8f25c">Open the booking page</a>.</p>
      </td></tr></table>
      <p style="max-width:560px;color:#9aa1ae;font-size:12px;line-height:1.7">You're receiving this because {escape(host)} shared this event with your address.</p>
      </td></tr></table></body></html>"""
    return {
        "from": settings.email_from,
        "to": [recipient],
        "subject": f"{host} invited you: {title}".replace("\r", " ").replace("\n", " "),
        "text": text,
        "html": body,
    }
