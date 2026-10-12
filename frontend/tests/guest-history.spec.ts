import { test, expect, type Page } from "@playwright/test";

const user = "11111111-1111-4111-8111-111111111111";
function session() {
  const encode = (value: object) =>
    Buffer.from(JSON.stringify(value)).toString("base64url");
  return {
    access_token: `${encode({ alg: "ES256" })}.${encode({ sub: user, aud: "authenticated", exp: Math.floor(Date.now() / 1000) + 3600 })}.test`,
    refresh_token: "synthetic-refresh",
    token_type: "bearer",
    expires_in: 3600,
    expires_at: Math.floor(Date.now() / 1000) + 3600,
    user: {
      id: user,
      aud: "authenticated",
      role: "authenticated",
      email: "guest@example.test",
      app_metadata: {},
      user_metadata: {},
      created_at: new Date().toISOString(),
    },
  };
}
async function config(page: Page, signedIn = false) {
  await page.route("**/api/auth/config", (route) =>
    route.fulfill({
      json: {
        configured: true,
        supabase_url: "https://guest-test.supabase.co",
        publishable_key: "sb_publishable_test",
      },
    }),
  );
  await page.route("https://guest-test.supabase.co/**", (route) =>
    route.fulfill({ json: {} }),
  );
  if (signedIn)
    await page.addInitScript(
      (value) =>
        localStorage.setItem("sb-guest-test-auth-token", JSON.stringify(value)),
      session(),
    );
}
const booking = {
  id: user,
  title: "Project review",
  host_name: "Review host",
  host_timezone: "Europe/London",
  start_at: "2026-11-10T10:00:00Z",
  end_at: "2026-11-10T10:30:00Z",
  duration: 30,
  invitee_timezone: "Asia/Kolkata",
  status: "confirmed",
  location: "Online conversation",
  meet_url: "https://meet.google.com/test-review-link",
};

test("anonymous guests verify email before any history request", async ({
  page,
}, info) => {
  await config(page);
  let historyCalls = 0;
  await page.route("**/api/guest/bookings**", (route) => {
    historyCalls++;
    return route.fulfill({ json: {} });
  });
  let redirect = "";
  await page.route("https://guest-test.supabase.co/auth/v1/otp**", (route) => {
    expect(route.request().postDataJSON()).toMatchObject({
      email: "guest@example.test",
      create_user: true,
    });
    redirect =
      new URL(route.request().url()).searchParams.get("redirect_to") || "";
    return route.fulfill({ json: {} });
  });
  await page.goto("/guest/bookings");
  await page.getByLabel("Your booking email").fill("guest@example.test");
  await page.getByRole("button", { name: "Send sign-in link" }).click();
  await expect(page.getByRole("status")).toContainText("Check your inbox");
  expect(redirect).toBe(new URL("/auth/callback?next=guest", page.url()).href);
  expect(historyCalls).toBe(0);
  await page.screenshot({
    path: info.outputPath("guest-verify-desktop.png"),
    fullPage: true,
  });
});

test("magic-link callback opens guest history without host onboarding", async ({
  page,
}) => {
  await config(page);
  let verified = 0;
  await page.route("https://guest-test.supabase.co/auth/v1/verify", (route) => {
    verified++;
    expect(route.request().postDataJSON()).toMatchObject({
      token_hash: "synthetic-hash",
      type: "email",
    });
    return route.fulfill({ json: session() });
  });
  let hostCalls = 0;
  await page.route("**/api/me", (route) => {
    hostCalls++;
    return route.fulfill({ json: {} });
  });
  await page.route("**/api/guest/bookings**", (route) =>
    route.fulfill({
      json: { bookings: [booking], has_more: false, next_offset: null },
    }),
  );
  await page.goto("/auth/callback?token_hash=synthetic-hash&next=guest");
  await expect(page).toHaveURL(/\/guest\/bookings$/);
  await expect(
    page.getByRole("heading", { name: "Project review" }),
  ).toBeVisible();
  expect(verified).toBe(1);
  expect(hostCalls).toBe(0);
});

test("guest history filters, pagination, refresh and sign-out", async ({
  page,
}, info) => {
  await config(page, true);
  let calls = 0;
  await page.route("**/api/guest/bookings**", (route) => {
    calls++;
    expect(route.request().headers().authorization).toContain("Bearer ");
    const query = new URL(route.request().url()).searchParams;
    expect(query.has("email")).toBe(false);
    const kind = query.get("kind");
    const second = query.get("offset") === "25";
    const rows =
      kind === "past"
        ? []
        : [
            {
              ...booking,
              title: second ? "Second page" : "Project review",
              status: kind === "cancelled" ? "cancelled" : "confirmed",
            },
          ];
    return route.fulfill({
      json: {
        bookings: rows,
        has_more: kind === "upcoming" && !second,
        next_offset: kind === "upcoming" && !second ? 25 : null,
      },
    });
  });
  await page.goto("/guest/bookings");
  await expect(
    page.getByRole("link", { name: "Join Google Meet" }),
  ).toBeVisible();
  await expect(page.getByText("Asia/Kolkata", { exact: true })).toBeVisible();
  await page.screenshot({
    path: info.outputPath("guest-history-desktop.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "More bookings" }).click();
  await expect(
    page.getByRole("heading", { name: "Second page" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Previous bookings" }).click();
  await expect(
    page.getByRole("heading", { name: "Project review" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Past", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "No past bookings" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Cancelled", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Project review" }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Join Google Meet" }),
  ).toHaveCount(0);
  const before = calls;
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect.poll(() => calls).toBeGreaterThan(before);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: info.outputPath("guest-history-mobile.png"),
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByLabel("Your booking email")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Project review" }),
  ).toHaveCount(0);
});

test("history provider failure can be retried without exposing results", async ({
  page,
}) => {
  await config(page, true);
  let failed = true;
  await page.route("**/api/guest/bookings**", (route) =>
    route.fulfill(
      failed
        ? {
            status: 503,
            json: {
              error: {
                code: "AUTH_UNAVAILABLE",
                message: "Email verification is temporarily unavailable.",
              },
            },
          }
        : { json: { bookings: [], has_more: false, next_offset: null } },
    ),
  );
  await page.goto("/guest/bookings");
  await expect(page.getByRole("alert")).toContainText(
    "Email verification is temporarily unavailable",
  );
  failed = false;
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "No upcoming bookings" }),
  ).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
});
