# Public availability preview review

Step 1 implements a read-only public booking page and Python availability engine. It uses a labelled demo schedule for Ananya Rao. Supabase, live calendars, booking creation, payments and the agent remain later steps.

## Review path

Open http://127.0.0.1:8017/ananya/career-strategy while the preview server is running.

1. Select 30, 45 and 60 minutes and observe the available times update.
2. Choose an available day and move to another month.
3. Change your timezone to London, New York or Kathmandu. Both invitee and host times remain visible.
4. Select a slot and choose Review. Confirm your current or travel timezone before the time summary. Change my time zone returns you to the selector and recalculates slots. The summary shows both dates/times and makes clear that nothing is reserved.
5. Return to available times. At 390px, use the day strip and View month calendar.

## Demonstrated rules

The demo host works weekdays 09:00 to 18:00 in Asia/Kolkata, protects 09:00 to 11:00 and Friday afternoons, and has an occupied 13:00 to 14:00 interval. Candidates use 15 minute increments, 12 hour notice, a 60 day horizon and 10 minute before/15 minute after buffers. Buffers must fit working hours. Caps are supported and tested by the engine but this first page has no booked reservations to count.

## Review boundary

Review the layout, selection flow and proposed availability rules before Step 2. The missing SPEC.md may change policy details later; the sample data is not a confirmed production configuration.

## Verification results

- 25 backend tests passed, covering API validation, interval boundaries, notice, buffers, caps, focus blocks, timezone date boundaries and DST gaps/folds.
- Ruff checks and format checks passed.
- TypeScript checks and the Vite production build passed.
- 4 browser tests passed with installed Chrome: desktop selection, 390px mobile selection and minimum calendar target size, fetch failure/retry, and automatic device timezone plus travel override/confirmation. The updated TypeScript checks and production build pass.
- Desktop and mobile screenshots were inspected; mobile has no horizontal overflow.
- The served booking page returned HTTP 200.

Reviewed captures: [Desktop](01-desktop.png), [Mobile](01-mobile.png). Browser tests regenerate captures in frontend/test-results; these review copies were saved after the passing run.

The backend test client currently emits a third-party deprecation warning about its HTTP transport. All assertions pass; revisit the test transport when updating FastAPI/Starlette dependencies.
