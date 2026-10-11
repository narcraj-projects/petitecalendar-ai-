# PetCalendar AI implementation plan

Build one functionality, verify and demonstrate it, then stop for user review before advancing. Use the Python, Supabase and agent architecture in [ARCHITECTURE.md](ARCHITECTURE.md), and the Midnight adaptations in [DESIGN_ADAPTATION.md](DESIGN_ADAPTATION.md). Changes requested during review stay within the current functionality.

## Core functionality sequence

On 11 October 2026 the user approved prioritizing the core booking flow, keeping a review after each functionality, and choosing the order of remaining improvements only after the core build. Steps 1–5 retain their numbers; Google Calendar is now Step 6 and email/ICS Step 7. The AI assistant remains in scope and moves after the core review.

| Step | Functionality | Acceptance and dependencies |
| --- | --- | --- |
| 1 | Public availability preview | Python slot engine and responsive booking UI; change duration/date/timezone and review a slot. Label demo fixtures. No booking creation or credentials needed |
| 2 | Host identity and onboarding | Supabase Google/email login, profile, username and zone. Reject unauthenticated and cross-host requests. Requires development Supabase project |
| 3 | Event type management | Extend SQLAlchemy/Alembic models introduced for Step 2 profiles; list/editor, duration options, policies and publication. Create, reload and publish a unique route |
| 4 | Availability and Focus Guard management | Persist weekly hours, overrides, blocks, caps and clustering. Changes update public slots and exclusion explanations |
| 5 | Free booking and dashboard | Atomic reservation, host lock, exclusion constraint, idempotency, secure manage capability and confirmation. Simultaneous attempts produce one booking |
| 6 | Google Calendar and Meet | Separate consent, selected calendars, encrypted refresh tokens, live free/busy and durable event delivery. Verify one event/Meet link under retries |
| 7 | Email and calendar download | Resend, ICS and outbox delivery. Show actual delivery status and correct timezone/calendar UID |

## Improvements to sequence after the core review

Step 4's proposed implementation uses one persisted host schedule for all event types, an independent schedule timezone, weekly/date windows, focus blocks, host caps and soft recommendations. The public page computes slots from saved event/schedule settings; no default schedule is activated before Save. Real booking occupancy is introduced in Step 5 and calendar occupancy in Step 6. See [Step 4 review](reviews/04-availability-focus.md).

The user confirmed live email receipt and selected cancellation/rescheduling next on 11 October 2026. This is Step 8. The user's subsequent "ok" accepted that review, and Step 9 is the scheduling assistant. Deployment follows its review; other improvements remain to be sequenced.

| Functionality | Acceptance and dependencies |
| --- | --- |
| Host and invitee scheduling agent | Typed tools, clarifications, drafts, confirmed mutations and UI. Test conflict, hostile content and model failure; no mutation before bound confirmation |
| Cancellation and reschedule | Policy snapshots, manage links, approval requests and alternative times. Replace reservation atomically or preserve the original on failure |
| Email reminders | Durable 24 hour and 1 hour jobs. Cancellation, new revisions and worker restarts cannot send stale reminders |
| Mutual Match | Temporary read-only invitee calendar filter and Show anyway. Verify event data never enters DB/logs/LLM; review token lifetime and copy |
| Razorpay payments | Server-priced checkout, 15 minute holds, signed webhooks, deposits and refunds. Test duplicate events and late capture against expiry in test mode |
| Stripe payments | Reuse payment domain, add adapter and repeat the same provider contract tests |
| WhatsApp reminders | Explicit consent, template configuration, opt-out and current-revision delivery |
| Release readiness | Staging deployment, backup restore, secrets, supervision, limits and lifecycle regression. Production release is a separate decision |

This is dependency order, not a calendar deadline. The domain can accept busy intervals and active holds before live integrations exist. Agent tools reuse established booking services. Each provider requires its own credentials only at its milestone.

## First functionality

Build /ananya/career-strategy with host context, 30/45/60 minute choices, month calendar, mobile day strip, slots, editable timezone and selected-slot review showing both zones. Use a seeded schedule adapter and clearly label Demo schedule. The review card does not create a booking; no payment, Meet or sent-email success is simulated.

Expose GET /api/health, GET /api/public/events/{username}/{slug}, and GET /api/public/events/{username}/{slug}/slots with bounded start/end dates, selected duration and invitee zone. Return UTC instants and available dates. Validate parameters with Pydantic, reject unknown events and excessive ranges, and return structured application errors. The Python engine is the only slot generator.

Test notice, occupied intervals, buffers, focus windows, duration variants, daily and weekly caps, DST, Asia/Kolkata and Asia/Kathmandu. Browser review covers duration/date/timezone selection, month navigation, empty/loading/error states and 390px/desktop layouts. Record exact setup and check commands in README.md.

## Schema and service preparation

Steps 1–4 have been reviewed. Step 5 implements free, immediately confirmed bookings with required name/email, UTC start and duration, confirmed invitee timezone, saved policies/buffers and an account-free private confirmation capability. These contact and confirmation defaults fill the missing SPEC and remain reviewable proposals. Host dashboard lists upcoming/past bookings by host-local month and independently counts the current host-local week. Payment, cancellation/reschedule, calendar and email controls remain at their assigned milestones. See [Step 5 review](reviews/05-booking-dashboard.md); the user approved this review with "ok" before Step 6.

Before identity, configure a development Supabase project with redirect URLs and email delivery. Before schema, resolve proposed policy defaults. Alembic alone owns application migrations; do not independently edit the same schema in the dashboard. Keep placeholders in environment examples and real credentials ignored.

Reserve app, api, booking and assets usernames. Public metadata includes only published fields. A public booking UID alone does not authorize invitee details or management. Database correctness tests must use PostgreSQL, since SQLite cannot represent the reservation constraints and locking.

## Agent acceptance examples

| Scenario | Expected result |
| --- | --- |
| Make this 45 minutes with a 15 minute buffer | Typed settings diff; confirm before saving |
| Tuesday afternoon in London | Resolve exact date/zone and return engine-approved slots |
| Duration changes after a proposal | Invalidate the old proposal and recalculate |
| Slot disappears before confirmation | Conflict and fresh options, never a success claim |
| Event description asks to ignore policy | Content cannot change tool permissions |
| Request reads another host's bookings | Authorization blocks tool execution |
| Cancel this booking | Show identity and saved policy, then require bound confirmation |
| Model times out or exceeds budget | Conventional calendar remains usable |

Use model doubles for deterministic tests, then a measured live-model evaluation to choose provider and model. Record redacted metrics for accuracy, latency, cost and failure categories; do not persist invitee chat by default.

## Review protocol

For each step, record working behaviour, real versus demo services, checks run, limitations and a short manual review path in docs/reviews. Keep the local preview available during review and wait before starting the next step. Apply feedback, rerun relevant checks and update the review note.

Polls, teams, round-robin routing, subscription billing, additional calendar providers and retained agent memory require separate functional scope. Missing SPEC.md does not prevent the labelled first preview, but exact policies must be resolved before their respective booking/payment features.

## Step 1 travel timezone feedback

Use the device timezone as a suggestion for the invitee's current or travel zone. Require explicit confirmation before each review and provide a change-zone path that recalculates availability and clears the previous selection. Browser checks cover device detection, a travel override and the confirmation boundary. This refinement stays within Step 1.

## Step 2 implementation scope

Supabase email magic-link and Google OAuth sign-in use the client SDK with PKCE. FastAPI verifies the Supabase identity before reading or saving a profile. The proposed onboarding sequence is display name, unique booking username, home timezone, then explicit review/save. This fills the missing SPEC onboarding details and is subject to user review. Host home timezone is stored separately from the invitee travel zone.

Introduce only the profile migration in Step 2 because persistence is necessary for onboarding. Future event/schedule/booking tables belong to their own steps. Reserve framework route names, derive ownership solely from authentication, and isolate database transactions with a restricted role and RLS. A saved username does not publish a booking page. Provider configuration and a real user sign-in remain part of live acceptance; browser tests use isolated service doubles without adding application authentication bypasses.

## Step 6 implementation scope

Step 6 is built, tested and live-verified after the user completed the review booking flow on 11 October 2026. Separate Google consent, encrypted host-bound refresh tokens, selected blocking calendars, a writable destination and optional Meet are implemented. The destination always blocks time. Caps count PetCalendar AI bookings; external free/busy protects availability. Provider failure stops connected-host slot generation and reservations.

A confirmed booking and pinned calendar job commit atomically after host lock and connection revision checks. A separate Python worker uses leases, bounded retries, deterministic event/Meet request IDs and saved Google account generation. Status and Meet links appear on host dashboard and private confirmation. Existing bookings are not backfilled; Google guest invitations are not sent. Read [Step 6 review](reviews/06-google-calendar.md) and complete actual Google consent/event acceptance before Step 7.

## Step 7 implementation scope

Step 6 live acceptance passed and the user approved continuing with "ok". Step 7 implements invitee email confirmations through Resend, private calendar downloads, durable outbox-linked jobs and actual queued/accepted/failed/uncertain status. Confirmations include both saved zones, a private link and an ICS attachment; the worker briefly waits for Meet and freezes retries to avoid body changes. Provider acceptance does not claim inbox delivery. Earlier bookings are not emailed retrospectively. Host notifications, signed delivery webhooks and reminders are separate improvements. See [email setup](EMAIL_SETUP.md) and [Step 7 review](reviews/07-email-calendar.md). After this core review, ask the user to sequence the remaining improvements, including the AI agent.


## Step 8 implementation scope

The user selected cancellation/rescheduling after confirming booking email receipt. Build invitee and host action reviews, saved deadlines, immediate cancellation, atomic direct rescheduling, optional host approval with up to three alternatives, decline/withdrawal, durable Google cleanup and changed-booking emails/ICS. Proposed times have no holds. Host actions may override the invitee cutoff only before the meeting starts. Keep email in the existing restricted test mode. Stop for user review at the private booking page and host dashboard before implementing the AI assistant or deployment. See [Step 8 review](reviews/08-booking-lifecycle.md).

## Step 9 implementation scope

Step 8 was accepted with "ok"; that acceptance does not independently establish live Calendar/email lifecycle verification. Step 9 adds the OpenAI scheduling assistant to published event pages, private booking management and the host event-type list. Invitees find engine-approved times in their current/travel zone, then confirm that zone and use the same booking form or lifecycle review. Hosts draft changes to existing event durations, buffers, limits and policies or saved shared availability/Focus Guard. Settings and cancellation proposals require explicit confirmation with encrypted exact arguments, actor/capability scope, target revision and a 15-minute expiry. New event creation remains in the conventional editor.

Use deterministic provider doubles, real PostgreSQL confirmation/isolation checks, responsive browser checks and an opt-in synthetic live evaluation. OpenAI billing and measured live-model results must be verified before declaring live AI acceptance. The current model is configurable; `gpt-6-astra` is the initial candidate, not a completed cost/latency comparison. No deployment is started before this review. See [Step 9 review](reviews/09-scheduling-assistant.md).

The user's Step 9 feedback requested fewer clarification questions and automatic contact entry. The refinement uses known page context and a seven-day default search, prefills the signed-in invitee's own verified contact, and retains guest edits while changing times. Contact lookup remains outside AI context. This is part of the current review; deployment still waits for acceptance.

## Application name and GitHub handoff

On 11 October 2026 the user named the application **PetCalendar AI**, with **petcalendar-ai** as the GitHub repository name. UI labels, browser title, API metadata, model instructions, calendar product label and package names reflect the new name. Existing database roles, Google private markers and stable calendar UIDs keep their original internal identifiers to preserve existing bookings and connected calendars. The user moved the original ZIP and draw.io workflow into an external backup. Git ignores those formats, credentials, local tooling and review screenshots. The refined Step 9 review was accepted; GitHub handoff precedes deployment.
