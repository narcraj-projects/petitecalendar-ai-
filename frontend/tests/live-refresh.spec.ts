import { test, expect, type Page } from "@playwright/test";

const id = "33333333-3333-4333-8333-333333333333";
const capability = "a".repeat(64);
const booking = {
  id,
  start_at: "2026-10-20T05:30:00Z",
  end_at: "2026-10-20T06:15:00Z",
  duration: 45,
  invitee_name: "Fixture invitee",
  invitee_email: "fixture@example.com",
  invitee_timezone: "Asia/Kolkata",
  status: "confirmed",
  revision: 1,
  calendar_status: "queued",
  email_status: "queued",
  meet_url: null as string | null,
  snapshot: {
    title: "Refresh call",
    location: "Online",
    host_name: "Fixture host",
    host_timezone: "Asia/Kolkata",
    cancellation_hours: 12,
    reschedule_hours: 12,
  },
};

test.beforeEach(async ({ page }) => {
  await page.clock.install({ time: new Date("2026-10-11T06:00:00Z") });
});

test("invitee delivery and cancellation updates arrive without reload", async ({
  page,
}) => {
  let saved = { ...booking };
  await page.route(`**/api/bookings/${id}`, (route) =>
    route.fulfill({ json: { booking: saved } }),
  );
  await page.goto(`/booking/${id}#${capability}`);
  await expect(
    page.getByText("Calendar delivery queued", { exact: true }),
  ).toBeVisible();
  saved = {
    ...saved,
    calendar_status: "synced",
    email_status: "accepted",
    meet_url: "https://meet.google.com/abc-defg-hij",
  };
  await page.clock.fastForward(16_000);
  await expect(
    page.getByRole("link", { name: "Join Google Meet" }),
  ).toBeVisible();
  saved = { ...saved, status: "cancelled", revision: 2 };
  await page.clock.fastForward(16_000);
  await expect(
    page.getByRole("heading", { name: "Booking cancelled." }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Join Google Meet" }),
  ).not.toBeVisible();
  expect(new URL(page.url()).hash).toBe(`#${capability}`);
});

test("other tabs notify a private booking page without exposing booking data", async ({
  page,
  context,
}) => {
  let saved = { ...booking };
  await page.route(`**/api/bookings/${id}`, (route) =>
    route.fulfill({ json: { booking: saved } }),
  );
  await page.goto(`/booking/${id}#${capability}`);
  await expect(
    page.getByRole("heading", { name: "You’re booked." }),
  ).toBeVisible();
  const other = await context.newPage();
  await other.goto("/");
  saved = { ...saved, status: "cancelled", revision: 2 };
  await other.evaluate(() =>
    localStorage.setItem("petcalendar:booking-refresh", String(Date.now())),
  );
  await expect(
    page.getByRole("heading", { name: "Booking cancelled." }),
  ).toBeVisible();
  await other.close();
});

async function authenticate(page: Page) {
  await page.route("**/api/auth/config", (r) =>
    r.fulfill({
      json: {
        configured: true,
        supabase_url: "https://refresh-test.supabase.co",
        publishable_key: "sb_publishable_test",
      },
    }),
  );
  await page.addInitScript(() => {
    const encode = (o: object) =>
      btoa(JSON.stringify(o))
        .replaceAll("=", "")
        .replaceAll("+", "-")
        .replaceAll("/", "_");
    const user = {
      id: "11111111-1111-4111-8111-111111111111",
      aud: "authenticated",
      role: "authenticated",
      app_metadata: {},
      user_metadata: {},
      created_at: new Date().toISOString(),
    };
    localStorage.setItem(
      "sb-refresh-test-auth-token",
      JSON.stringify({
        access_token: `${encode({ alg: "ES256" })}.${encode({ sub: user.id, aud: "authenticated", exp: Math.floor(Date.now() / 1000) + 3600 })}.test`,
        refresh_token: "synthetic",
        token_type: "bearer",
        expires_at: Math.floor(Date.now() / 1000) + 3600,
        user,
      }),
    );
  });
  await page.route("**/api/me", (r) =>
    r.fulfill({
      json: {
        profile: {
          display_name: "Fixture host",
          username: "fixture",
          timezone: "Asia/Kolkata",
        },
      },
    }),
  );
}

test("host receives another user's booking and updated Focus Guard counts", async ({
  page,
}) => {
  await authenticate(page);
  let rows: (typeof booking)[] = [];
  await page.route("**/api/me/bookings?**", (r) =>
    r.fulfill({
      json: {
        bookings: rows,
        week_bookings: rows,
        week_start: "2026-10-19",
        truncated: false,
        schedule: {
          timezone: "Asia/Kolkata",
          host_daily_cap: 4,
          weekly_cap_minutes: 600,
        },
      },
    }),
  );
  await page.goto("/app/bookings");
  await expect(
    page.getByRole("heading", { name: "No upcoming bookings this month." }),
  ).toBeVisible();
  rows = [{ ...booking }];
  await page.clock.fastForward(16_000);
  await expect(
    page.getByText("Fixture invitee", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("1 meeting · 45 / 600 minutes", { exact: true }),
  ).toBeVisible();
});

test("availability polling preserves contact, duration and open review, then removes a taken slot", async ({
  page,
}) => {
  await page.route("**/api/auth/config", (r) =>
    r.fulfill({ json: { configured: false } }),
  );
  await page.route("**/api/public/events/fixture/refresh", (r) =>
    r.fulfill({
      json: {
        title: "Refresh call",
        description: "A meeting",
        host: { name: "Fixture host", timezone: "Asia/Kolkata" },
        durations: [30, 45],
        default_duration: 45,
        location: "Online",
        notice_minutes: 720,
        buffer_before: 10,
        buffer_after: 15,
        cancellation_hours: 12,
        reschedule_hours: 12,
        availability_ready: true,
      },
    }),
  );
  let occupied = false;
  await page.route("**/api/public/events/fixture/refresh/slots?**", (r) =>
    r.fulfill({
      json: {
        slots: occupied
          ? []
          : [
              {
                start: booking.start_at,
                end: booking.end_at,
                date: "2026-10-20",
              },
            ],
        calendar_status: "connected",
      },
    }),
  );
  await page.goto("/fixture/refresh");
  await page.getByRole("button", { name: "30 min", exact: true }).click();
  await page.locator(".picker-slot").first().click();
  await page.getByRole("button", { name: "Review selected time" }).click();
  await page
    .getByRole("button", { name: "Yes, confirm zone & review" })
    .click();
  await page.getByLabel("Your name", { exact: true }).fill("Guest draft");
  await page
    .getByLabel("Email address", { exact: true })
    .fill("guest@example.com");
  await page.clock.fastForward(16_000);
  await expect(page.getByLabel("Your name", { exact: true })).toHaveValue(
    "Guest draft",
  );
  await expect(page.getByLabel("Email address", { exact: true })).toHaveValue(
    "guest@example.com",
  );
  await expect(
    page.getByRole("button", { name: "30 min", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  occupied = true;
  await page.clock.fastForward(16_000);
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await expect(page.locator(".picker-slot")).toHaveCount(0);
  await expect(
    page.getByText(
      "Your selected time is no longer available. Choose another time.",
    ),
  ).toBeVisible();
});
