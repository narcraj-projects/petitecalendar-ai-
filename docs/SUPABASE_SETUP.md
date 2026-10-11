# Development Supabase setup

Use a development project for Step 2. Keep credentials in the root `.env`; it is ignored by Git. Do not paste database passwords or Google client secrets into chat.

## Project connection

Create a project in [Supabase Dashboard](https://supabase.com/dashboard). In Connect, choose Framework → React → Vite to locate the project URL and publishable key. Keys are also available under Settings → API Keys. Use the publishable key, not a secret or service-role key. See [API keys](https://supabase.com/docs/guides/getting-started/api-keys).

Copy `.env.example` to `.env` if it does not exist. Fill these variables:

```dotenv
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_PUBLISHABLE_KEY=sb_publishable_your_key
DATABASE_URL=postgresql://postgres.your-project:your_encoded_password@your_session_pooler_host:5432/postgres
```

Copy the actual Session pooler URI from Connect → Direct rather than constructing it from this example. Replace the entire `[YOUR-PASSWORD]` placeholder, including brackets. URL-encode special characters in the password component. The session pooler works with the Python connection pool; do not select transaction pooling for this initial setup. See [database connections](https://supabase.com/docs/guides/database/connecting-to-postgres).

## Application redirects

In Authentication → URL Configuration, set:

- Site URL: `http://127.0.0.1:8017`
- Redirect URLs: `http://127.0.0.1:8017/auth/callback`

Use this exact origin consistently. `localhost` and `127.0.0.1` have separate browser storage; PKCE sign-in started on one must return to the same origin. See [redirect URLs](https://supabase.com/docs/guides/auth/redirect-urls).

## Email sign-in

Enable Email under Authentication → Sign In / Providers. Keep user signups enabled for initial onboarding. Under Authentication → Email Templates, use this link for the **Magic Link** and **Confirm Signup** templates:

```html
<a href="{{ .SiteURL }}/auth/callback?token_hash={{ .TokenHash }}&type=email">Sign in to PetiteCalendar-ai</a>
```

The application consumes the token hash through `verifyOtp`; Google callbacks use a PKCE code exchange. Callback parameters are immediately removed from browser history. Invalid or expired links show a retry path. See [passwordless email](https://supabase.com/docs/guides/auth/auth-email-passwordless).

For initial testing, use the email belonging to your Supabase organization. Supabase's default mail service restricts recipients and rate limits delivery; configure custom SMTP if you need other recipients. See [SMTP configuration](https://supabase.com/docs/guides/auth/auth-smtp). This authentication email is separate from booking notifications, which arrive in Step 8.

## Google sign-in

1. Create/select a project in [Google Cloud Console](https://console.cloud.google.com/).
2. Open Google Auth Platform. Complete Branding with PetiteCalendar-ai and the required support/contact email.
3. Set Audience to External. While testing, add your Google account under Test users.
4. Under Data Access, include only `openid`, `userinfo.email`, and `userinfo.profile` for sign-in.
5. Under Clients, create an OAuth client with application type Web application. Add the local app origin `http://127.0.0.1:8017` under Authorized JavaScript origins if requested.
6. In Supabase Authentication → Sign In / Providers → Google, copy the displayed callback URL. It is the hosted project URL ending in `/auth/v1/callback`.
7. Add that exact Supabase callback URL under Google's Authorized redirect URIs. It is different from the application's `/auth/callback` URL.
8. Copy the client ID and secret into the Supabase Google provider settings. Enable Google and save. Keep nonce verification enabled.

Google first returns to Supabase; Supabase then returns to the app. Calendar permissions are introduced separately at core Step 6. See [Supabase Google setup](https://supabase.com/docs/guides/auth/social-login/auth-google).

## Signing keys and migrations

The backend verifies asymmetric ES256/RS256 JWTs using the project's JWKS endpoint, expected issuer, authenticated audience, expiry, required claims, and role. Anonymous sessions are rejected. New Supabase projects normally have asymmetric signing keys; an older HS256-only project needs migration under Authentication → Signing Keys. See [JWT signing keys](https://supabase.com/docs/guides/auth/signing-keys).

Run from the repository root:

```powershell
uv sync
uv run alembic upgrade head
Set-Location frontend
npm.cmd ci
npm.cmd run build
Set-Location ..
uv run uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8017 --no-access-log
```

Access logging is disabled because callbacks contain authentication parameters. Do not add proxy logging of full callback URLs. Migrations create a private `app_private.host_profiles` table referencing `auth.users`, a restricted NOLOGIN API role, and row-level isolation. The private schema should remain outside Supabase's exposed Data API schemas. Each profile transaction switches to the API role and sets the verified user ID locally. The development connection uses the migration account; use a separate least-privileged runtime login before deployment.

Open `http://127.0.0.1:8017/login`. Sign in, complete the four onboarding steps, confirm and save, then reload `/app/profile` to check persistence. Editing a profile uses the same validation and review flow. A username is reserved here; no published booking page is created until event management is implemented.

Opt-in PostgreSQL checks create temporary fixtures within one rolled-back transaction:

```powershell
$env:RUN_DATABASE_TESTS = '1'
uv run pytest backend/tests/test_profile_database.py -q
Remove-Item Env:RUN_DATABASE_TESTS
```
