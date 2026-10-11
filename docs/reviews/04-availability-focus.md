# Step 4 — Availability and Focus Guard

Implemented on 11 October 2026. User approved this step with “ok”; proceeding to Step 5.

## Working behaviour

`/app/availability` stores one host schedule across all event types: schedule timezone, start increment, weekly hours, date overrides, recurring focus blocks, daily host cap, weekly minute cap, clustering preference and an enabled/pause switch. Each day supports up to three non-overlapping windows. Up to 90 unique date overrides replace that day's weekly hours; an empty override closes the day. Saving/reloading retains settings in Supabase. Stale revisions return a conflict rather than overwriting another edit.

Suggested Monday–Friday 09:00–17:00 hours are inactive until the host saves. Initial caps are 4 meetings/day and 12 hours/week; focus blocks start empty and clustering starts off. All defaults are editable proposals for review because SPEC.md is absent. Schedule timezone is persisted independently of profile/home timezone. Changing it retains the local clock hours and changes their UTC instants, with explicit UI copy. The invitee's current/travel timezone changes display and requested dates without moving the host's schedule.

Published event pages now show real Python-calculated slots when availability is saved and enabled. The month calendar marks available days; slot buttons show invitee and host times with UTC offsets, including DST folds. Changing duration, timezone or month clears selection. Every Review first asks the invitee to confirm their current timezone or change it. When using the device suggestion, a changed device zone triggers recalculation before review. Native modal dialog supports keyboard focus containment and Escape. Review shows both exact local times and explicitly does not reserve a booking.

No schedule shows the existing not-configured state; disabled availability shows paused. Empty months, loading, errors and retry are supported. Broad exclusion explanations name notice, horizon, working hours, buffers, focus or caps without exposing the raw schedule or external calendar contents.

## Domain behaviour

The pure slot engine accepts date overrides and recurring focus windows while retaining notice, event/host caps, weekly limits, occupied intervals, buffers and DST handling. Date overrides replace rather than add to recurring hours. Buffers must fit inside a working window and avoid focus blocks. DST gaps skip nonexistent candidate times; boundaries in gaps advance to the next real minute. Focus folds conservatively protect both occurrences.

Clustering recommends up to three existing valid slots per host day nearest real supplied meeting intervals; it does not remove other choices or reorder the chronological list. With no meetings supplied, it makes no recommendation. Daily/weekly caps limit actual occupancy plus a hypothetical candidate, not the number of displayed choices.

Current occupancy is empty because reservation persistence is Step 5 and connected calendars are Step 6. The engine's cap accounting and clustering are tested with injected occupancy; real booked-meeting counts/recommendations will be wired to those sources when implemented. Public UI clearly identifies current inputs as the saved host schedule and does not claim calendar synchronization or booking confirmation.

## Persistence and authorization

Applied Alembic `0003_availability` to development Supabase. The private availability row references the host profile and stores validated local rule data, revision and UTC update time. API reads/writes use verified host identity, restricted role and RLS. Mutations lock the host profile consistently with event writes. Public scheduling reads use the restricted public role and published-event policies; raw weekly/focus/override rules are never returned by public APIs. Metadata reports schedule readiness and the schedule timezone.

## Checks

- 88 Python tests passed; 3 opt-in database checks skipped in the default run.
- All 3 opt-in checks passed against real Supabase PostgreSQL: prior profile/event isolation plus schedule save/reload, revision conflicts, cross-host protection, metadata readiness, focus exclusions, closed/custom overrides, UTC slot values and pause behaviour. Fixtures were rolled back.
- All 16 Playwright checks passed, covering prior functionality plus desktop/mobile schedule save/reload/pause, controls and caps, current/travel-zone confirmation, selection clearing, errors/retry and stale-save rejection.
- TypeScript/production build and Ruff lint/format checks passed. Host authentication code is loaded separately to keep the public entry bundle smaller; the prior bundle-size warning is resolved.
- Desktop and 390px mobile captures visually inspected; no horizontal overflow.

Browser checks use service doubles; database checks use real PostgreSQL and domain checks use injected inputs. The user's real save-to-public-page path is the remaining manual review. Live email sign-in remains unverified from Step 2. The existing test-client deprecation warning remains non-blocking.

## Review path

1. Open `http://127.0.0.1:8017/app/availability` in the signed-in browser.
2. Confirm schedule timezone, set working hours and add a focus block if desired. Save availability.
3. Add a future closed-date or custom-hours override, save, and reload to check persistence.
4. Open an existing published event page from Event types. Check marked dates and displayed times; adjust duration and invitee timezone.
5. Select a time, confirm current/travel timezone, and check both times in Review. No booking is created.
6. Optionally pause availability, then reload the public page to check the paused state. Re-enable when finished.
7. Approve or request changes before Step 5: atomic booking and dashboard.

Screenshots: [Desktop settings](04-settings-desktop.png), [Mobile settings](04-settings-mobile.png), [Mobile public review](04-public-review-mobile.png).
