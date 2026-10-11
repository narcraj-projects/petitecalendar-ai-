# AGENTS.md — PetCalendar AI

## Source of truth
- The user selected Python, Supabase and agentic AI on 11 October 2026. This overrides the technology choices in the original ZIP.
- Read docs/ARCHITECTURE.md, docs/IMPLEMENTATION_PLAN.md and docs/DESIGN_ADAPTATION.md before implementation.
- Read docs/SPEC.md if supplied; it is missing from the original kit. Mark unresolved functional requirements explicitly.
- Implement one functionality at a time and stop for user review before advancing.
- For anything visual, follow docs/DESIGN.md and match the reference screens in docs/design/
  (and docs/design/screenshots/ if present). Same colours, fonts, spacing, copy and hierarchy.

## Stack
- Python FastAPI, Pydantic, SQLAlchemy and Alembic; Supabase PostgreSQL and Auth.
- React, TypeScript and Vite frontend with shared Midnight CSS tokens.
- Python agent orchestrator with typed tools and an LLM provider adapter.
- PostgreSQL durable jobs and outbox, Python worker, integration adapters.
- pytest, Ruff, TypeScript checks and Playwright.

## UI rules
- Use only the Tailwind tokens defined in docs/DESIGN.md; no raw hex values in components.
- Fonts: Space Grotesk for headings and Manrope for body text; load through the frontend rather than next/font.
- Dark theme is the default. No gradients, no shadows, no emoji.
- Touch targets at least 44px; text contrast at least 4.5:1; real <button>, <a>, <label> elements.
- Every page must work at 390px wide (mobile) and 1280px+ (desktop).
- Build reusable components in frontend/src/components. Adapt agent interactions according to docs/DESIGN_ADAPTATION.md.

## Engineering rules
- Store all times in UTC (timestamptz); timezones as IANA strings.
- backend/app/domain/availability.py must be pure with no I/O; inject `now` and external busy intervals.
- Every external service goes through backend/app/integrations with a test double.
- Validate API and agent tool inputs with Pydantic; return { error: { code, message } } on failure.
- Derive host identity from verified Supabase authentication, never a client-supplied owner ID.
- All reservations and holds go through the same transaction service. Agents never bypass domain rules.
- Agent mutations require explicit confirmation bound to exact arguments, actor, revision and expiry.
- Never log tokens, emails or phone numbers.
- Never log raw calendar data or unredacted agent conversations.
- Add meaningful tests for implemented behaviour and run relevant checks. Document checks blocked by missing credentials.
- Update architecture and plan when approved behaviour changes. Preserve the source ZIP.

## Commands
- Exact development and check commands are established in README.md by each functionality. Old pnpm and Drizzle commands do not apply.
