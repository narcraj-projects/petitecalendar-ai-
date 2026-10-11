# Step 8: cancellation and rescheduling

Implemented after the user selected this improvement on 11 October 2026. Ready for live user review; no real booking was cancelled or moved by the agent.

## Working behaviour

- Invitees use their existing private booking link; hosts use their authenticated dashboard. Every action has an explicit review/confirmation and a bound revision/idempotency key.
- Saved invitee cutoffs are enforced, including the exact deadline. Hosts may override invitee cutoffs only for a future meeting. Cancelled meetings cannot be restored or moved.
- Cancellation releases the local reservation immediately, retains a cancelled private page and appears in the dashboard's Cancelled filter. Google removal/email have separate actual delivery status.
- Direct rescheduling atomically replaces the reservation using the saved duration/buffers and current schedule/notice/focus/caps. Failed validation or competing changes preserve the original.
- Current/travel timezone is confirmed before each replacement-time review. Both zones appear in the review.
- With saved host approval enabled, the original stays reserved while one to three alternatives are pending. Alternatives are not held. Hosts review and approve one still-available time or decline; invitees can withdraw. Cancellation supersedes pending requests.
- New revisions queue a new deterministic Google event/Meet, then remove prior owned events. Cancellation removes prior events. Stale jobs never apply to a different current revision. Both workers serialize delivery with lifecycle changes.
- Changed-booking emails and ICS preserve the booking UID and increase SEQUENCE; cancellation files use STATUS:CANCELLED. Host changes refer to the original private link if no capability is available.

## Persistence and privacy

Migration 0008_booking_lifecycle is applied in development Supabase. It adds update timestamps, Calendar operations, a private change-request table, action idempotency records and changed-booking outbox/email categories. Forced RLS protects tenant/capability scope. Change-request capability ciphertext is omitted from API column grants and whitelisted responses, and erased when resolved. Calendar worker grants still exclude invitee email.

Rescheduling excludes the original booking from local intervals and caps. For the affected selected Google calendars, a minimal events list excludes only known IDs with matching private ownership markers. It preserves overlapping unrelated events, including all-day and recurring instances; other calendars still use free/busy. Titles, descriptions and attendees are not requested or retained. Delete checks ownership and uses ETag concurrency protection.

## Verification

- 147 Python tests passed; six real-database checks are opt-in. Ruff lint/format and TypeScript/production build passed.
- All six PostgreSQL checks passed, including lifecycle atomic replacement, original-slot count exclusion at a daily cap, conflict preservation, capability/host isolation, exact retries, stale revisions, cutoff boundaries, approval alternatives, fresh approval conflicts, decline/withdrawal, competing cancellation/reschedule and durable fake-provider Calendar/email results. Synthetic committed fixtures were cleaned up; the live delivery worker was stopped.
- All 28 existing browser checks and four lifecycle checks passed. Lifecycle checks cover timezone confirmation, exact retry after an uncertain response, explicit cancellation/reload, pending approval/withdrawal and host approval/Cancelled filtering. Desktop and 390px layouts are verified, including 44px date targets and no page overflow.
- A read-only check against the actual connected Google account passed for the new replacement availability path. No Google event was created, moved or removed during that check.
- Browser screenshots are visually reviewed. Live mutation, updated email and calendar-client import acceptance remain for the user.

## Review decisions and limits

Host overrides end at the meeting start. Alternatives have no holds and are rechecked on approval. Saved duration/buffers/cutoffs stay fixed; current host schedule and protection rules apply. Existing private links remain valid after changes. Direct host rescheduling and cancellation work from the dashboard.

Google changes are eventually consistent: old occupancy can remain while cleanup retries. A replacement gets a new Google event and may get a new Meet link. Changes preserve the original connected-account generation/destination; switching accounts cannot clean up the old account, and the failure stays visible. A reconnect to the original account plus Retry calendar delivery can recover current failed jobs.

Pending requests have no separate notification/reminder/expiry job. Hosts review them on the dashboard. Imported ICS updates/removals depend on the calendar client; the app sends no Google attendee invitation. Resend remains in test mode by user choice and only supports the account email as a real recipient. Provider acceptance does not prove inbox delivery. Paid lifecycle/refunds remain separate.

## Runtime and manual review

The user accepted this review with "ok" before Step 9. No additional live lifecycle evidence was supplied with that acceptance; automated and read-only results above remain the recorded verification.

The API at http://127.0.0.1:8017 serves the rebuilt frontend. The combined delivery worker is restarted after checks using the existing email authorization and the user's request to implement lifecycle updates. No additional credentials are needed.

1. Open the private booking link in a confirmation email for a meeting at least two days ahead (or create a new test booking using your Resend account email).
2. Choose Reschedule booking, select a different available time, confirm your current zone, review both times and confirm the change. If approval is enabled, review/approve it under /app/bookings; the original stays reserved meanwhile.
3. Refresh Calendar/email status. Check the new time in the private page, dashboard, Google Calendar and changed-booking email. The old Google event should be removed once delivery finishes.
4. On the same future booking, choose Cancel booking and explicitly confirm. Check the cancelled page/dashboard filter, Google removal and cancellation email.
5. Report the result or requested changes. Do not begin AI scheduling or deployment until this review is accepted.

Screenshots: [replacement on mobile](08-reschedule-mobile.png), [desktop confirmation](08-reschedule-desktop.png), [host approval on mobile](08-host-approval-mobile.png).
