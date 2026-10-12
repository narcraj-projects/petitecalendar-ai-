# Host notifications and guest history review

Status: reviewed and approved for deployment and public-repository publication on 12 October 2026. Hosted migration `0010_host_guest` is applied; restricted web/guest/worker roles passed read-only checks. Code deployment and live SMTP acceptance follow the approved push.

## Behavior to review

New bookings queue separate confirmations for the guest and host. The host receives guest contact, title, both timezone times, duration, location/Meet and a link to the signed-in host dashboard. Host delivery status appears on the host booking card. A failure for one recipient does not change the other recipient's job. Existing bookings are not backfilled. Host reschedule/cancellation emails are outside this increment.

The guest history entry is `/guest/bookings`, linked from the homepage, host navigation and new guest confirmation emails. Guests use their booking email to request a Supabase magic link. The verified inbox sees Upcoming, Past and Cancelled views, including earlier bookings made using that email. No host profile is needed. Booking remains available without signing in. History is read-only; guests manage a meeting through its original private confirmation link.

The API verifies the signed session and current confirmed Auth email. Client-supplied email or owner parameters never select a history. PostgreSQL enforces the same restriction using a dedicated guest role and forced RLS. Responses exclude contacts and private capabilities; changed identities are rejected. There is no alias/different-address merging.

## Local checks

- Backend regression: 227 passed; 9 opt-in checks skipped in the ordinary run.
- New PostgreSQL migration/authorization check: passed against isolated development storage, with synthetic users/jobs and complete rollback. Verified guest RLS, denial of capability reads, atomic/idempotent host-job creation, independent recipient states, and immutable host retries after an account-email change.
- Ruff and TypeScript/Vite build: passed.
- Browser regression: all 49 scenarios passed, including the four new guest-history scenarios. Verified anonymous verification, callback routing without host onboarding, filter/pagination/refresh/sign-out, provider errors and 390px layout; visually inspected desktop/mobile screenshots.
- Real providers were replaced by test doubles for email sending and magic-link verification. No live messages were sent.

## Review locally

The review web server runs on `http://127.0.0.1:8029`; the entry is `http://127.0.0.1:8029/guest/bookings`. It is a local UI preview. The development database remains on its existing migration, so real history cannot load until an approved migration. Browser screenshots use clearly synthetic meeting/contact fixtures; the browser tests demonstrate the complete authenticated flow without sending email.

Reproduce UI tests with `PLAYWRIGHT_BASE_URL=http://127.0.0.1:8029` and `npx playwright test` in `frontend`. Start the API with `.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8029 --no-access-log`; do not start a live email worker for a preview.

## Activation after approval

Before arbitrary guests can receive magic links, verify custom SMTP in the application's Supabase project. Supabase's default SMTP only sends to project-team addresses. Existing Resend SMTP can use host `smtp.resend.com`, port `465`, username `resend`, the private Resend API key as password, and a verified sender such as `bookings@petcalendar-ai.ink`. Keep click tracking disabled for authentication links. Check the callback allowlist includes the app's `/auth/callback?next=guest`; keep email confirmation enabled and current rate/budget limits.

Sources: [Supabase custom SMTP](https://supabase.com/docs/guides/auth/auth-smtp), [Resend SMTP](https://resend.com/docs/send-with-smtp).

Then apply `0010_host_guest` with the migration account, deploy the reviewed web/worker code, and verify a new booking sends two independent messages plus a magic-link session sees only its inbox's history. Do not activate the new code against an unmigrated database: host-dashboard reads require the new table. Existing provider variables are reused; no new hosted service or paid upgrade is needed. PDF/video artifacts stay local and are outside this code change.
