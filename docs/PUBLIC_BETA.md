# PetCalendar AI public weekend release

On 11 October 2026 the user confirmed receipt of a booking email after configuring the verified `petcalendar-ai.ink` sender, then explicitly approved removing the Railway staging password gate for the website, public booking pages and AI assistant.

## Access

- Website: https://web-staging-1ecf.up.railway.app
- Host sign-in: https://web-staging-1ecf.up.railway.app/login
- Published Project Review booking page: https://web-staging-1ecf.up.railway.app/narcraj/project-review

The existing Railway environment and isolated Supabase project are being used for the public weekend release. This does not create a separate production environment or migrate development bookings. The website still uses its Railway address; `petcalendar-ai.ink` is configured for sending email.

The homepage separates **Start hosting / Host sign in** from **Book as a guest**. Guests can paste the host's booking link or open it directly. They do not create an account: after choosing a slot and confirming their current timezone, they enter their own name and email before confirming the booking. The example availability demo is not the homepage or a real booking page.

Booking-dependent screens refresh automatically while visible and online, every 15 seconds and when the user returns to the tab or reconnects. Same-browser booking changes also notify other tabs without sharing contact details or private capabilities. This updates host booking lists and Focus Guard counts, public slots, and invitee confirmation/delivery status. Refresh preserves the selected duration and contact draft; a selected slot that becomes unavailable is cleared. Background failures keep the last view and show a retry notice. Final reservation still rechecks availability on the server.

`STAGING_PRIVATE=false` removes the shared password challenge. Host APIs still require a verified Supabase token, and booking management still requires its private capability. The worker has no public domain. No provider secrets or database credentials are exposed by this setting.

## Google access

Google OAuth remains in **Testing**, as confirmed by the user. Guests can book without Google sign-in or Calendar authorization. Hosts connecting Google Calendar must be listed as Google test users. Calendar consent and refresh-token restrictions still apply; this release does not claim unrestricted Google Calendar onboarding for arbitrary hosts. See [Google audience guidance](https://support.google.com/cloud/answer/15549945).

## Spending and limitations

The combined allowance remains USD 20/month, including fees: Railway USD 10 hard cutoff / USD 7 alert, OpenAI dedicated project USD 3 enforced limit, Supabase/Resend Free and remaining reserve. No paid plan, recharge, cutoff increase or domain auto-renewal is enabled by this release. Provider metering can lag.

The assistant runs on one web process/replica with process-local concurrency and hourly counters. They reset on restart and do not provide shared multi-replica accounting. Behind the hosting proxy, guest requests may share an actor/IP limit. A shared proxy-aware limiter remains future work. Manual booking stays available when the assistant is limited or its provider is unavailable.

The user deferred backup/restore verification, monitoring and additional launch checks for the weekend scope. Broad Google verification, shared AI limits, reminders, Mutual Match, payments, teams and polls remain separate improvements. This is a limited public release, not a completed general production-readiness review.

## Rollback

If public access must be paused, set Railway web `STAGING_PRIVATE=true` and redeploy. Retain the existing strong staging password and encryption key. This restores the gate without deleting bookings or disconnecting providers. Do not increase spending limits to recover from a cutoff without explicit user approval.
