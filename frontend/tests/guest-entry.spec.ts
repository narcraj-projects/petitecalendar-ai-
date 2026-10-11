import { test, expect } from "@playwright/test";

test("guest opens a shared booking link and reaches contact fields without signing in", async ({
  page,
}) => {
  await page.route("**/api/auth/config", (route) =>
    route.fulfill({ json: { configured: false } }),
  );
  await page.route("**/api/public/events/fixture/review", (route) =>
    route.fulfill({
      json: {
        title: "Project review",
        description: "Review our project",
        host: { name: "Fixture host", timezone: "Asia/Kolkata" },
        durations: [30],
        default_duration: 30,
        location: "Online",
        notice_minutes: 0,
        buffer_before: 0,
        buffer_after: 0,
        cancellation_hours: 12,
        reschedule_hours: 12,
        availability_ready: true,
      },
    }),
  );
  const date = new Date(Date.now() + 3 * 86400000);
  await page.route("**/api/public/events/fixture/review/slots?**", (route) =>
    route.fulfill({
      json: {
        slots: [
          {
            start: date.toISOString(),
            end: new Date(date.getTime() + 30 * 60000).toISOString(),
            date: new Intl.DateTimeFormat("en-CA", {
              timeZone: "Asia/Kolkata",
            }).format(date),
          },
        ],
        calendar_status: "connected",
      },
    }),
  );
  await page.goto("/");
  await page
    .getByLabel("Booking link from your host")
    .fill(new URL("/fixture/review", page.url()).href);
  await page.getByRole("button", { name: "Open booking page" }).click();
  await expect(
    page.getByRole("heading", { name: "Project review", exact: true }),
  ).toBeVisible();
  await page.locator(".picker-slot").first().click();
  await page.getByRole("button", { name: "Review selected time" }).click();
  await page
    .getByRole("button", { name: "Yes, confirm zone & review" })
    .click();
  await expect(page.getByLabel("Your name", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Email address", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Confirm booking", exact: true }),
  ).toBeVisible();
});

test("guest entry rejects an unrelated website and fits mobile", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page
    .getByLabel("Booking link from your host")
    .fill("https://example.com/fixture/review");
  await page.getByRole("button", { name: "Open booking page" }).click();
  await expect(page.getByRole("alert")).toContainText(
    "booking link shared by your host",
  );
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
