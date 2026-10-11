import { test, expect } from "@playwright/test";

async function waitForSlots(page: import("@playwright/test").Page) {
  await expect(page.getByText(/\d+ times available ·/)).toBeVisible();
}

test("desktop duration, timezone, month and selection flow", async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/ananya/career-strategy");
  await waitForSlots(page);
  await expect(page.getByText("Demo schedule", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "60 min", exact: true }).click();
  await expect(page.getByText(/times available · 60 min/)).toBeVisible();
  await page.getByLabel("YOUR TIME ZONE").selectOption("Europe/London");
  await waitForSlots(page);
  await expect(
    page.getByText("All times are shown in London.", { exact: false }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Next month" }).click();
  await waitForSlots(page);
  await page.getByRole("button", { name: "Previous month" }).click();
  await waitForSlots(page);
  await page.locator(".slot").first().click();
  await expect(
    page.getByRole("button", { name: "Review", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("desktop.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "Review", exact: true }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Check your current time zone." }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "A good time to talk." }),
  ).not.toBeVisible();
  await page
    .getByRole("button", { name: "Yes, confirm zone & review" })
    .click();
  await expect(page.getByText("YOU · LONDON")).toBeVisible();
  await expect(
    page.getByText("Your time has not been reserved.", { exact: false }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).not.toBeVisible();
});

test("390px mobile calendar and slot review without overflow", async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/ananya/career-strategy");
  await waitForSlots(page);
  await expect(page.locator(".mobile-day-strip")).toBeVisible();
  await page.getByRole("button", { name: "View month calendar" }).click();
  await expect(page.locator(".month-calendar")).toBeVisible();
  const target = await page
    .locator(".calendar-days button.available")
    .first()
    .boundingBox();
  expect(target!.width).toBeGreaterThanOrEqual(44);
  expect(target!.height).toBeGreaterThanOrEqual(44);
  await page.locator(".calendar-days button.available").last().click();
  await expect(page.locator(".month-calendar")).not.toBeVisible();
  await page.getByRole("button", { name: "30 min", exact: true }).click();
  await expect(page.getByText(/times available · 30 min/)).toBeVisible();
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth))
    .toBeLessThanOrEqual(390);
  await page.screenshot({
    path: testInfo.outputPath("mobile.png"),
    fullPage: true,
  });
  await page.locator(".slot").first().click();
  await page.getByRole("button", { name: "Review", exact: true }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page
    .getByRole("button", { name: "Yes, confirm zone & review" })
    .click();
  await page.getByRole("button", { name: "Back to available times" }).click();
  await expect(page.getByRole("dialog")).not.toBeVisible();
});

test("slot fetch failure offers a working retry", async ({ page }) => {
  let fail = true;
  await page.route("**/slots?**", (route) =>
    fail ? route.abort() : route.continue(),
  );
  await page.goto("/ananya/career-strategy");
  await expect(page.getByText("Schedule unavailable")).toBeVisible();
  fail = false;
  await page.getByRole("button", { name: "Try again" }).click();
  await waitForSlots(page);
});

test.describe("current travel timezone", () => {
  test.use({ timezoneId: "Asia/Tokyo" });

  test("suggests the device zone and requires confirmation after a travel override", async ({
    page,
  }) => {
    await page.goto("/ananya/career-strategy");
    await waitForSlots(page);
    await expect(page.getByLabel("YOUR TIME ZONE")).toHaveValue("Asia/Tokyo");
    await expect(
      page.getByText("Suggested by your device", { exact: false }),
    ).toBeVisible();
    await page.locator(".slot").first().click();
    await page.getByRole("button", { name: "Review", exact: true }).click();
    await expect(page.locator(".zone-confirmation")).toContainText(
      "Asia/Tokyo",
    );
    await page.getByRole("button", { name: "Change my time zone" }).click();
    await expect(page.getByLabel("YOUR TIME ZONE")).toBeFocused();
    const recalculated = page.waitForResponse(
      (response) =>
        response.url().includes("/slots?") &&
        response.url().includes("America%2FLos_Angeles"),
    );
    await page.getByLabel("YOUR TIME ZONE").selectOption("America/Los_Angeles");
    await recalculated;
    await waitForSlots(page);
    await expect(
      page.getByText("Selected by you", { exact: false }),
    ).toBeVisible();
    await expect(page.getByRole("dialog")).not.toBeVisible();
    await page.locator(".slot").first().click();
    await page.getByRole("button", { name: "Review", exact: true }).click();
    await expect(page.locator(".zone-confirmation")).toContainText(
      "America/Los_Angeles",
    );
    await page
      .getByRole("button", { name: "Yes, confirm zone & review" })
      .click();
    await expect(page.getByText("YOU · LOS ANGELES")).toBeVisible();
    await page.getByRole("button", { name: "Back to available times" }).click();
    await page.getByRole("button", { name: "Review", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "Check your current time zone." }),
    ).toBeVisible();
  });
});
