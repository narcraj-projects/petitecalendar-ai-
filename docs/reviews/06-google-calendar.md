# Step 6 review: Google Calendar and Meet

Built on 11 October 2026 and ready for live review. Step 5 was approved with "ok". Step 7 has not started.

## Behaviour

Separate Google consent, blocking-calendar selection, writable destination, optional Meet, disconnect and host delivery retry are implemented. The destination always blocks time. Live free/busy feeds the same pure engine as saved reservations; Google failures stop connected-host availability and bookings. Caps count PetCalendar AI bookings; external intervals protect time without inventing meeting counts.

A booking fetches free/busy outside the transaction, takes the shared host lock, rechecks connection generation/revision/status and policy/local occupancy, then commits the reservation and pinned delivery job together. The worker uses SKIP LOCKED leases, expiry recovery and bounded retries. Deterministic Google event/Meet IDs recover uncertain responses without duplicating events. Existing events need matching ownership markers and exact saved times; manual changes require attention rather than being overwritten.

Dashboard and private confirmation show actual queued/working/retry/synced/failed states and Meet links. Events include title/time/guest name/location and private booking markers, excluding email/attendees. No guest invitation is sent. Earlier bookings are not backfilled. Disconnect clears the token locally and stops future checks/delivery while retaining reservations and Google events.

## Persistence and privacy

Migration `0006_google_calendar` is applied to development Supabase. Private connections, consent states and jobs have forced RLS. Consent state is hashed, cookie-bound, single-use and expires in ten minutes; PKCE verifiers/refresh tokens are encrypted with host-bound Fernet envelopes. Access tokens remain transient. Callback redirects are fixed/generic and clear the cookie; no-store/no-referrer and disabled access logging protect the path.

Separate service/worker roles restrict access. Public booking cannot select ciphertext; worker booking grants exclude guest email. Settings/disconnect use verified identity, the shared host lock and optimistic revisions. Reconnecting the same Google account preserves generation; switching accounts invalidates old queued jobs.

## Checks

- 114 Python checks passed; five opt-in database checks skipped in the default run. All 16 Calendar checks passed again after final token-error handling.
- All five real Supabase database checks passed. Calendar covers binding/replay, host isolation, stale settings, external conflicts, provider failure, atomic queue, idempotent booking retry, lease expiry, stale completion rejection, host retry, successful delivery and disconnect without deleting reservations.
- All 25 browser checks passed. Four Calendar checks cover consent navigation, selection/save/reload/disconnect at desktop/mobile sizes, load recovery and private Meet refresh. Those four passed again after correcting checkbox-label styles.
- TypeScript/build and Ruff lint/format passed. Screenshots were visually inspected at 1440px and 390px.

Provider responses are test doubles. PostgreSQL fixtures use random synthetic IDs and exact cleanup. The agent created no booking or Google event for the user's account. Credentials are configured; the last connection check found no saved live Calendar connection. Actual consent, live free/busy and one real event/Meet remain pending user acceptance. Email magic-link delivery remains unverified from Step 2.

## Limits and review

Google cannot share a PostgreSQL transaction; an external event created after the busy check may still race. Reservations remain confirmed during delivery failure. External manual edits/deletes are not continuously synchronized; lifecycle reconciliation is future work. The local worker is running for review; restart it after reboot. Production supervision remains release work.

1. Open [Calendar & Meet](http://127.0.0.1:8017/app/integrations), complete consent and save selections.
2. Verify a known Google busy time is unavailable on your public page.
3. Make a new test booking, retain its private link and refresh delivery status.
4. Check one matching Google event/Meet link, then refresh again.
5. Approve or request changes before Step 7: email and calendar download.

[Setup guide](../GOOGLE_CALENDAR_SETUP.md). Screenshots: [desktop](06-calendar-desktop.png), [mobile](06-calendar-mobile.png), [Meet confirmation](06-meet-confirmation-mobile.png).

## Callback repair during review

The first redirect mismatch came from using a different OAuth client in `.env` than the configured Calendar client; the matching values were saved and the API/worker restarted. A subsequent callback failure exposed overly strict OAuthlib scope comparison: it raises on previously granted extra scopes. Exchange now accepts validated tokens with a superset of required Calendar scopes, while rejecting missing permissions or refresh/access tokens. No global scope-check bypass was added. Fixed error categories distinguish expired consent, incomplete permissions, invalid client credentials, calendar access and storage failures without exposing provider messages or credentials.

Five new token-exchange regression cases exercise the actual OAuthlib parser with synthetic HTTP responses, including PKCE/redirect arguments, additional scopes, missing scopes/token and redacted client errors. All 119 Python checks and lint/build passed. The API was restarted. Live user reconnection still needs confirmation; Resend credentials are being prepared independently.

## Live acceptance verified

On 11 October 2026 the user completed consent, saved a writable primary destination with Meet enabled, removed a public subscribed calendar that returned notFound for free/busy, saved/enabled weekly availability and made test bookings. Read-only checks verified connected status, live selected-calendar free/busy, public availability and two confirmed bookings with two synced delivery jobs. Each job's deterministic Google event exists, is active, has the matching private booking marker and a Meet link. No event or booking was created by the agent. Step 6 live acceptance is now verified; email/ICS is next. Two saved bookings are present, each with its own synced job; this does not imply a duplicate event for either booking.
