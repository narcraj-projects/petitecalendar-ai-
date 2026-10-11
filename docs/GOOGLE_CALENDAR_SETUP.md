# Google Calendar and Meet setup

Calendar consent is separate from Supabase Google sign-in. The backend encrypts refresh tokens; the frontend never receives them.

## Google configuration

1. Enable **Google Calendar API** in your Google Cloud project under APIs & Services > Library.
2. Add your account under Google Auth Platform > Audience > Test users if the app is in Testing.
3. Create a **Web application** OAuth client for Calendar. Add the exact redirect URI: `http://127.0.0.1:8017/api/integrations/google/callback`.
4. Save the client values in the root `.env` as `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`. Keep Supabase sign-in's client/callback configured separately. Keep credentials out of chat and source control.
5. Use `APP_BASE_URL=http://127.0.0.1:8017`. The existing `TOKEN_ENCRYPTION_KEY` was generated locally. Keep and privately back it up; replacing it makes saved encrypted tokens unreadable.

The integration requests calendar-list read, event free/busy and event read/write scopes. See [Google OAuth web-server guidance](https://developers.google.com/identity/protocols/oauth2/web-server), [Calendar scopes](https://developers.google.com/workspace/calendar/api/auth) and [event insertion](https://developers.google.com/workspace/calendar/api/v3/reference/events/insert).

## Run locally

From the repository root:

```powershell
uv sync
uv run alembic upgrade head
Set-Location frontend
npm.cmd run build
Set-Location ..
uv run uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8017 --no-access-log
```

In a second terminal at the repository root:

```powershell
$env:PYTHONPATH = Join-Path $PWD 'backend'
uv run python -m app.worker
```

Both processes need the same database/encryption key. Without the worker, bookings remain reserved with Calendar delivery queued. Restart both processes after restarting your computer. Production supervision and a restricted runtime login belong to release readiness.

## Review

1. Open [Calendar & Meet](http://127.0.0.1:8017/app/integrations), click **Connect Google Calendar**, choose your account and complete consent.
2. Select blocking calendars and a writable destination, enable Meet if desired, then **Save calendar settings**. The destination always blocks time.
3. Verify a known Google busy time is absent from your public slots.
4. Make a new test booking, keep the private confirmation link and click **Refresh calendar status**.
5. Check **Calendar event created**, **Join Google Meet** and one matching Google event. Refresh again to verify a stable link.

Only new bookings after saved settings are queued; earlier bookings are not backfilled. Host events send no guest invitations; email/ICS are Step 7. Disconnect preserves reservations and existing Google events.

## Troubleshooting

- **redirect_uri_mismatch**: match the exact scheme/host/port/path above on the Calendar Web client. `localhost` and `127.0.0.1` differ.
- **Access blocked**: check Calendar API, allowed test user and all requested permissions.
- **Connection could not finish**: retry consent in the same browser. State is single-use, cookie-bound and expires in ten minutes.
- **Calendar needs attention**: reconnect the original account, save settings and retry from Bookings. A different account cannot receive an old account's queued booking.
- **Meet unsupported**: choose a compatible destination or disable Meet.
- **Queued stays queued**: start the worker. Repeated failures eventually require dashboard retry after the cause is resolved.

Testing-mode refresh tokens may require later reconnection. Public launch needs HTTPS and review of Google's publishing/verification requirements for the requested scopes.
