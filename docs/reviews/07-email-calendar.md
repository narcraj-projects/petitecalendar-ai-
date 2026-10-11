# Step 7 review: email confirmations and calendar downloads

Implemented on 11 October 2026 after live Calendar/Meet acceptance and the user's "ok". Core functionality is built; live email delivery and the user's review remain pending.

## Working behaviour

New bookings made while email is configured queue one invitee confirmation with the booking-confirmed outbox record and reservation. The email includes title, saved date/time, both timezone labels, duration, location/Meet when ready, a private booking link and an ICS attachment. There is no host notification in this first scope. Earlier bookings are not emailed retrospectively.

A separate email adapter/worker role uses the same worker process as Calendar delivery. It leases jobs, recovers expired leases, checks booking revision/status and briefly waits for Meet before freezing the message. Retries use exactly the same body and stable booking/revision idempotency key. Bounded retries stop before Resend's 24-hour key expiry; uncertain acceptance is not automatically resent later. Reservations stay confirmed on delivery failure.

Host dashboard and private confirmation show queued, working, retry, accepted, failed or uncertain status. Accepted means the service accepted the send request, not verified inbox delivery. Signed delivery webhooks are a later improvement. Failed/uncertain jobs do not expose a resend action that could duplicate a message.

Calendar downloads work for existing and new private confirmations without email configuration. The authenticated-capability header protects the download; the token is never in the API URL. Files use UTC instants, stable UID, saved creation stamp/revision, both-zone descriptions, UTF-8 octet folding and escaped text. No guest email or private capability enters the ICS. It publishes an entry without organizer/attendee invitations. Meet is included when ready; repeated files retain the UID, although calendar clients vary in update behaviour.

## Persistence and privacy

Migration `0007_booking_email` is applied to development Supabase. Forced RLS and column grants expose only host/private booking email status; no payload, recipient copy or capability ciphertext reaches those APIs. The email worker can read required guest contact/snapshot fields with its own NOLOGIN role. The Calendar worker's booking grants still exclude guest email.

The booking capability remains hashed on the booking row. A temporary host-bound encrypted copy and frozen message live in the email job, using the existing TOKEN_ENCRYPTION_KEY. Terminal outcomes clear both ciphertexts. Provider payloads/errors, emails and keys are not logged. The sender/key stay server-only.

## Verification

- All 135 Python checks passed, including 16 new email/ICS checks for UTC/DST, stable UID, multiline injection, Unicode folding, attachment privacy, HTML escaping, private download headers, Calendar-only email exclusion, pending-Meet deferral, expired retry windows and Resend status/error handling.
- All five real PostgreSQL checks passed. The expanded Calendar/email test verifies atomic queueing, host isolation, inaccessible ciphertext columns, encrypted link/message storage, lease recovery/stale completion, a simulated timeout followed by identical retry, one accepted job, terminal ciphertext deletion and exact booking retry after acceptance.
- All 28 browser checks passed, including private download/capability headers, actual saved filename/UID, queued-to-accepted refresh, uncertain status, failed download/retry and desktop/390px screenshots.
- TypeScript/production build and Ruff lint/format passed. Final copy was rebuilt. Screenshots were visually inspected.

All provider sends in tests are doubles. No real email was sent by the agent. Database fixtures use random synthetic IDs and are cleaned up; delivery workers were stopped during those tests. Resend key/sender presence is configured, but live acceptance/inbox delivery is unverified. The current test sender sends only to the Resend account's address; other recipients require a verified domain. Development private links open only on the local app computer.

## Current runtime and approval

The API and combined Calendar/email worker are running after explicit user approval. Automatic approval review rejected starting the combined worker because it would send invitee addresses, booking details, private links and attachments to Resend without explicit authorization for the recipients/payloads. All unaffected implementation and checks are complete. The user explicitly approved activating confirmation emails for new bookings via Resend, with the recipient and payload contract shown in the approval question. The combined worker then started successfully. No workaround was used. Live email acceptance/inbox review remains pending.

## Review path

1. Open an existing private confirmation and click Download calendar (.ics). Import/check the saved times and Meet location.
2. After email activation is approved, make a new test booking at your published event page using your Resend account email. Keep its private link.
3. Refresh email status, then check inbox/spam and open the attachment and private link.
4. Verify the meeting time, both zone labels and Meet link, and confirm one email arrived.
5. Approve or request changes. After the core review, choose the next improvements, including the scheduling AI agent.

[Email setup](../EMAIL_SETUP.md). Screenshots: [mobile confirmation](07-confirmation-mobile.png), [desktop confirmation](07-confirmation-desktop.png).


## Live email review update

The user confirmed inbox receipt on 11 October 2026 after correcting the booking form recipient. The earlier Delivered entry was addressed to the Resend test sender, not the user's inbox. A subsequent booking used the intended account address and the user reported it works. Calendar-file import details have not separately been confirmed. The user chose to retain test mode rather than verify a sending domain, then authorized Step 8 cancellation/rescheduling. Resend acceptance remains distinct from delivered status in the app.
