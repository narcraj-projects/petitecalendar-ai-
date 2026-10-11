import { test, expect, type Page } from "@playwright/test";
import type { Schedule } from "../src/AvailabilitySettings";
const scheduleFixture: Schedule = {
  revision: 2,
  timezone: "UTC",
  enabled: true,
  weekly: [],
  overrides: [],
  focus: [],
  increment_minutes: 15,
  host_daily_cap: 4,
  weekly_cap_minutes: 720,
  prefer_cluster: false,
};
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
test("save hours, closed override, focus and caps, then reload on desktop and mobile", async ({
  page,
}, testInfo) => {
  await authenticate(page);
  await page.setViewportSize({ width: 1440, height: 1000 });
  let saved: Schedule | null = null;
  await page.route("**/api/me/availability", (r) => {
    if (r.request().method() === "GET")
      return r.fulfill({ json: { schedule: saved } });
    const body = r.request().postDataJSON();
    saved = { ...body, revision: body.revision + 1 };
    return r.fulfill({ json: { schedule: saved } });
  });
  await page.goto("/app/availability");
  await expect(
    page.getByText("These suggested hours are not active until you save."),
  ).toBeVisible();
  await page.getByLabel("Monday window 1 start", { exact: true }).fill("10:00");
  await page
    .getByRole("button", { name: "Add date override", exact: true })
    .click();
  await page.getByLabel("Override 1 date", { exact: true }).fill("2026-10-13");
  await page
    .getByRole("button", { name: "Add focus block", exact: true })
    .click();
  await page.getByLabel("Focus block 1 start", { exact: true }).fill("12:00");
  await page.getByLabel("Focus block 1 end", { exact: true }).fill("13:00");
  await page.getByLabel("Max meetings per day", { exact: true }).fill("3");
  await page
    .getByLabel("Prefer times near existing meetings", { exact: true })
    .check();
  await page
    .getByRole("button", { name: "Save availability", exact: true })
    .click();
  await expect(page.getByRole("status")).toHaveText(
    "Availability and Focus Guard saved.",
  );
  expect(saved!.weekly[0].start).toBe("10:00");
  expect(saved!.overrides[0].windows).toEqual([]);
  expect(saved!.focus[0].start).toBe("12:00");
  expect(saved!.host_daily_cap).toBe(3);
  await page.screenshot({
    path: testInfo.outputPath("availability-desktop.png"),
    fullPage: true,
  });
  await page.reload();
  await expect(
    page.getByLabel("Monday window 1 start", { exact: true }),
  ).toHaveValue("10:00");
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: testInfo.outputPath("availability-mobile.png"),
    fullPage: true,
  });
  await page
    .getByLabel("Show available times on published event pages")
    .uncheck();
  await page
    .getByRole("button", { name: "Save availability", exact: true })
    .click();
  await expect(page.getByRole("status")).toHaveText("Availability paused.");
  expect(saved!.enabled).toBe(false);
});

test("published times clear stale selection and require current travel zone confirmation", async ({
  page,
}, testInfo) => {
  await page.clock.setFixedTime(new Date("2026-10-11T06:00:00Z"));
  await page.setViewportSize({ width: 390, height: 844 });
  await page.route("**/api/public/events/test-host/strategy-call", (r) =>
    r.fulfill({
      json: {
        title: "Strategy call",
        description: "Discuss your next move.",
        host: { name: "Test Host", timezone: "Asia/Kolkata" },
        schedule_timezone: "Asia/Kolkata",
        durations: [30, 45, 60],
        default_duration: 45,
        location: "Online conversation",
        notice_minutes: 720,
        buffer_before: 10,
        buffer_after: 15,
        cancellation_hours: 12,
        reschedule_hours: 12,
        availability_ready: true,
      },
    }),
  );
  let fail = false;
  const queries: URLSearchParams[] = [];
  await page.route(
    "**/api/public/events/test-host/strategy-call/slots?**",
    (r) => {
      const q = new URL(r.request().url()).searchParams;
      queries.push(q);
      if (fail)
        return r.fulfill({
          status: 503,
          json: { error: { message: "Times unavailable. Try again." } },
        });
      return r.fulfill({
        json: {
          slots: [
            {
              start: "2026-10-20T05:30:00+00:00",
              end: "2026-10-20T06:15:00+00:00",
              date: "2026-10-20",
            },
          ],
          explanations: ["focus_blocks", "minimum_notice"],
        },
      });
    },
  );
  await page.goto("/test-host/strategy-call");
  await expect(page.locator(".picker-slot")).toHaveCount(1);
  await page.locator(".picker-slot").click();
  await page
    .getByRole("button", { name: "Review selected time", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Check your current time zone." }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Change my time zone", exact: true })
    .click();
  await page
    .getByLabel("Your current time zone", { exact: true })
    .selectOption("Europe/London");
  await expect(
    page.getByRole("button", { name: "Review selected time", exact: true }),
  ).not.toBeVisible();
  await expect(page.locator(".picker-slot")).toHaveCount(1);
  expect(queries.at(-1)!.get("timezone")).toBe("Europe/London");
  await page.locator(".picker-slot").click();
  await page
    .getByRole("button", { name: "Review selected time", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Yes, confirm zone & review", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toContainText("HOST · Asia/Kolkata");
  await expect(page.getByRole("dialog")).toContainText(
    "Your time has not been reserved.",
  );
  await page.screenshot({
    path: testInfo.outputPath("availability-public-review-mobile.png"),
    fullPage: true,
  });
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await page.getByRole("button", { name: "60 min", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Review selected time", exact: true }),
  ).not.toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  fail = true;
  await page.getByRole("button", { name: "Next month", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Times unavailable");
  fail = false;
  await page.getByRole("button", { name: "Retry times", exact: true }).click();
  await expect(page.locator(".picker-calendar")).toBeVisible();
});

test("stale schedule cannot be silently saved over newer data", async ({
  page,
}) => {
  await authenticate(page);
  await page.route("**/api/me/availability", (r) =>
    r.request().method() === "GET"
      ? r.fulfill({
          json: { schedule: scheduleFixture },
        })
      : r.fulfill({
          status: 409,
          json: {
            error: { message: "Availability changed. Reload before saving." },
          },
        }),
  );
  await page.goto("/app/availability");
  await page
    .getByRole("button", { name: "Save availability", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText("Reload before saving");
  await expect(page.getByRole("status")).not.toBeVisible();
});
