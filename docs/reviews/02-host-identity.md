# Step 2 — Host identity and onboarding

Implemented and approved by the user on 11 October 2026. The user completed live Google sign-in and onboarding; a count-only database check confirmed a persisted host profile. The user accepted the current flow and appearance with no requested changes. Step 3 may proceed.

## Working implementation

- `/login`: Supabase Google OAuth and email magic-link sign-in, with PKCE and loading/error/inbox states.
- `/auth/callback`: exchange OAuth codes or verify email token hashes once, clear callback parameters immediately, then enter onboarding.
- `/onboarding`: display name, unique username, home timezone and explicit review/save. Device zone is a suggestion; host home zone is separate from invitee travel zone.
- `/app/profile`: persisted profile summary, editing and sign-out. Refresh loads the saved record from Supabase through FastAPI.
- `/api/me` and `/api/me/profile`: verified JWT ownership, validated fields, forbidden owner input, structured failures and username conflict handling.
- Alembic `0001_host_profiles`: private profile schema, auth user foreign key, unique usernames, restricted role and PostgreSQL RLS. Migration applied to the configured development project.

The public booking preview still uses its labelled demo schedule. Saving a host profile reserves a username but does not publish an event or book a slot. Onboarding's four-step sequence is a proposed implementation because the original kit omitted SPEC.md.

## Checks

- 47 Python tests passed; the opt-in database test skips in the default run.
- The opt-in database test passed separately against the actual Supabase PostgreSQL database: tenant read/update/insert isolation, exact uniqueness error, and real repository save, update, reload and conflict handling. All fixtures were rolled back; no test accounts or profiles remain.
- 11 Playwright checks passed: existing availability behaviour, email request with PKCE, Google redirect, single OAuth exchange, callback cleanup/expiry, mobile onboarding/review, username conflict recovery, reload, sign-out, protected routing, rejected session and storage retry.
- Frontend TypeScript/build passed; Ruff lint and format checks passed.
- Desktop and 390px mobile screenshots inspected; no horizontal overflow. [Desktop login](02-login-desktop.png), [Mobile review](02-onboarding-mobile.png).

Browser authentication tests use service doubles and synthetic sessions. They exercise the real SDK and UI without sending emails or contacting Google. They do not establish real provider login success. PostgreSQL tests use the real database. The authentication and persistence implementation has no demo authentication bypass.

The existing Starlette/httpx test-client deprecation warning remains a dependency warning, not a failed test.

## Live configuration and acceptance

The saved environment successfully connects to the development database. The project exposes an ES256 signing key and has email login enabled. Google provider enablement was verified, and the user completed Google consent and confirmed onboarding/profile save. A subsequent database query confirmed a persisted profile without displaying personal data. Follow [Supabase setup](../SUPABASE_SETUP.md) for exact local redirect URLs and email templates. Email delivery to recipients outside the Supabase organization may require custom SMTP.

Live email delivery/callback remains unverified; email browser checks use a test double. The user approved the current flow and appearance. Development uses a migration-capable database connection; a separate restricted runtime login is required before release, documented in the architecture and setup guide.

## Review path

1. Open `http://127.0.0.1:8017/login` using the configured local origin.
2. Try Google after enabling its provider, or email after setting the templates and redirects.
3. Enter a display name and lowercase booking username. Confirm your home timezone.
4. Check all three fields in Review, then save.
5. Reload `/app/profile`; confirm the fields persist. Edit the profile and save again.
6. Sign out and visit `/app/profile`; verify it returns to login.
7. Review the 390px mobile layout and report desired changes before Step 3.
