# Prompts to paste into Codex (one at a time)

Historical reference only: the user selected Python, Supabase and agentic AI. Follow AGENTS.md and docs/IMPLEMENTATION_PLAN.md instead of the original technology instructions below. Implement one functionality and stop for review.

Tip: start each prompt by asking Codex to "list your plan and the files you'll touch first".
Attach the matching screenshot from docs/design/screenshots/ when a prompt builds a screen.

## 0. Design foundation (do this right after scaffolding)
Read AGENTS.md, docs/SPEC.md and docs/DESIGN.md. Set up the "Midnight" design system: add the colour,
font and radius tokens to tailwind.config.ts, load Space Grotesk and Manrope with next/font, map the
shadcn/ui CSS variables in globals.css to the tokens, and make dark the default theme. Then build a
/design-preview page showing every token and these components: DurationToggle, MonthCalendar,
SlotList, MutualMatchBanner, TimezoneLine, StatusChip, FocusGuardBar. Match docs/design/01-booking-desktop.html.

## 1. Scaffold
Scaffold the Next.js + TypeScript project with Tailwind, shadcn/ui, Drizzle (Postgres), Vitest,
Playwright, ESLint, Prettier and the folder structure in SPEC section 5. Add .env.example. No features yet.
(Run this before prompt 0.)

## 2. Schema
Implement the MVP tables in SPEC section 6 with Drizzle, including the bookings exclusion constraint via
a raw SQL migration (enable btree_gist). Add a seed script with one host, two event types and a weekly schedule.

## 3. Auth + onboarding
Add Auth.js with Google (calendar scopes, offline access) and email magic link. Build the 4-step
onboarding wizard (SPEC section 10) in the Midnight style, plus encrypted token storage (SPEC section 11).

## 4. Availability engine (test-first)
Implement getAvailableSlots exactly per SPEC section 7. Write Vitest tests first (DST, Asia/Kolkata,
Asia/Kathmandu, buffers, min notice, daily caps, focus blocks, Mutual Match). Then implement until green.

## 5. Host screens
Build /app/bookings and /app/event-types/[id] to match docs/design/04-host-dashboard.html and
docs/design/05-event-type-editor.html, using the /api/me routes in SPEC section 8. Use seed data.

## 6. Public booking flow
Build /[username]/[slug] to match docs/design/01-booking-desktop.html on desktop and
docs/design/02-booking-mobile-mutual-match.html on mobile, then /booking/[uid] to match
docs/design/03-confirmation-mobile.html. Wire the slots API, booking creation with transaction + 409
handling, Google Calendar event with Meet link, and Resend confirmation email with ICS.

## 7. Reschedule, cancel, reminders
Manage links and policies, Inngest reminder jobs (24 h and 1 h), WhatsApp Cloud API adapter with opt-in.

## 8. Payments
Razorpay and Stripe adapters, 15-minute pending hold, signed webhooks, deposits and refunds per policy.
