# PetCalendar AI

The application name is **PetCalendar AI**; the repository and package name is `petcalendar-ai`. Legacy internal database roles, Google event markers and calendar UIDs retain their original identifiers so existing bookings and integrations stay compatible. Design references use `petcalendar-ai.example` as a placeholder, not a registered application domain.

The current direction is Python, Supabase and agentic AI, implemented and reviewed one functionality at a time. See [Architecture](docs/ARCHITECTURE.md), [Implementation plan](docs/IMPLEMENTATION_PLAN.md) and [Design adaptation](docs/DESIGN_ADAPTATION.md). The original ZIP is preserved. Its technology instructions are superseded by AGENTS.md; docs/SPEC.md was not included.

## Scheduling assistant (Step 9)

Add `OPENAI_API_KEY` to the root `.env`; keep it server-only. `OPENAI_MODEL` defaults to `gpt-6-astra`. The existing `TOKEN_ENCRYPTION_KEY` binds settings/cancellation confirmations across restarts. Rebuild the frontend and restart the API after configuration/code changes. A valid key also needs a funded API organization; `credit_balance_exhausted` requires checking that key's organization billing, not repeated retries.

On a published event page, open **Find a time with the assistant** and try **Book me a meeting**. The assistant uses the page's event, duration and selected zone; without a requested date, it searches the next seven days. Confirm the current/travel zone and review before booking. Signed-in users get their own verified email and saved profile name filled automatically; guests enter contact details once per page visit. Contact details stay outside model requests. Private booking management also supports suggested replacement times, saved policy explanations and explicitly confirmed cancellation. On `/app/event-types`, select an existing event or shared availability/Focus Guard, open **Draft settings with the assistant**, ask for a change and review its diff before applying. Conventional controls remain available.

Checks: `.venv/Scripts/python.exe -m pytest backend/tests/test_assistant.py -q`; opt into `backend/tests/test_assistant_database.py` with `RUN_DATABASE_TESTS=1`. The database check uses synthetic hosts and rolls back all fixtures. Browser checks: `npm run test:e2e -- tests/assistant.spec.ts` from `frontend`. For a deliberately triggered live evaluation, set `PYTHONPATH` to `backend` and run `.venv/Scripts/python.exe backend/evaluate_assistant.py`; it sends four synthetic examples to OpenAI and performs no domain writes. See [Step 9 review](docs/reviews/09-scheduling-assistant.md).

## Local availability preview

Step 1 is a responsive booking page with Python-calculated slots and a labelled demo schedule. It does not create bookings or connect calendars, Supabase or an AI provider yet.

Preview: http://127.0.0.1:8017/ananya/career-strategy

Initial setup from the repository root in PowerShell:

```powershell
$env:UV_CACHE_DIR = Join-Path $PWD '.cache/uv'
uv sync
Set-Location frontend
npm.cmd ci
npm.cmd run build
Set-Location ..
uv run uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8017 --no-access-log
```

FastAPI serves the compiled frontend and API at the same origin. Rebuild after frontend edits. For hot reload, run the API and frontend `npm.cmd run dev` in separate terminals; Vite proxies /api to port 8017. Python 3.13 is pinned; uv uses a compatible installed interpreter or can install one.

Checks from the repository root:

```powershell
$env:UV_CACHE_DIR = Join-Path $PWD '.cache/uv'
uv run pytest
uv run ruff check backend
uv run ruff format --check backend
Set-Location frontend
npm.cmd run build
$env:TEMP = Join-Path (Split-Path $PWD) '.cache/tmp'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null
npm.cmd run test:e2e
```

Browser tests expect the preview server to be running and use installed Google Chrome. They save desktop/mobile captures under frontend/test-results; reviewed copies are kept in docs/reviews. Workspace-local temporary files avoid the full system temporary drive encountered during development. See [Step 1 review](docs/reviews/01-availability.md).

## Host sign-in and onboarding

Step 2 adds Supabase host sign-in and a persisted profile. Follow [Supabase setup](docs/SUPABASE_SETUP.md) for environment values, redirect URLs, email templates, Google OAuth and migrations. Host entry: http://127.0.0.1:8017/login. The availability demo remains separate from host profile data.

## Event types

Step 3 entry: http://127.0.0.1:8017/app/event-types. Run `uv run alembic upgrade head` to apply the event schema, rebuild the frontend, and restart the API. Create/edit drafts, publish/unpublish, and open real public metadata pages. Scheduling and booking arrive in the next milestones. See [Step 3 review](docs/reviews/03-event-types.md).

Opt-in database checks: set `$env:RUN_DATABASE_TESTS = '1'`, then run `uv run pytest backend/tests/test_profile_database.py backend/tests/test_event_database.py -q`; remove the environment flag afterwards. Fixtures are rolled back.

## Availability and Focus Guard

Step 4 entry: http://127.0.0.1:8017/app/availability. Apply `uv run alembic upgrade head`, rebuild, and restart as above. Save weekly hours, overrides and Focus Guard to show real calculated times on your published event pages. The suggested hours are inactive until saved. Step 5 adds explicit booking confirmation after review. See [Step 4 review](docs/reviews/04-availability-focus.md).

All real database checks: set `$env:RUN_DATABASE_TESTS = '1'`, run `uv run pytest backend/tests/test_profile_database.py backend/tests/test_event_database.py backend/tests/test_schedule_database.py -q`, then remove the flag. Temporary fixtures are rolled back.

## Free booking and dashboard

Step 5: open a published event from http://127.0.0.1:8017/app/event-types, select a time, confirm the current/travel timezone, enter name/email and explicitly confirm. The booking commits to PostgreSQL; the private fragment link reloads its saved confirmation. Host dashboard: http://127.0.0.1:8017/app/bookings. Saved reservations now filter public slots and enforce Focus Guard counts. The Ananya demo remains a preview.

Apply `uv run alembic upgrade head`, rebuild the frontend and restart the API. No new environment values are needed. Calendar/Meet and email/ICS remain Steps 6 and 7. Keep the private confirmation URL because emails are not sent yet. See [Step 5 review](docs/reviews/05-booking-dashboard.md).

For all PostgreSQL checks, set `$env:RUN_DATABASE_TESTS = '1'`, run `uv run pytest backend/tests/test_profile_database.py backend/tests/test_event_database.py backend/tests/test_schedule_database.py backend/tests/test_booking_database.py -q`, then remove the flag. The concurrency check commits random synthetic fixtures so independent connections can compete, then removes only those fixtures in `finally`; prior checks roll back their fixtures.

## Google Calendar and Meet

Step 6 entry: http://127.0.0.1:8017/app/integrations. Follow [Google Calendar setup](docs/GOOGLE_CALENDAR_SETUP.md), apply migrations, rebuild and restart the API. In a second terminal set `$env:PYTHONPATH = Join-Path $PWD 'backend'` and run `uv run python -m app.worker`. Saved settings activate busy checks and queue new bookings for Calendar/Meet. Earlier bookings are not backfilled. Email/ICS remain Step 7. See [Step 6 review](docs/reviews/06-google-calendar.md).

All five PostgreSQL checks: set `$env:RUN_DATABASE_TESTS = '1'`, run `uv run pytest backend/tests -q -k database`, then remove the flag. Calendar/booking fixtures commit random synthetic IDs and remove only those IDs afterwards. Provider calls use doubles.

## Email and calendar downloads

Step 7 adds invitee confirmation emails and Download calendar (.ics) on private booking pages. Follow [email setup](docs/EMAIL_SETUP.md), apply migration `0007_booking_email`, rebuild and restart the API/worker. The existing `python -m app.worker` now processes both Calendar and email deliveries. Host dashboard and confirmations show actual email states; Accepted means the provider accepted a request, not proof of inbox arrival. Earlier bookings are not backfilled. The test sender works only for your Resend account address.

Stop delivery workers before opt-in PostgreSQL tests to keep real providers from claiming synthetic fixtures. Tests inject fake providers and remove committed random IDs afterwards. See [Step 7 review](docs/reviews/07-email-calendar.md).

## Original hand-off instructions


The following historical instructions describe the original hand-off kit.

Put these files in the root of your project repo (or an empty folder you open in Codex):

```
AGENTS.md                 Rules Codex reads automatically before every task
CODEX_PROMPTS.md          The prompts to paste into Codex, in order
docs/SPEC.md              <- ADD THIS: export the spec doc as Markdown and save it here
docs/DESIGN.md            Colours, fonts, components, screen-to-route map
docs/design/*.html        Reference screens (the approved "Midnight" UI)
docs/design/screenshots/  <- OPTIONAL: PNG exports of each screen from the canvas
```

Steps
1. Export the spec doc: open "PetCalendar AI – Product & Technical Design Spec", click the doc's name → Export → Markdown. Rename to `SPEC.md` and put it in `docs/`.
2. (Optional, recommended) Export each screen from the design canvas as PNG into `docs/design/screenshots/`. Codex follows a picture better than markup alone, and you can attach the PNG to a prompt.
3. Push the folder to a GitHub repo (for Codex in ChatGPT / cloud) or open it locally (for Codex CLI or the IDE extension).
4. Paste the prompts from `CODEX_PROMPTS.md` one at a time. Review, run and commit after each.

About the reference screens
The `.html` files in `docs/design/` were made in a design canvas. They use a small template syntax
(`<x-dc>`, `<sc-for>`, `<sc-if>`, `{{value}}`) and won't open as normal pages. Codex can still read the
exact layout, spacing, colours and copy from them; treat them as the visual source of truth, not as code to copy.


## Cancellation and rescheduling

Step 8 adds change controls to the private confirmation and host dashboard. Apply `uv run alembic upgrade head`, rebuild the frontend and restart both API and delivery worker. No additional credentials are required. The original booking stays reserved during approval and on failure; proposed alternatives are not held. Host review supports approve/decline, and invitees can withdraw. Calendar cleanup and change emails run durably after commit. Resend remains in test mode. See [Step 8 review](docs/reviews/08-booking-lifecycle.md).

Stop the live delivery worker before all six opt-in PostgreSQL checks: set `$env:RUN_DATABASE_TESTS='1'` and run `uv run pytest backend/tests -q -k database`, then remove the flag. External providers are fake; fixtures use committed random IDs and are cleaned up in `finally`.

## Staging deployment preparation

Container build and separate web/worker definitions are in `Dockerfile` and `compose.staging.yaml`. See [staging setup](docs/STAGING_SETUP.md) for isolated credentials, OAuth redirects, private access and acceptance. No online service has been provisioned.
