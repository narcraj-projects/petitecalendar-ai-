# PetCalendar AI functional specification

Version 1.0, 11 October 2026. This specification describes the implemented application and its agreed weekend-project scope. It was derived from the current code and feature reviews; it is not the missing specification referenced by the original design kit.

## Purpose and users

PetCalendar AI lets a host publish meeting links, protect working and focus hours, and accept bookings without exchanging availability messages. Invitees select a duration and time in their current timezone, review the meeting, and receive a private management link. An optional AI assistant helps find times and draft changes using the same scheduling rules as the manual interface.

| Actor | Capabilities |
| --- | --- |
| Host | Sign in, configure a profile, publish events, set availability, connect calendars, inspect bookings, manage changes and review AI proposals |
| Invitee | Open a published link, find times, book without an account, download a calendar file and manage their booking using a private link |
| Signed-in invitee | Use their own verified identity to prefill name and email |
| Operator | Configure provider credentials, deploy services, maintain migrations and enforce the approved spending boundary |

## Current release scope

The core application is implemented. On 11 October 2026 the user explicitly approved opening the existing Railway environment for a public weekend release. The shared staging gate is disabled; host authentication and private booking capabilities remain enforced. Google Calendar consent remains limited to listed Google test users. The homepage identifies the application and links to sign-in; the original Ananya demo is separate at `/ananya/career-strategy`. See [public release details](PUBLIC_BETA.md).

The user purchased `petcalendar-ai.ink`, confirmed Resend verification and reported receipt of a new booking email. Local and Railway web/worker sender settings use `PetCalendar AI <bookings@petcalendar-ai.ink>`; both Railway deployments succeeded after the change. Website hosting remains on Railway. Backups, monitoring and additional launch checks are deferred by the user for this weekend project. Deferred work is not a claim of production readiness.

## Functional requirements

| ID | Function | Implemented behavior and acceptance condition |
| --- | --- | --- |
| FR01 | Authentication | Supabase provides Google sign-in and email-link authentication. Protected host APIs verify the token and derive the host identity from it. An unauthenticated caller cannot edit a host's settings. |
| FR02 | Onboarding and profile | Save display name, unique booking username and IANA home timezone. Review before saving; validation rejects invalid or unavailable usernames. Profile changes apply to subsequent public views. |
| FR03 | Event types | Create drafts and update saved event types; publish or unpublish. Store title, description, slug, location, duration options, default duration, notice, horizon, buffers, daily cap and lifecycle policies. Only published events have public metadata/availability. |
| FR04 | Duration validation | Offer one to six unique durations, each 5–240 minutes in five-minute increments. The default must be one of the offered choices. A booking cannot use a duration removed from the event. |
| FR05 | Working availability | Save one shared host schedule with its own IANA timezone, enabled flag, weekly windows and date overrides. An override replaces that day's ordinary hours; empty windows close that date. Windows must end on the same day and cannot overlap. |
| FR06 | Focus Guard | Exclude recurring focus blocks; enforce host daily count and weekly meeting-minute caps, plus event daily caps. Configurable clustering ranks valid slots near existing meetings without overriding protection rules. |
| FR07 | Slot calculation | Combine saved schedule, event policies, confirmed app bookings and selected Google calendars' busy intervals. Exclude conflicts and buffers; enforce notice and horizon. Recalculate when date, duration or timezone changes. Disabled or missing availability offers no bookable times. |
| FR08 | Current and travel timezone | Suggest the browser's IANA timezone and allow another current/travel zone. Before reviewing a selected slot, require confirmation of the displayed zone. Display host and invitee times. Device settings do not verify physical location. |
| FR09 | Booking | Invitee chooses a slot, confirms timezone, enters their own name/email, reviews and explicitly confirms. The server recalculates availability and commits a confirmed booking atomically. Retrying the same request does not create a duplicate. A contested slot produces a conflict and refreshed selection. |
| FR10 | Private confirmation | Show saved time, duration, both zones, location, snapshotted policy and integration status through a private booking capability. Protect that capability from URL/referrer logging; possession authorizes access to that booking. |
| FR11 | Host dashboard | Show the authenticated host's bookings in a bounded date range, pending change requests and Calendar/email states. Host actions are scoped to that host. |
| FR12 | Calendar connection | Request separate Google Calendar consent, select accessible blocking calendars and a writable destination, and optionally enable Meet. The destination also blocks availability. Save preferences explicitly. Support disconnect, reconnect and permitted delivery retry. |
| FR13 | Calendar and Meet delivery | Queue provider operations after booking commit. Create/reconcile a stable Google event for the booking revision, retrieve the actual Meet link and clean up earlier revisions after changes. Provider failure does not release the confirmed reservation. |
| FR14 | Booking email | When configured, queue invitee confirmation/change/cancellation messages through Resend with meeting details, private management link and an ICS attachment. Wait briefly for Calendar delivery before freezing content. Show provider acceptance separately from inbox receipt. External recipients require a verified sending domain. |
| FR15 | Calendar download | Generate a private `.ics` download from the saved booking, with stable identity and revision information. Access requires the booking capability. |
| FR16 | Cancellation | Enforce the saved invitee cancellation cutoff; permit authorized host handling before meeting start. An accepted cancellation changes local reservation state and queues Calendar cleanup and an email. Repeated identical actions are idempotent. |
| FR17 | Rescheduling | Recheck saved policy and new availability. Immediate changes replace the active time atomically. If approval is required, retain the original reservation while the host reviews up to three alternatives. Alternatives are not held. Support approve, decline and invitee withdrawal. |
| FR18 | Invitee AI assistance | Use page event, selected duration and timezone to find valid slots; undated requests search the next seven days. Booking and rescheduling suggestions open the ordinary review flow. Explain saved policies and propose confirmed cancellation through a scoped private booking link. |
| FR19 | Host AI assistance | Draft changes to an existing event or saved shared schedule/Focus Guard. Present a diff and require explicit confirmation. Creating a new event remains in the ordinary editor. |
| FR20 | AI confirmation and fallback | Bind mutation proposals to exact validated arguments, actor or booking capability, target revision and 15-minute expiry. Reject stale or mismatched proposals. On model failure, refusal, rate limit or budget exhaustion, keep manual controls usable. |

## Main user journeys

### Host setup

Sign in → review name, username and timezone → save profile → create an event draft → save working hours and Focus Guard → optionally connect Google Calendar and save selected calendars → publish the event → share its link.

### Invitee booking

Open the published link → choose duration and date, or ask the assistant → select a valid slot → confirm current timezone → supply contact details or review authenticated prefill → confirm → open the private booking page. The database reservation is immediate; Meet and email delivery can finish later.

Guests need no login. They may open the shared link directly or paste it into the homepage's guest entry. Visible, online booking screens update every 15 seconds and on tab return/reconnection; same-browser successful actions notify other tabs. Public slots, host lists/Focus Guard counts and private booking/delivery states refresh while preserving contact drafts. If another guest takes a selected slot, selection clears and a notice asks for another time.

### Booking changes

Open the private link or host dashboard → choose cancellation or replacement times → review policy and details → explicitly submit. An approval request keeps the original time occupied until the host approves a freshly available alternative. Decline or withdrawal leaves the original reservation intact.

## Scheduling rules

All stored meeting instants use UTC. Recurring hours use local wall time plus an IANA timezone. Day/week cap accounting follows the saved schedule timezone; weekly meeting minutes exclude buffers. Nonexistent daylight-saving times are skipped and valid instants remain unambiguous internally.

Each confirmed booking blocks a half-open interval expanded by its saved before/after buffers. Host-wide overlap protection applies across event types. Changing future event policies does not rewrite existing booking policy/buffer snapshots. New slots are recalculated before every mutation, including an AI-assisted action.

Google occupancy is checked outside the short booking transaction and the connection version is checked during commit. A Google event created concurrently can still conflict because Google and PostgreSQL cannot commit atomically.

## Validation and failure behavior

| Situation | Required response |
| --- | --- |
| Invalid date, duration, contact or timezone | Reject with a structured validation error; retain a usable form |
| Unpublished/missing event | Do not expose a bookable event |
| Slot taken or settings changed | Reject the mutation; ask the client to refresh availability |
| Missing/invalid host token | Deny protected APIs |
| Invalid private capability | Do not reveal booking details |
| Connected calendar cannot be checked | Surface the provider problem instead of assuming the calendar is free |
| Calendar/email delivery problem | Preserve booking state and show separate delivery status |
| Stale or expired AI proposal | Require a new proposal/review |
| Spending boundary reached | Interrupt the affected provider function; retain manual behavior where available |

## Privacy and operating requirements

Host identity comes from verified Supabase authentication. Browser business operations go through FastAPI; application tables are in a private PostgreSQL schema with restricted roles and row-level policies. Provider keys stay server-side, and Google refresh tokens and delivery payloads use authenticated encryption.

Do not log contact details, tokens, private capability URLs, raw calendar contents or unredacted conversations. AI requests exclude stored contacts and calendar event contents; contact prefill is a separate authenticated feature. Conversation history stays in browser memory. `store=false` does not imply every provider retention policy is disabled.

Use the approved Midnight interface on desktop and mobile, semantic controls, visible states and accessible touch targets. No latency or uptime SLA is promised. The private staging health endpoint checks process responsiveness, not database/provider readiness.

The approved allowance is USD 20/month total including fees: Railway USD 10 cutoff, OpenAI USD 3 enforced project limit, Supabase/Resend Free, and USD 7 reserve. Provider metering can lag. Domain purchase is separately user-confirmed; no automatic renewal, plan upgrade or cutoff increase is authorized by this specification.

## Deferred features

Payments/deposits/refunds, WhatsApp, reminders, Mutual Match with invitee calendar access, polls, teams, a retained chat store and automatic event creation by AI are outside the implemented core. Shared AI rate limiting, backup/restore verification, monitoring and broader public-release acceptance are also deferred. The original kit's examples for these features are not active application behavior.

## Verification and acceptance

Existing verification includes 196 backend tests, seven opt-in PostgreSQL checks, container CI and per-feature browser test suites. Hosted staging checks observed authentication/onboarding, slots, a booking, Meet, earlier Calendar revision cleanup, provider-accepted emails and live AI slot suggestions. These historical results do not prove every live lifecycle path or inbox delivery in the current provider configuration.

For each next increment: test the changed behavior, check authorization/conflicts and provider failure handling where applicable, then review the user journey. For the purchased domain, acceptance requires verified Resend DNS, the updated sender and an actual invitee inbox check before claiming delivery works.

## Related documents

- [High-level design](HIGH_LEVEL_DESIGN.md)
- [Low-level design](LOW_LEVEL_DESIGN.md)
- [Architecture decisions and future direction](ARCHITECTURE.md)
- [Implementation plan](IMPLEMENTATION_PLAN.md)
- [Private staging review](reviews/10-private-staging.md)
