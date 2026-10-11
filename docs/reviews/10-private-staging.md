# Step 10: private staging review

Review URL: https://web-staging-1ecf.up.railway.app/login

## Working deployment

Railway builds the private `narcraj-projects/petcalendar-ai` GitHub repository. The web and continuously running Calendar/email worker are separate single-replica services; the worker has no public domain. The web process healthcheck uses `/api/health`, which verifies process responsiveness, not provider readiness. All other routes, including pages, assets and APIs, require the staging gate. The browser receives an encrypted eight-hour Secure/HttpOnly/SameSite=Lax cookie. Normal Supabase authorization still protects host APIs.

Staging uses its own Supabase project, all eight migrations and separate restricted NOINHERIT web/worker logins. Privileged migration credentials remain local. Credentials are ignored by Git; the user explicitly authorized their transfer into Railway private service variables. Compose uses `.env.staging.worker` to override the web database login for the worker.

## Verified on 11 October 2026

- Ruff passed; 196 backend tests passed, plus all seven opt-in PostgreSQL tests against isolated staging.
- GitHub Linux container build/startup checks passed. Railway web and worker deployments succeeded.
- HTTPS gate rejects unauthorized pages/APIs/docs; the authorized frontend loads, auth configuration points at staging and `/api/me` rejects an unauthenticated application session.
- Google sign-in is enabled. The user reached onboarding and saved a host, two published events and an enabled five-day weekly schedule.
- Hosted availability returned real slots for both published events. The third proposed Brainstorming event remains optional and was not found under its proposed slug.
- A confirmed booking and two synced Calendar revisions were observed. Read-only Google verification found its current event and saved Meet link; the previous revision's event was removed.
- Two email jobs were accepted by Resend. The sending key returned HTTP 401 on email status lookup; do not interpret provider acceptance as independently verified inbox delivery. Keep the existing restricted test sender.
- The user explicitly confirmed that the matching local/staging OpenAI key is now dedicated to PetCalendar AI with an enforced USD 3 limit. Key authentication and model availability passed, and `AI_ENABLED=true` was set for hosted web. A live scheduling request using the saved 45-minute event default returned eight slots in 6.8 seconds. An earlier request for an unsupported 15-minute duration was rejected without creating a booking. No AI confirmation or mutation was performed.
- Railway USD 10 hard cutoff and USD 7 alert remain enabled; Railway Agent remains disabled. Supabase and Resend remain Free. No spending limit or plan was raised.

## User review

Open the review URL. At the browser challenge use username `staging` and retrieve `STAGING_ACCESS_PASSWORD` locally from `.env.staging`, without quotes. Sign in, open a published event and try the assistant with "Find a time next week". Its choices still require normal timezone review and booking confirmation. Check your existing booking's Calendar/Meet details and actual email receipt. Do not create duplicate test bookings unnecessarily.

## Release work still pending

This review is for private staging. Inbox receipt, live cancellation acceptance and a worker interruption with pending delivery are not independently verified here. Backup export/restoration into a disposable database, monitoring and a verified sender domain remain production release work. Public access requires a separate decision and a budget-compatible plan; the USD 20 combined monthly authorization still applies. After this review, ask the user to sequence improvements such as reminders, Mutual Match and production readiness. Payments, WhatsApp, teams and polls remain separate scope.
