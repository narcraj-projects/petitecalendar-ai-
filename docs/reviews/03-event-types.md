# Step 3 — Event types

Implemented on 11 October 2026. The user reported completing the review on 11 October 2026 with no changes requested. Step 4 may proceed.

## Working behaviour

Host event list at `/app/event-types`, linked from the profile page. Create drafts, edit and reload saved fields, and publish or unpublish a unique `/{username}/{slug}` page. Copy/open published links from the list. Draft pages and another host's event types remain inaccessible. Duplicate slugs are rejected per host; different hosts may use the same slug.

The editor follows the Midnight reference's sidebar, heading, settings navigation, limits/policy cards and protection summary. It includes title, description, slug, 1–6 duration options, default duration, location text, notice, horizon, buffers, daily event cap, cancellation/reschedule cutoffs, reschedule approval and alternatives. Publication is saved explicitly; drafts start private. Revision checks reject stale edits. Changing the slug or host username changes the public address; old addresses have no redirect.

Published pages show actual saved event and host details, duration choices and policies. They clearly say scheduling is not ready. No demo schedule is assigned to a real host. Persisted availability is Step 4, atomic bookings Step 5, calendar/Meet Step 6 and email/ICS Step 7 under the approved core-first sequence. Cancellation/rescheduling actions and AI remain improvements to sequence with the user after the core review.

## Persistence and authorization

Applied Alembic `0002_event_types` to the development Supabase project. Events reference the host profile, have unique host/slug pairs, revisions and UTC timestamps. Host transactions use the existing restricted API role, actor context and RLS. The public metadata repository uses a separate restricted read-only role and publication policies. Public API responses whitelist metadata and do not disclose user IDs, revisions or private timestamps. Keep the private schema outside the Data API. Creation requires a profile; mutations lock the host profile to serialize related writes.

## Verification

- 68 Python tests passed; 2 opt-in database tests skipped in the default run.
- Both opt-in tests passed separately against real Supabase PostgreSQL. Event checks cover create/reload, per-host slug uniqueness, cross-host update denial, draft privacy, publication, public metadata filtering, stale revisions, slug changes and unpublication. Temporary users/profiles/events were rolled back.
- 13 Playwright checks passed, including the prior booking and onboarding checks. New tests cover desktop/mobile creation, editing policy fields, reload, publishing, public duration selection, unpublishing, invalid durations and duplicate-slug recovery.
- TypeScript/production build, Ruff lint and formatting passed.
- Desktop and 390px screenshots visually inspected; mobile overflow checks passed.

Browser checks use service doubles; the repository/database checks use real PostgreSQL. The user reported completing the manual review with no changes requested; individual manual actions were not independently observed. Live email login remains unverified from Step 2.

## Proposed defaults and limits

SPEC.md remains absent. Editable defaults use the reference values where applicable: 30/45/60 minutes, 45 minute default, 12 hour notice, 10/15 minute buffers, 3 events per day, and 12 hour policy cutoffs. The 60 day horizon comes from the first demo. Duration options permit 5–240 minutes in five-minute increments, at most six options. These are proposed values for review, not silently applied global scheduling policy. The saved daily cap is event-specific; host-wide Focus Guard follows in Step 4.

Policies are persisted/displayed; the later booking and management services will enforce them. No booking success is simulated. Payment amounts, deposits, connected Meet, reminders, Mutual Match and questionnaires belong to later functionality reviews.

## Review path

1. Open `http://127.0.0.1:8017/app/event-types` in your signed-in browser.
2. Create an event title and inspect its generated slug. Set description, durations and location; save the draft.
3. Open Limits & policies, change notice/buffers/cutoffs, and save. Reload to check persistence.
4. Open Publication, check Publish this event, and save.
5. Open the saved public page. Check event details, duration choices, policies and the scheduling-not-ready message.
6. Unpublish and confirm the public URL is unavailable. Re-publish if desired.
7. Report requested changes or approve before Step 4.

Screenshots: [Desktop editor](03-editor-desktop.png), [Mobile editor](03-editor-mobile.png), [Mobile public page](03-public-mobile.png).
