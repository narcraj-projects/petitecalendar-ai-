import { test, expect } from "@playwright/test";

async function authenticate(page: import("@playwright/test").Page) {
  await page.route("**/api/auth/config", (r) =>
    r.fulfill({
      json: {
        configured: true,
        supabase_url: "https://lifecycle-test.supabase.co",
        publishable_key: "sb_publishable_test",
      },
    }),
  );
  await page.addInitScript(() => {
    const encode = (value: object) =>
      btoa(JSON.stringify(value))
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
      "sb-lifecycle-test-auth-token",
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
          timezone: "UTC",
        },
      },
    }),
  );
}

const uid = "44444444-4444-4444-8444-444444444444",
  capability = "a".repeat(64);
const original = {
  id: uid,
  start_at: "2030-01-20T10:00:00Z",
  end_at: "2030-01-20T10:30:00Z",
  duration: 30,
  invitee_name: "Fixture",
  invitee_email: "fixture@example.com",
  invitee_timezone: "Asia/Kolkata",
  status: "confirmed",
  revision: 1,
  calendar_status: "synced",
  email_status: "accepted",
  snapshot: {
    title: "Lifecycle call",
    location: "Online",
    host_name: "Fixture host",
    host_timezone: "UTC",
    cancellation_hours: 12,
    reschedule_hours: 12,
    reschedule_requires_approval: false,
    allow_alternatives: false,
  },
};
const replacement = "2030-01-21T10:00:00Z";

test("reschedule reviews both zones and retries the exact uncertain action", async ({
  page,
}, info) => {
  await page.clock.setFixedTime(new Date("2030-01-01T10:00:00Z"));
  await page.setViewportSize({ width: 390, height: 844 });
  let saved = original,
    calls: any[] = [];
  await page.route("**/api/bookings/**", async (r) => {
    expect(r.request().headers()["x-booking-capability"]).toBe(capability);
    expect(r.request().url()).not.toContain(capability);
    if (r.request().url().includes("/slots?"))
      return r.fulfill({
        json: {
          slots: [
            {
              start: replacement,
              end: "2030-01-21T10:30:00Z",
              date: "2030-01-21",
            },
          ],
          explanations: [],
          calendar_status: "connected",
        },
      });
    if (r.request().method() === "POST") {
      const command = r.request().postDataJSON();
      calls.push(command);
      if (calls.length === 1)
        return r.fulfill({
          status: 503,
          json: {
            error: {
              message:
                "The action could not be verified. Retry the same request.",
            },
          },
        });
      expect(command).toEqual(calls[0]);
      expect(command.action).toBe("reschedule");
      expect(command.candidates).toEqual([replacement]);
      saved = {
        ...original,
        start_at: replacement,
        end_at: "2030-01-21T10:30:00Z",
        revision: 2,
        calendar_status: "queued",
        email_status: "queued",
      };
    }
    return r.fulfill({ json: { booking: saved } });
  });
  await page.goto(`/booking/${uid}#${capability}`);
  await page
    .getByRole("button", { name: "Reschedule booking", exact: true })
    .click();
  await page.getByRole("button", { name: "2030-01-21", exact: true }).click();
  await page.locator(".picker-slot").click();
  const target = await page.locator(".picker-day.available").boundingBox();
  expect(target!.width).toBeGreaterThanOrEqual(44);
  expect(target!.height).toBeGreaterThanOrEqual(44);
  await page.getByRole("button", { name: "Review selected time" }).click();
  await expect(
    page.getByRole("heading", { name: "Check your current time zone." }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Yes, confirm zone & review" })
    .click();
  await page.getByRole("button", { name: "Use this time" }).click();
  await expect(page.locator(".management-review")).toContainText(
    /Asia\/(Kolkata|Calcutta)/,
  );
  expect(calls).toHaveLength(0);
  await page.screenshot({
    path: info.outputPath("reschedule-mobile.png"),
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page
    .getByRole("button", { name: "Confirm reschedule", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Retry same action" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Retry same action" }).click();
  await expect(
    page.getByText("Booking rescheduled. Your new time is reserved."),
  ).toBeVisible();
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.screenshot({
    path: info.outputPath("reschedule-desktop.png"),
    fullPage: true,
  });
  expect(calls).toHaveLength(2);
});

test("cancellation requires confirmation and persists after reload", async ({
  page,
}) => {
  await page.clock.setFixedTime(new Date("2030-01-01T10:00:00Z"));
  let cancelled = false,
    calls = 0;
  await page.route("**/api/bookings/**", (r) => {
    if (r.request().method() === "POST") {
      calls++;
      expect(r.request().postDataJSON().action).toBe("cancel");
      cancelled = true;
    }
    return r.fulfill({
      json: {
        booking: {
          ...original,
          status: cancelled ? "cancelled" : "confirmed",
          revision: cancelled ? 2 : 1,
          calendar_status: cancelled ? "queued" : "synced",
        },
      },
    });
  });
  await page.goto(`/booking/${uid}#${capability}`);
  await page
    .getByRole("button", { name: "Cancel booking", exact: true })
    .click();
  expect(calls).toBe(0);
  await page.getByRole("button", { name: "Go back", exact: true }).click();
  expect(calls).toBe(0);
  await page
    .getByRole("button", { name: "Cancel booking", exact: true })
    .click();
  await page.getByRole("button", { name: "Yes, cancel booking" }).click();
  await expect(
    page.getByRole("heading", { name: "Booking cancelled.", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Calendar removal pending")).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Booking cancelled.", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Reschedule booking", exact: true }),
  ).toBeDisabled();
  expect(calls).toBe(1);
});

test("pending approval preserves original and can be withdrawn", async ({
  page,
}) => {
  await page.clock.setFixedTime(new Date("2030-01-01T10:00:00Z"));
  let status = "pending";
  await page.route("**/api/bookings/**", (r) => {
    if (r.request().method() === "POST") {
      expect(r.request().postDataJSON().action).toBe("withdraw");
      expect(r.request().postDataJSON().request_id).toBe(uid);
      status = "withdrawn";
    }
    return r.fulfill({
      json: {
        booking: {
          ...original,
          change_request: {
            id: uid,
            booking_revision: 1,
            candidates: [replacement],
            timezone: "UTC",
            status,
          },
        },
      },
    });
  });
  await page.goto(`/booking/${uid}#${capability}`);
  await expect(
    page.getByRole("button", { name: "Reschedule booking", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByText("The original booking remains reserved.", { exact: false }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Withdraw request", exact: true })
    .click();
  await page.getByRole("button", { name: "Confirm withdrawal" }).click();
  await expect(
    page.getByText("Request closed. Your original time is unchanged."),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Reschedule booking", exact: true }),
  ).toBeEnabled();
});

test("host reviews approval and can view cancelled bookings", async ({
  page,
}, info) => {
  await page.clock.setFixedTime(new Date("2030-01-01T10:00:00Z"));
  await authenticate(page);
  await page.setViewportSize({ width: 390, height: 844 });
  let approved = false,
    cancelled = false,
    commands: any[] = [];
  await page.route("**/api/me/bookings**", (r) => {
    expect(r.request().headers()["authorization"]).toMatch(/^Bearer /);
    const row = {
      ...original,
      status: cancelled ? "cancelled" : "confirmed",
      start_at: approved ? replacement : original.start_at,
      revision: approved ? 2 : 1,
      change_request: {
        id: uid,
        booking_revision: 1,
        candidates: [replacement],
        timezone: "UTC",
        status: approved ? "approved" : "pending",
      },
    };
    if (r.request().method() === "POST") {
      const command = r.request().postDataJSON();
      commands.push(command);
      if (command.action === "approve") {
        expect(command.candidates).toEqual([replacement]);
        expect(command.request_id).toBe(uid);
        approved = true;
      }
      if (command.action === "cancel") cancelled = true;
      return r.fulfill({ json: { booking: row } });
    }
    return r.fulfill({
      json: {
        bookings: [row],
        week_bookings: [],
        week_start: "2029-12-31",
        truncated: false,
        schedule: null,
      },
    });
  });
  await page.goto("/app/bookings");
  await page.getByRole("button", { name: /^Review approval/ }).click();
  expect(commands).toHaveLength(0);
  await page.screenshot({
    path: info.outputPath("host-approval-mobile.png"),
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page
    .getByRole("button", { name: "Approve requested time", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Reschedule request · approved" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Cancel booking", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Yes, cancel booking", exact: true })
    .click();
  await page.getByLabel("Show", { exact: true }).selectOption("cancelled");
  await expect(page.locator(".booking-status")).toHaveText("Cancelled");
  expect(commands).toHaveLength(2);
});
