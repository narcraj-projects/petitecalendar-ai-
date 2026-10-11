# Step 5 — Free booking and dashboard

Implemented on 11 October 2026. Ready for user review; wait before Step 6.

## Working behaviour

A published event with saved/enabled availability now supports selecting a real slot, confirming the invitee's current/travel timezone, entering required name/email and explicitly confirming a free booking. Success appears only after the reservation transaction commits. The confirmation shows both saved timezone views with UTC offsets, duration, location, invitee details and saved policy deadlines. Keep/copy the private link to revisit it without an account. The Ananya demo still does not create bookings.

The host dashboard at `/app/bookings` (also `/app`) lists upcoming/past confirmed bookings in a selected host-local month, with contact details, saved event title and real integration availability. Current-week Focus Guard counts/minutes and daily bars are queried independently of the selected month. Empty/loading/error/refresh states are supported. At most 500 month rows are displayed with an explicit truncation notice; the bounded API supports narrower date ranges. Mobile uses stacked booking cards to avoid horizontal scrolling.

Required name/email and immediate free confirmation are proposed defaults because SPEC.md is missing. Calendar/Meet is not connected, email is not enabled and no invitation is sent. No fake delivery/Meet/payment success or unsupported controls appear. Cancellation/reschedule remains an improvement to sequence after the core build; saved cutoffs prepare it without claiming it is implemented.

## Reservation correctness and privacy

Applied `0004_bookings` and `0005_booking_outbox` to development Supabase. A host-profile lock serializes booking and existing settings writers. The service rechecks current publication/route, working hours, overrides, focus, notice/horizon, duration/buffers, event/host daily caps and weekly minutes. A half-open buffered `tstzrange` exclusion constraint prevents host-wide overlaps. UTC times and policy/buffer/location/host snapshots persist together with a unique booking-confirmed outbox event.

Confirmed reservations now feed public availability, recommendations and Focus Guard counts across event types. Stored buffers remain protected after event edits. Counts use the current schedule timezone; confirmation keeps its original saved zones. External calendar occupancy waits for Step 6.

Idempotency binds the UUID to the exact route and request fingerprint. Repeating a command returns the same booking; editing its arguments conflicts. Uncertain browser responses retain/freeze the current form command for identical retry. Keep the tab open until it resolves; a page reload does not persist an unverified form command. A successful confirmation fragment link can reload safely.

The browser generates a random 256-bit capability and the database saves only its digest. Booking ID alone does not expose details. Capability is in a link fragment and API header, with no-referrer/no-store responses and no access logging. Host reads use verified JWT identity and RLS; public booking operations use a separate restricted role with transaction-local scope. Private confirmation links grant access to personal booking details and must be retained/shared carefully. Lifecycle capability rotation/revocation is part of future management work.

## Checks

- 98 Python checks passed; 4 opt-in database checks skipped in the default run.
- All 4 real Supabase PostgreSQL checks passed. Booking checks cover simultaneous same-slot attempts, simultaneous different-slot attempts competing for the final cap, idempotency/revision-independent retry, changed-argument conflicts, stored buffers, weekly cap on another day, private-link rejection, host isolation, direct exclusion enforcement and one outbox event per booking.
- Prior 16 browser checks passed; all 5 new booking/dashboard checks passed after correcting test text encoding and the dashboard filter label. They cover confirmation/reload, timezone boundary, ambiguous-response retry, slot conflicts, private-link failure, month/past filtering, current-week counts and mobile overflow.
- TypeScript/production build and Ruff lint/format checks passed. Existing test-client deprecation warning remains non-blocking.

Database concurrency fixtures use committed random synthetic IDs and are deleted in `finally`; other fixtures are rolled back. Browser services use doubles. No booking was created for the user's account by the agent. Desktop/mobile screenshots are saved alongside this review and visually inspected. The real user save/confirm/dashboard flow remains the manual acceptance check. Live email sign-in remains unverified from Step 2.

## Review path

1. Open `/app/event-types` and open your published event link with enabled availability.
2. Choose a future time, confirm your current/travel timezone, enter your name/email and click Confirm booking.
3. Check the confirmation times and copy/save the private link; reload it to verify persistence.
4. Open `/app/bookings`, select the booking's month and check it appears with the correct host time.
5. Reload the public event page: the reserved time and conflicting buffered choices should disappear. Focus Guard counts update from the real reservation.
6. Approve or request changes before Step 6: Google Calendar and Meet.

This creates a real development booking. Cancellation controls are not available until the management improvement, so choose a test time you can leave reserved for now.

Screenshots: [Mobile booking form](05-booking-form-mobile.png), [Mobile confirmation](05-confirmation-mobile.png), [Desktop dashboard](05-dashboard-desktop.png), [Mobile dashboard](05-dashboard-mobile.png).

User review: approved with "ok" before proceeding to Step 6 on 11 October 2026.
