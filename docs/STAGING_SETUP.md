# PetCalendar AI staging setup

Step 10 private staging is deployed and ready for review. Railway CLI authentication and the workspace USD 10 compute cutoff, USD 7 alert and disabled Railway Agent were verified. The `petcalendar-ai-staging` project runs `web` and `worker` services from private GitHub. All eight migrations were applied to the separate staging Supabase database; separate restricted NOINHERIT web and worker logins were verified. See [the staging review](reviews/10-private-staging.md) for observed provider behavior and remaining production acceptance work. Private source on GitHub does not make a deployed booking page private.

## Package and configuration

The Docker image builds React with `npm ci` and installs the Python dependencies from `uv.lock`. It runs as a non-root user and explicitly copies only runtime code, migrations and compiled assets. The build context excludes credentials, screenshots and original reference documents. This follows the [uv Docker guide](https://docs.astral.sh/uv/guides/integration/docker/). The API and delivery worker use the same image as separate services, as supported by [Docker Compose](https://docs.docker.com/reference/compose-file/services/).

Create `.env.staging` from `.env.example`; it is ignored by Git. Use a separate staging Supabase project and synthetic users/bookings, not the development database. Set `APP_BASE_URL` to the final HTTPS staging origin. Set all three provider credentials only in the staging secret store. Generate and retain a separate `TOKEN_ENCRYPTION_KEY`; the API and worker must share that key. Do not rotate it casually because saved Google refresh tokens and pending delivery payloads depend on it. Use a TLS database connection and provision runtime login privileges for the existing role-based services before release. Migration credentials should be kept separately from runtime credentials. The staged web login is in `.env.staging`; `.env.staging.worker` contains the worker's distinct `DATABASE_URL` override and is required by Compose.

When the online origin is assigned, add its `/auth/callback` to the Supabase redirect allowlist and its `/api/integrations/google/callback` to the Google Calendar OAuth client redirect list. Supabase's own Google login callback remains separate. Update Google consent branding to PetCalendar AI in its console. Keep Resend's current restricted test sender until a sending domain is verified; staging invitees must use the permitted test recipient.

## Verify the container locally

Start Docker Desktop with Linux containers. The Compose file binds only `127.0.0.1:8027`, avoiding the existing local preview at port 8017. Run from the repository root:

```powershell
docker compose -f compose.staging.yaml build web
# Apply migrations once using an isolated migration environment with DATABASE_URL set.
# The named image is built above. Never migrate the development database by accident.
docker run --rm --env-file .env.staging.migrations petcalendar-ai:staging alembic upgrade head
docker compose -f compose.staging.yaml up -d
Invoke-RestMethod http://127.0.0.1:8027/api/health
docker compose -f compose.staging.yaml ps
```

`.env.staging.migrations` needs only the staging migration `DATABASE_URL`; it is ignored by Git. The web health check verifies process responsiveness, not database/provider readiness. The worker has no HTTP health check; inspect job progress and failed/uncertain statuses during acceptance. Container restarts use existing durable job leases. Keep one web process and one replica while assistant limits remain process-local. Do not run a second worker against the development database while its local worker is running.

For hosted deployment, configure one web service on container port 8017 and one continuously running worker using `python -m app.worker`. Run migrations once before starting delivery. Put the web service behind HTTPS and a private network or access gateway allowing only test users; a secret-looking hostname is not access control. Its OAuth callback must remain accessible to the signed-in browser. Hosting selection, price, ingress privacy and secrets configuration must be reviewed before creating services.

The application now provides an additional staging gate: set `STAGING_PRIVATE=true`, an HTTPS `APP_BASE_URL`, a `STAGING_ACCESS_PASSWORD` of at least 20 characters, and a valid `TOKEN_ENCRYPTION_KEY`. The browser prompts for username `staging` and that password; successful access issues an encrypted, Secure, HttpOnly, SameSite=Lax cookie lasting eight hours. Normal Supabase authentication remains required for host actions. All pages, assets and APIs are gated except `/api/health`; missing or invalid gate configuration fails closed. Password changes invalidate existing gate sessions. Keep the generated password in the ignored local staging file and share it only with authorized reviewers. Never enter it in chat or commit it.

Railway builds from the private GitHub repository. The local CLI configures and verifies services; do not upload the desktop workspace with `railway up`. Upload only staging secrets to the provider, with separate restricted web/worker database logins; keep the privileged migration login local.

## Acceptance and rollback

Use a synthetic host and the authorized test recipient. Verify sign-in/onboarding, event publication, current/travel-zone confirmation, fresh availability, booking conflict/idempotency, one Google event and Meet link, actual email receipt and ICS, cancellation/reschedule cleanup, and assistant draft/confirmation boundaries. Restart the worker with a pending job and verify one delivery. Record results before allowing public traffic. Provider failure must retain the booking and show delivery status rather than report success.

Back up staging and demonstrate restoration into a disposable project before production. Keep the previous image digest/commit for application rollback. Database rollback needs its own reviewed migration plan; do not blindly downgrade populated schemas. Stop delivery workers before restoring a database so restored jobs do not replay real provider effects.

Production is a separate decision. Shared request limits, least-privilege runtime credentials, verified email sending, backup restoration, monitoring and measured model cost/reliability remain release requirements.

## Preparation verification

Compose configuration validation passed against the blank environment example, and `uv lock --check --offline` passed. The [GitHub container check](https://github.com/narcraj-projects/petcalendar-ai/actions/runs/38142949745) passed for commit `3ac5e02`: locked Linux image build, worker imports, non-root web startup, health endpoint and SPA response. Docker Desktop was unavailable locally. This does not verify real staging authentication, database migrations, Google/Resend delivery, private ingress or backup restore; those require the hosted environment.

## Approved monthly spending boundary

On 11 October 2026 the user authorized a total maximum of USD 20/month for this app, including taxes and fees. Do not start online services until account controls are verified. The planned allocation is Railway USD 10, OpenAI USD 3, Supabase Free USD 0, Resend Free USD 0, and USD 7 left for taxes, fees and enforcement delay. This is not a claim that provider billing settings are already configured, nor an absolute guarantee against delayed metering. Additional paid staging resources, domains, plan upgrades, automatic recharge and cutoff increases require explicit user approval.

1. Create a Railway account with GitHub and select the Hobby plan (USD 5/month, including USD 5 resource usage). Grant repository access only to `petcalendar-ai`. Before creating services, open workspace Usage, then Set Usage Limits. Set the **Compute hard limit** to USD 10 and the email alert to USD 7. Confirm the displayed billing/subscription treatment and taxes fit the allowance. Keep Railway's separately billed Agent feature unused. These limits are workspace-wide: use a workspace dedicated to this app. [Railway cost controls](https://docs.railway.com/pricing/cost-control).
2. Use a dedicated OpenAI project and key for PetCalendar AI, not the existing other-project key. In Project settings ? Limits ? Spend ? Edit spend limit, enter USD 3/month and enable **Enforce a hard limit**. Save and verify enforcement is on, not merely an alert. Keep auto-recharge disabled; do not change limits for the user's other application. Enforcement can lag and spend can slightly exceed the number, so preserve the buffer. [Official OpenAI spend limits](https://developers.openai.com/api/docs/guides/spend-limits).
3. Supabase and Resend stay on Free. Do not enable Resend transactional overages, upgrade plans or buy domains. Verify sender-domain needs and free-tier quotas before public release. A free Supabase project has no automatic backups; production readiness remains a separate review.
4. The app now defaults to `AI_ENABLED=false`, even if an API key is present. Only set `AI_ENABLED=true` after the separate enforced OpenAI cutoff is verified. When OpenAI reports a spending limit, the application makes no automatic retry and shows manual scheduling fallback. This switch is not a cross-provider dollar ledger.

Railway's hard cutoff can stop web and worker delivery. Pending bookings/jobs remain in PostgreSQL; external delivery may wait until services are restored within an authorized budget. Do not raise the cutoff automatically. An OpenAI cutoff only pauses assistant calls; ordinary booking remains available while the web service is running. Existing hourly limits are not monthly billing controls. Monthly resets follow each provider's billing cycle, which need not align.

Verified: Railway account/CLI, workspace compute cutoff and alert, disabled Railway Agent, isolated staging database, migrations, restricted runtime logins and hosted private access. The user confirms a dedicated OpenAI project with an enforced USD 3 limit; key authentication and a live hosted assistant search passed. Tax treatment has not been independently verified; preserve the authorized reserve. Both hosted services are running.

The private staging access change passed Ruff and 196 backend tests. The seven opt-in PostgreSQL checks subsequently passed against isolated staging, including booking races, isolation and lifecycle correctness. Its [Linux container build and startup check](https://github.com/narcraj-projects/petcalendar-ai/actions/runs/38145354810) passed for `08e3951`.

The user explicitly authorized staging database, OAuth, Resend, encryption, access and OpenAI credentials to be stored in Railway service variables after an initial automatic-review rejection. This authorization was then accepted; web/worker secrets were uploaded with separate runtime database credentials. The user connected GitHub; direct service connections succeeded even though Railway's repository-list query still reported `Not Authorized`.

Both services deployed successfully from private GitHub `main`, commit `6ced1b1`. The environment is named `staging`, with web origin `https://web-staging-1ecf.up.railway.app` and port 8017; the worker runs `python -m app.worker` and has no public domain. HTTPS checks verified health availability, 401 on unauthenticated pages/APIs/docs, successful frontend access after the staging challenge, and Secure/HttpOnly/SameSite cookie flags. Access username is `staging`; retrieve the password locally from `.env.staging`, never from chat or GitHub.

The user subsequently confirmed that the identical local/staging key is now dedicated to PetCalendar AI, with the enforced USD 3 project limit. Non-billable key authentication and model availability passed; hosted web now has `AI_ENABLED=true` and returned eight live slot suggestions using the saved event duration. The worker remains AI-disabled. The user configured hosted Supabase/Google callbacks, reached onboarding, saved events/availability and connected Calendar. A current Google event/Meet link and removal of the earlier revision were verified. Resend accepted two emails, but inbox receipt is not independently verified. Production acceptance and backup restoration remain pending. The spending controls remain USD 10 Railway hard / USD 7 alert, USD 0 Railway Agent, with Supabase/Resend Free.
