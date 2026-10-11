# Step 9: scheduling assistant

Implemented on 11 October 2026 after the user's Step 8 acceptance. Live usability checks passed; the refined user review was subsequently accepted below.
The user accepted the refined assistant review with "ok done" on 11 October 2026. GitHub preparation now precedes deployment at the user's request.

## Behaviour

- Public booking pages: optional assistant, scoped live time search over up to 14 days, eight engine-approved results at a time, exact date/timezone/duration cards, current/travel-zone confirmation and the existing booking form. No booking is made by asking for suggestions.
- Private booking management and host dashboard: replacement suggestions enter the existing lifecycle review; saved policies are explained from the snapshot; cancellation requires a separate explicit confirmation. Saved cutoffs, revision checks and durable provider jobs apply.
- Host event-type list: choose a saved event or shared availability/Focus Guard, draft numeric/boolean policy changes or weekly/focus/cap changes, compare current/proposed settings and explicitly apply. New event creation, date overrides and publication remain in the conventional editors. A numerical affected-slot preview is not included in this increment; live availability recalculates after saving.
- Clarification, working, no-match, expired, invalid, uncertain and provider-unavailable states keep manual controls available. Conversation history is ephemeral and capped at six messages; common contact/key/link/capability patterns are redacted before provider requests. Stored invitee names/emails, calendar contents and credentials are not model context.

## Confirmation and failure handling

Each model response may request exactly one strict, scope-specific tool. Unexpected tools, malformed arguments, incomplete responses and refusals fail closed. The provider has a 35-second request timeout and 1,800 output-token ceiling. Four concurrent calls, 20 requests per actor/IP per hour and a global 200/hour cap bound this single-process preview. Public release needs shared limits and measured model cost/latency.

Settings/cancellation proposals contain encrypted exact arguments, actor or private-capability scope, target revision and a 15-minute expiry. The browser cannot edit a proposal's arguments. Changed targets conflict; exact settings retries recognize the same next revision without saving twice. Cancellation uses the existing lifecycle journal/idempotency key. New booking/reschedule choices use the conventional domain confirmation and fresh availability checks. Suggested slots have no holds.

`store=false` is sent to OpenAI. This disables response storage for the request; it is not a claim of zero retention under every provider/account policy. No raw conversations are persisted by PetCalendar AI.

## Verification

- 175 Python checks passed; seven database checks are opt-in. The 28 assistant checks cover scope, expiry, tampering, exact retry, stale revision, invalid settings/windows, privacy redaction, strict tool schemas, hostile/malformed output, multiple calls, timeout, quota, refusal and manual fallback contracts. A regression check verifies the generator-based calendar dependency is resolved and closed correctly, including paused availability.
- The new real PostgreSQL check passed: drafts are read-only, cross-host access/confirmation fails, confirmation saves through existing RLS/host locks, an exact replay does not increment revision, and a changed revision rejects the old proposal. All fixtures roll back; no booking or provider job is created.
- Ruff, TypeScript and the production build passed. All 36 browser scenarios passed across the full run and the final targeted rerun. Four initial failures exposed ambiguous timezone labels after adding the assistant; naming its field **Assistant time zone** fixed the collision. The 12 affected assistant/availability/booking scenarios then passed. Desktop and 390px screenshots are visually reviewed, with no page overflow and assistant buttons at least 44px tall.
- The saved key authenticates successfully and the initial model is available. After the user added credits, normal synthetic live cases passed: duration/buffer draft (594 input/80 output tokens, 3.07 seconds), London weekday/afternoon search (489/58 tokens, 3.23 seconds), and clarification (586/44 tokens, 4.05 seconds). These successful calls total 1,442 input and 182 output tokens; currency cost is not estimated without a verified account tariff. A repeat passed the first two cases but hit a provider rate limit on clarification. Hostile requests returned a safe provider-unavailable error and executed no tool, rather than the preferred clarification response. This is a small smoke evaluation, not a comprehensive model comparison or reliability claim.
- The real public assistant endpoint returned HTTP 200, engine-derived slots, Europe/London, and a correct no-match result against saved availability and connected calendars. No reservation was created. An initially detected calendar dependency wiring error was corrected and covered by the regression check above.

## Review path

1. With API credits available, open the published booking page and ask **Book me a meeting** or **Next Tuesday afternoon in London**. Confirm the actual current/travel zone before reviewing a suggestion. Signed-in users see their own saved contact summary; guests enter details once per page visit. Booking still requires explicit confirmation.
2. At `/app/event-types`, select the intended saved event and ask **Make this 45 minutes with a 15 minute buffer**. Check the duration/buffer diff and apply only if desired. Reload and check the conventional editor.
3. Select **Shared availability & Focus Guard** and ask **Limit me to two meetings per day**. Review the shared impact before applying.
4. From a private confirmation link, ask for a replacement date or **Explain my cancellation policy**. Use **Cancel this booking** only for a test booking you intend to cancel; asking merely drafts it.
5. Report the results/changes. Live evaluation and this review precede deployment.

Email remains in the restricted Resend test mode selected earlier. No real booking, calendar mutation or email was performed by the assistant implementation/evaluation checks.

Screenshots: [mobile time review](09-assistant-mobile.png), [host draft on desktop](09-assistant-host-desktop.png).

## Refinement after user feedback

The assistant now uses known event, duration and selected zone rather than asking for them again. An ordinary undated request searches the next seven days; unspecified hours use the full day. It only asks for essential unresolved information and does not collect contact details through chat. The booking form fills the signed-in person's own profile name and verified email through an authenticated endpoint, with an edit option. Unknown guests enter their details once; their edits survive changing suggested times, in page memory only. Neither mechanism supplies contacts to OpenAI. Timezone review and explicit final confirmation remain required.

The refined backend passed 177 Python checks (seven opt-in database checks skipped), and Ruff and the production frontend build passed. All 18 targeted assistant, authentication and reservation browser scenarios passed before the final request-cleanup refinement. The live synthetic usability evaluation passed **Book me a meeting**, **Tomorrow** and **Any time next week**, each selecting `find_times` directly with the expected dates and known context (2.83–3.58 seconds). These were read-only interpretation checks; no booking or provider job was created.

After the final request-cleanup refinement and server restart, all six assistant browser scenarios passed again, including automatic contact confirmation and guest contact persistence. The anonymous contact endpoint returns 401. [Signed-in contact review at mobile width](09-assistant-known-contact-mobile.png).
