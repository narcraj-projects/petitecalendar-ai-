import { test, expect } from "@playwright/test";
import { readFile } from "node:fs/promises";
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

test("private calendar download uses the capability header and preserves UID", async ({
  page,
}, info) => {
  await page.setViewportSize({ width: 390, height: 844 });
  let accepted = false;
  await page.route("**/api/bookings/**", (r) => {
    expect(r.request().headers()["x-booking-capability"]).toBe(capability);
    expect(r.request().url()).not.toContain(capability);
    if (r.request().url().endsWith("/calendar.ics"))
      return r.fulfill({
        contentType: "text/calendar",
        body: `BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:${uid}@petitecalendar\r\nDTSTART:20261020T053000Z\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n`,
      });
    return r.fulfill({
      json: {
        booking: {
          ...booking,
          email_status: accepted ? "accepted" : "queued",
          calendar_status: "synced",
          meet_url: "https://meet.google.com/abc-defg-hij",
        },
      },
    });
  });
  await page.goto(`/booking/${uid}#${capability}`);
  await expect(
    page.getByText("Email confirmation queued", { exact: true }),
  ).toBeVisible();
  accepted = true;
  await page
    .getByRole("button", { name: "Refresh email status", exact: true })
    .click();
  await expect(
    page.getByText("Email accepted by the email service.", { exact: false }),
  ).toBeVisible();
  const nextDownload = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Download calendar (.ics)", exact: true })
    .click();
  const download = await nextDownload;
  expect(download.suggestedFilename()).toBe(`booking-${uid}.ics`);
  const path = info.outputPath("booking.ics");
  await download.saveAs(path);
  expect(await readFile(path, "utf-8")).toContain(`UID:${uid}@petitecalendar`);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: info.outputPath("email-confirmation-mobile.png"),
    fullPage: true,
  });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.screenshot({
    path: info.outputPath("email-confirmation-desktop.png"),
    fullPage: true,
  });
});
test("failed download keeps the booking and allows retry", async ({ page }) => {
  let fail = true;
  await page.route("**/api/bookings/**", (r) => {
    if (r.request().url().endsWith("/calendar.ics"))
      return fail
        ? r.fulfill({
            status: 503,
            json: { error: { message: "Calendar unavailable" } },
          })
        : r.fulfill({
            contentType: "text/calendar",
            body: "BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n",
          });
    return r.fulfill({
      json: { booking: { ...booking, email_status: "failed" } },
    });
  });
  await page.goto(`/booking/${uid}#${capability}`);
  await expect(
    page.getByText("Email could not be sent.", { exact: false }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Download calendar (.ics)", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText(
    "Calendar download failed",
  );
  await expect(
    page.getByText("Your time is reserved.", { exact: false }),
  ).toBeVisible();
  fail = false;
  const download = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Download calendar (.ics)", exact: true })
    .click();
  await download;
  await expect(page.getByRole("alert")).not.toBeVisible();
});
test("uncertain email does not claim inbox delivery", async ({ page }) => {
  await page.route("**/api/bookings/**", (r) =>
    r.fulfill({ json: { booking: { ...booking, email_status: "uncertain" } } }),
  );
  await page.goto(`/booking/${uid}#${capability}`);
  await expect(
    page.getByText("Email status is uncertain.", { exact: false }),
  ).toBeVisible();
  await expect(
    page.getByText("Email accepted by the email service.", { exact: false }),
  ).not.toBeVisible();
});
