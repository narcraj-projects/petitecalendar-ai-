# PetCalendar AI staging setup

This is deployment preparation. No hosting account, online environment or paid service has been created. The user has no hosting account yet. Private source on GitHub does not make a deployed booking page private.

## Package and configuration

The Docker image builds React with `npm ci` and installs the Python dependencies from `uv.lock`. It runs as a non-root user and explicitly copies only runtime code, migrations and compiled assets. The build context excludes credentials, screenshots and original reference documents. This follows the [uv Docker guide](https://docs.astral.sh/uv/guides/integration/docker/). The API and delivery worker use the same image as separate services, as supported by [Docker Compose](https://docs.docker.com/reference/compose-file/services/).

Create `.env.staging` from `.env.example`; it is ignored by Git. Use a separate staging Supabase project and synthetic users/bookings, not the development database. Set `APP_BASE_URL` to the final HTTPS staging origin. Set all three provider credentials only in the staging secret store. Generate and retain a separate `TOKEN_ENCRYPTION_KEY`; the API and worker must share that key. Do not rotate it casually because saved Google refresh tokens and pending delivery payloads depend on it. Use a TLS database connection and provision runtime login privileges for the existing role-based services before release. Migration credentials should be kept separately from runtime credentials.

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

## Acceptance and rollback

Use a synthetic host and the authorized test recipient. Verify sign-in/onboarding, event publication, current/travel-zone confirmation, fresh availability, booking conflict/idempotency, one Google event and Meet link, actual email receipt and ICS, cancellation/reschedule cleanup, and assistant draft/confirmation boundaries. Restart the worker with a pending job and verify one delivery. Record results before allowing public traffic. Provider failure must retain the booking and show delivery status rather than report success.

Back up staging and demonstrate restoration into a disposable project before production. Keep the previous image digest/commit for application rollback. Database rollback needs its own reviewed migration plan; do not blindly downgrade populated schemas. Stop delivery workers before restoring a database so restored jobs do not replay real provider effects.

Production is a separate decision. Shared request limits, least-privilege runtime credentials, verified email sending, backup restoration, monitoring and measured model cost/reliability remain release requirements.

## Preparation verification

Compose configuration validation passed against the blank environment example, and `uv lock --check --offline` passed. The [GitHub container check](https://github.com/narcraj-projects/petcalendar-ai/actions/runs/38142949745) passed for commit `3ac5e02`: locked Linux image build, worker imports, non-root web startup, health endpoint and SPA response. Docker Desktop was unavailable locally. This does not verify real staging authentication, database migrations, Google/Resend delivery, private ingress or backup restore; those require the hosted environment.
