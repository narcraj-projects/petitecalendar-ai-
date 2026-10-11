# PetCalendar AI design adaptation

Preserve Midnight's dark surfaces, lime primary actions, amber protection cues, Space Grotesk headings and Manrope body text. Add conversational assistance while keeping dates, both timezones, duration, price and policies visible. The original screens remain the visual baseline.

## Public booking and assistant

Keep host context left and calendar/slots right on desktop. Mobile retains compact day selection, with month navigation available. Add an optional Find a time with the assistant action when the agent milestone is implemented. It opens a desktop side panel or mobile sheet while preserving manual selection.

Agent results use API-backed slot cards with exact date, both zone times and duration. Calendar clicks and agent suggestions open the same review card. Suggested is distinct from reserved; success appears only after the command commits. The first functionality has real slot selection with demo schedules, not a pretend chatbot.

## Host configuration

Add an assistant composer above event types. Generated event settings appear as a draft with a before/after diff, affected slot count and Apply changes. Existing manual controls remain. Focus Guard suggestions use amber and preview their consequences without implying settings are already saved.

## Confirmation and management

Retain both timezone tiles, location, calendar download and manage actions. Separate booking confirmed from calendar/email delivery pending. Render actual payment and delivery states rather than sample success copy. Default WhatsApp consent to unchecked until explicitly selected, although the reference screen shows a checked example.

Policies come from the booking snapshot with deadlines calculated in the invitee timezone. Manual and agent reschedules share one action-review component.

## Components and accessibility

Reuse DurationToggle, MonthCalendar, MobileDayStrip, SlotList, TimezoneLine, MutualMatchBanner, StatusChip and FocusGuardBar. Add AssistantPanel, ClarificationChoice, SlotProposalCard, SettingsDiff, ActionReviewCard and IntegrationStatus at the relevant milestones.

Provide loading, empty, error and retry states. The assistant additionally needs clarification, searching, proposal, confirmation, execution and failure states. Announce changes accessibly and preserve focus. Use semantic controls, 44px targets and meaningful 4.5:1 text contrast. Verify dim tokens and host accent overrides on their actual surfaces. The IANA zone, not a city label or fixed offset, drives calculations.

Review the first functionality at 390px and 1280px with duration/date/zone changes and slot selection. Later reviews add actual agent and integration states without redesigning the core flow.

## Current timezone confirmation

Label the timezone as Suggested by your device or Selected by you. Support the browser's full IANA timezone list, including travel destinations. Review first opens Check your current time zone with the selected IANA zone, Yes confirm zone and review, and Change my time zone. Only explicit confirmation opens the time summary. The change action returns focus to the timezone selector; changing zones refreshes slots and clears the old selection. Each new review requires confirmation again. Do not claim to verify physical location.
