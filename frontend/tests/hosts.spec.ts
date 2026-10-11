import { test, expect, type Page } from "@playwright/test";

test("Google sign-in uses PKCE and the local app callback", async ({
  page,
}) => {
  await mockConfig(page);
  await page.route(
    "https://host-test.supabase.co/auth/v1/authorize**",
    (route) =>
      route.fulfill({
        contentType: "text/html",
        body: "<p>OAuth provider test double</p>",
      }),
  );
  await page.goto("/login");
  await page.getByRole("button", { name: "Continue with Google" }).click();
  await expect(page).toHaveURL(/host-test.supabase.co\/auth\/v1\/authorize/);
  const url = new URL(page.url());
  expect(url.searchParams.get("provider")).toBe("google");
  expect(url.searchParams.get("redirect_to")).toBe(
    "http://127.0.0.1:8017/auth/callback",
  );
  expect(url.searchParams.get("code_challenge")).toBeTruthy();
});

test("OAuth callback exchanges a code once and opens onboarding", async ({
  page,
}) => {
  await mockConfig(page);
  await page.addInitScript(() =>
    localStorage.setItem(
      "sb-host-test-auth-token-code-verifier",
      JSON.stringify("test-verifier"),
    ),
  );
  let calls = 0;
  await page.route("https://host-test.supabase.co/auth/v1/token**", (route) => {
    calls++;
    expect(route.request().postDataJSON()).toMatchObject({
      auth_code: "synthetic-code",
      code_verifier: "test-verifier",
    });
    const encode = (obj: object) =>
      Buffer.from(JSON.stringify(obj)).toString("base64url");
    const access_token = `${encode({ alg: "ES256" })}.${encode({ sub: user, aud: "authenticated", exp: Math.floor(Date.now() / 1000) + 3600 })}.test`;
    return route.fulfill({
      json: {
        access_token,
        refresh_token: "test-refresh",
        token_type: "bearer",
        expires_in: 3600,
        user: {
          id: user,
          aud: "authenticated",
          role: "authenticated",
          email: "test@example.test",
          app_metadata: {},
          user_metadata: {},
          created_at: new Date().toISOString(),
        },
      },
    });
  });
  await page.route("**/api/me", (route) =>
    route.fulfill({ json: { user_id: user, profile: null } }),
  );
  await page.goto("/auth/callback?code=synthetic-code");
  await expect(page.getByLabel("Display name")).toBeVisible();
  await expect(page).toHaveURL(/\/onboarding$/);
  expect(calls).toBe(1);
});

const user = "11111111-1111-4111-8111-111111111111";
async function mockConfig(page: Page) {
  await page.route("**/api/auth/config", (route) =>
    route.fulfill({
      json: {
        configured: true,
        supabase_url: "https://host-test.supabase.co",
        publishable_key: "sb_publishable_test",
      },
    }),
  );
}
async function authenticated(page: Page) {
  await mockConfig(page);
  await page.addInitScript(
    ({ user }) => {
      const encode = (obj: object) =>
        btoa(JSON.stringify(obj))
          .replaceAll("=", "")
          .replaceAll("+", "-")
          .replaceAll("/", "_");
      const access_token = `${encode({ alg: "ES256", typ: "JWT" })}.${encode({ sub: user, aud: "authenticated", exp: Math.floor(Date.now() / 1000) + 3600 })}.test`;
      localStorage.setItem(
        "sb-host-test-auth-token",
        JSON.stringify({
          access_token,
          refresh_token: "test-refresh",
          token_type: "bearer",
          expires_at: Math.floor(Date.now() / 1000) + 3600,
          expires_in: 3600,
          user: {
            id: user,
            aud: "authenticated",
            role: "authenticated",
            email: "test@example.test",
            app_metadata: {},
            user_metadata: {},
            created_at: new Date().toISOString(),
          },
        }),
      );
    },
    { user },
  );
  await page.route("https://host-test.supabase.co/**", (route) =>
    route.fulfill({ json: {} }),
  );
}

test("email sign-in uses Supabase and displays inbox instruction", async ({
  page,
}, testInfo) => {
  await mockConfig(page);
  let requested: Record<string, unknown> = {};
  await page.route("https://host-test.supabase.co/auth/v1/otp**", (route) => {
    requested = route.request().postDataJSON();
    return route.fulfill({ json: {} });
  });
  await page.goto("/login");
  await page.getByLabel("Email address").fill("test@example.test");
  await page.getByRole("button", { name: "Email me a sign-in link" }).click();
  await expect(page.getByRole("status")).toContainText("Check your inbox");
  expect(requested.email).toBe("test@example.test");
  expect(requested.code_challenge).toBeTruthy();
  await page.screenshot({
    path: testInfo.outputPath("login-desktop.png"),
    fullPage: true,
  });
});

test("mobile onboarding reviews timezone, handles collision and persists on reload", async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await authenticated(page);
  let profile: Record<string, string> | null = null;
  let collisions = 1;
  await page.route("**/api/me", (route) =>
    route.fulfill({ json: { user_id: user, profile } }),
  );
  await page.route("**/api/me/profile", (route) => {
    if (collisions-- > 0)
      return route.fulfill({
        status: 409,
        json: {
          error: {
            code: "USERNAME_TAKEN",
            message: "That booking username is already taken.",
          },
        },
      });
    profile = route.request().postDataJSON();
    return route.fulfill({ json: { user_id: user, profile } });
  });
  await page.goto("/onboarding");
  await page.getByLabel("Display name").fill("Test Host");
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await page.getByLabel("Booking username").fill("test-host");
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await page.getByLabel("Home timezone").selectOption("Asia/Tokyo");
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(page.locator(".host-summary")).toContainText("Asia/Tokyo");
  await page.screenshot({
    path: testInfo.outputPath("onboarding-mobile.png"),
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.getByRole("button", { name: "Confirm & save profile" }).click();
  await expect(page.getByRole("alert")).toContainText("already taken");
  await page.getByRole("button", { name: "Back", exact: true }).click();
  await page.getByRole("button", { name: "Back", exact: true }).click();
  await page.getByLabel("Booking username").fill("test-host-new");
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await page.getByRole("button", { name: "Confirm & save profile" }).click();
  await expect(
    page.getByRole("heading", { name: "You’re ready, Test Host." }),
  ).toBeVisible();
  expect(profile).toEqual({
    display_name: "Test Host",
    username: "test-host-new",
    timezone: "Asia/Tokyo",
  });
  await page.reload();
  await expect(page.locator(".host-summary")).toContainText("test-host-new");
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
});

test("protected page redirects and rejected session signs out", async ({
  page,
}) => {
  await mockConfig(page);
  await page.goto("/app/profile");
  await expect(page).toHaveURL(/\/login$/);
  await authenticated(page);
  await page.route("**/api/me", (route) =>
    route.fulfill({
      status: 401,
      json: { error: { message: "Session expired." } },
    }),
  );
  await page.goto("/app/profile");
  await expect(page).toHaveURL(/\/login$/);
});

test("callback token hash is consumed once and removed from URL", async ({
  page,
}) => {
  await mockConfig(page);
  let calls = 0;
  await page.route("https://host-test.supabase.co/auth/v1/verify", (route) => {
    calls++;
    expect(route.request().postDataJSON()).toMatchObject({
      token_hash: "synthetic-hash",
      type: "email",
    });
    return route.fulfill({
      status: 403,
      json: { error_code: "otp_expired", msg: "Expired" },
    });
  });
  await page.goto("/auth/callback?token_hash=synthetic-hash&type=email");
  await expect(page.getByRole("alert")).toContainText("expired");
  await expect(page).toHaveURL(/\/auth\/callback$/);
  expect(calls).toBe(1);
});

test("profile storage failure supports retry without invented success", async ({
  page,
}) => {
  await authenticated(page);
  let failed = true;
  await page.route("**/api/me", (route) =>
    failed
      ? route.fulfill({
          status: 503,
          json: {
            error: { message: "Your profile could not be loaded. Try again." },
          },
        })
      : route.fulfill({
          json: {
            user_id: user,
            profile: {
              display_name: "Test Host",
              username: "test-host",
              timezone: "UTC",
            },
          },
        }),
  );
  await page.goto("/app/profile");
  await expect(page.getByRole("alert")).toContainText("could not be loaded");
  failed = false;
  await page.getByRole("button", { name: "Retry", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "You’re ready, Test Host." }),
  ).toBeVisible();
});
