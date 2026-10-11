# Booking email and calendar downloads

Step 7 uses Resend for invitee booking confirmations. Supabase sign-in email settings are separate. Existing bookings are not backfilled; only new bookings after configured email support queue confirmations. Calendar downloads work on all existing private confirmation pages.

## Development setup

1. Sign up at [Resend](https://resend.com).
2. Open API Keys, create a Sending access key and save it privately in the root `.env`.
3. For a development test without a verified domain, use:

```dotenv
RESEND_API_KEY=replace_with_your_key
EMAIL_FROM=PetCalendar AI <onboarding@resend.dev>
```

The test sender can send only to the email address associated with your Resend account. Use that exact address as the invitee email for review. For other invitees, add a domain you own in Resend, add its required DNS records, wait for verification and change EMAIL_FROM to an address on that verified domain. Do not use a personal Gmail address as the sender. See [Resend testing limits](https://resend.com/docs/knowledge-base/403-error-resend-dev-domain) and [verified domains](https://resend.com/docs/dashboard/domains/introduction).

Do not share the API key in chat or commit `.env`. Retain TOKEN_ENCRYPTION_KEY across restarts; it encrypts queued private booking links and message payloads. Keep email click/open tracking disabled for private capability links.

## Run

Apply `uv run alembic upgrade head`, rebuild the frontend and restart the API. In a separate terminal at the repository root:

```powershell
$env:PYTHONPATH = Join-Path $PWD 'backend'
uv run python -m app.worker
```

The worker supports Calendar and email jobs with separate roles/adapters. The user explicitly approved booking confirmation emails on 11 October 2026, and the combined worker is active. Use --calendar-only when email delivery should be paused. Stop delivery workers while running committed database fixture tests; the tests use fake providers. They must not compete with a live worker for synthetic jobs.

## Review

1. Open your published booking page and reserve a future time using your Resend account email.
2. Keep the private confirmation URL. Refresh Calendar and email status after a few seconds.
3. Check the message in your inbox/spam folder. It includes both timezone labels, the private booking link and a booking.ics attachment. When ready within ten minutes, Meet is included; otherwise the private link shows its latest status.
4. Click Download calendar (.ics) and open/import the file into a calendar. Verify start/end and the Meet location. Calendar apps convert its UTC instants into their own display timezone.
5. Email Accepted means Resend accepted the request, not verified inbox delivery. If a job is uncertain, check your inbox before taking any further action. Automatic retries stop before Resend's 24-hour deduplication window expires.

Development email links use 127.0.0.1 and open only on the computer running the app. Public launch requires an HTTPS APP_BASE_URL accessible to invitees, a verified sender domain and release readiness.
