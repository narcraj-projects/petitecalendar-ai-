import { test, expect, type Page } from "@playwright/test";
async function authenticate(page: Page) {
  await page.route("**/api/auth/config", (r) =>
    r.fulfill({
      json: {
        configured: true,
        supabase_url: "https://availability-test.supabase.co",
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
      "sb-availability-test-auth-token",
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
          display_name: "Test Host",
          username: "test-host",
          timezone: "Asia/Kolkata",
        },
      },
    }),
  );
}
const capability = "a".repeat(64);
const uid = "33333333-3333-4333-8333-333333333333";
const booking = {
  id: uid,
  start_at: "2026-10-20T05:30:00Z",
  end_at: "2026-10-20T06:15:00Z",
  duration: 45,
  invitee_name: "Test Invitee",
  invitee_email: "fixture@example.com",
  invitee_timezone: "Europe/London",
  status: "confirmed",
  revision: 1,
  snapshot: {
    title: "Strategy call",
    location: "Online conversation",
    host_name: "Test Host",
    host_timezone: "Asia/Kolkata",
    cancellation_hours: 12,
    reschedule_hours: 12,
  },
  calendar_status: "not_connected",
  email_status: "not_enabled",
};
async function publicPage(page: Page) {
  await page.clock.setFixedTime(new Date("2026-10-11T06:00:00Z"));
  await page.route("**/api/public/events/test-host/strategy-call", (r) =>
    r.fulfill({
      json: {
        title: "Strategy call",
        description: "Discuss your next move.",
        host: { name: "Test Host", timezone: "Asia/Kolkata" },
        durations: [30, 45, 60],
        default_duration: 45,
        location: "Online conversation",
        notice_minutes: 720,
        buffer_before: 10,
        buffer_after: 15,
        cancellation_hours: 12,
        reschedule_hours: 12,
        availability_ready: true,
        schedule_timezone: "Asia/Kolkata",
      },
    }),
  );
  await page.route(
    "**/api/public/events/test-host/strategy-call/slots?**",
    (r) =>
      r.fulfill({
        json: {
          slots: [
            {
              start: booking.start_at,
              end: booking.end_at,
              date: "2026-10-20",
            },
          ],
        },
      }),
  );
  await page.goto("/test-host/strategy-call");
  await page
    .getByLabel("Your current time zone", { exact: true })
    .selectOption("Europe/London");
  await expect(page.locator(".picker-slot")).toHaveCount(1);
  await page.locator(".picker-slot").click();
  await page
    .getByRole("button", { name: "Review selected time", exact: true })
    .click();
  await expect(page.getByLabel("Your name", { exact: true })).not.toBeVisible();
  await page
    .getByRole("button", { name: "Yes, confirm zone & review", exact: true })
    .click();
  await page.getByLabel("Your name", { exact: true }).fill("Test Invitee");
  await page
    .getByLabel("Email address", { exact: true })
    .fill("fixture@example.com");
}

test("confirmed booking uses private fragment link and loads saved timezone details", async ({
  page,
}, info) => {
  await page.setViewportSize({ width: 390, height: 844 });
  let sent: any;
  await page.route(
    "**/api/public/events/test-host/strategy-call/bookings",
    (r) => {
      sent = r.request().postDataJSON();
      return r.fulfill({ status: 201, json: { booking } });
    },
  );
  await page.route("**/api/bookings/**", (r) => {
    expect(r.request().headers()["x-booking-capability"]).toBe(sent.capability);
    expect(r.request().url()).not.toContain(sent.capability);
    return r.fulfill({ json: { booking } });
  });
  await publicPage(page);
  await page.screenshot({
    path: info.outputPath("booking-form-mobile.png"),
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Confirm booking", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "You’re booked." }),
  ).toBeVisible();
  expect(page.url()).toContain(`#${sent.capability}`);
  expect(sent.timezone).toBe("Europe/London");
  expect(sent.capability).toMatch(/^[a-f0-9]{64}$/);
  await expect(page.getByText("YOU · Europe/London")).toBeVisible();
  await expect(
    page.getByText("No invitation has been sent yet.", { exact: false }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", {
      name: "Copy private booking link",
      exact: true,
    }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: info.outputPath("booking-confirmation-mobile.png"),
    fullPage: true,
  });
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "You’re booked." }),
  ).toBeVisible();
});

test("ambiguous response retries identical details and idempotency key", async ({
  page,
}) => {
  const attempts: any[] = [];
  await page.route(
    "**/api/public/events/test-host/strategy-call/bookings",
    (r) => {
      attempts.push(r.request().postDataJSON());
      return r.fulfill({
        status: 503,
        json: {
          error: {
            message: "Booking could not be verified. Retry the same request.",
          },
        },
      });
    },
  );
  await publicPage(page);
  await page
    .getByRole("button", { name: "Confirm booking", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText("Retry the same request");
  await expect(page.getByLabel("Your name", { exact: true })).toBeDisabled();
  await page
    .getByRole("button", { name: "Retry booking confirmation", exact: true })
    .click();
  await expect.poll(() => attempts.length).toBe(2);
  expect(attempts[1]).toEqual(attempts[0]);
  await expect(
    page.getByRole("heading", { name: "You’re booked." }),
  ).not.toBeVisible();
});

test("slot conflict clears selection and refreshes times without confirming", async ({
  page,
}) => {
  await page.route(
    "**/api/public/events/test-host/strategy-call/bookings",
    (r) =>
      r.fulfill({
        status: 409,
        json: {
          error: {
            code: "SLOT_UNAVAILABLE",
            message: "That time is no longer available.",
          },
        },
      }),
  );
  await publicPage(page);
  await page
    .getByRole("button", { name: "Confirm booking", exact: true })
    .click();
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await expect(
    page.getByText("That time is no longer available. Choose another time."),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Review selected time", exact: true }),
  ).not.toBeVisible();
  await expect(
    page.getByRole("heading", { name: "You’re booked." }),
  ).not.toBeVisible();
});

test("invalid private capability shows no booking details", async ({
  page,
}) => {
  await page.route("**/api/bookings/**", (r) =>
    r.fulfill({
      status: 404,
      json: { error: { message: "This private booking link is invalid." } },
    }),
  );
  await page.goto(`/booking/${uid}#${capability}`);
  await expect(page.getByRole("alert")).toContainText(
    "private booking link is invalid",
  );
  await expect(page.getByText("fixture@example.com")).not.toBeVisible();
});

test("dashboard filters month and past bookings, keeps weekly focus counts, supports mobile", async ({
  page,
}, info) => {
  await authenticate(page);
  await page.clock.setFixedTime(new Date("2026-10-11T06:00:00Z"));
  await page.setViewportSize({ width: 1440, height: 1000 });
  let fail = false;
  const queries: string[] = [];
  await page.route("**/api/me/bookings?**", (r) => {
    queries.push(r.request().url());
    if (fail)
      return r.fulfill({
        status: 503,
        json: {
          error: { message: "Bookings could not be loaded. Try again." },
        },
      });
    return r.fulfill({
      json: {
        bookings: [
          booking,
          {
            ...booking,
            id: "past",
            start_at: "2026-10-07T05:30:00Z",
            end_at: "2026-10-07T06:15:00Z",
          },
        ],
        week_bookings: [
          {
            ...booking,
            start_at: "2026-10-07T05:30:00Z",
            end_at: "2026-10-07T06:15:00Z",
          },
        ],
        week_start: "2026-10-05",
        truncated: false,
        schedule: {
          timezone: "Asia/Kolkata",
          host_daily_cap: 4,
          weekly_cap_minutes: 720,
        },
      },
    });
  });
  await page.goto("/app/bookings");
  await expect(
    page.getByRole("heading", { name: "Bookings", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".booking-row")).toHaveCount(1);
  await expect(page.getByText("1 meeting · 45 / 720 minutes")).toBeVisible();
  await page.screenshot({
    path: info.outputPath("bookings-dashboard-desktop.png"),
    fullPage: true,
  });
  await page.getByLabel("Show", { exact: true }).selectOption("past");
  await expect(page.locator(".booking-row")).toContainText("7 Oct 2026");
  await page.getByLabel("Booking month", { exact: true }).fill("2026-11");
  await expect.poll(() => queries.at(-1)).toContain("start=2026-11-01");
  await page.getByLabel("Booking month", { exact: true }).fill("2026-10");
  await expect.poll(() => queries.at(-1)).toContain("start=2026-10-01");
  await expect(page.locator(".booking-row")).toHaveCount(1);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: info.outputPath("bookings-dashboard-mobile.png"),
    fullPage: true,
  });
  fail = true;
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Bookings could not be loaded",
  );
  fail = false;
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(page.locator(".booking-row")).toHaveCount(1);
});
