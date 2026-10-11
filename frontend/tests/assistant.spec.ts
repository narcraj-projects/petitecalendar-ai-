import { test, expect, type Page } from "@playwright/test";
import { blankEvent } from "../src/components/EventEditor";

const expiry = "2030-01-01T10:15:00Z";
const slot = {
  start: "2030-01-22T14:00:00Z",
  end: "2030-01-22T14:30:00Z",
  date: "2030-01-22",
};
async function publicPage(page: Page, respond: (route: any) => Promise<void>) {
  await page.clock.setFixedTime(new Date("2030-01-01T10:00:00Z"));
  await page.route("**/api/public/events/fixture/meeting**", async (r) => {
    const path = new URL(r.request().url()).pathname;
    if (path.endsWith("/assistant") || path.endsWith("/bookings"))
      return respond(r);
    if (path.endsWith("/slots"))
      return r.fulfill({
        json: { slots: [slot], host_timezone: "Asia/Kolkata" },
      });
    return r.fulfill({
      json: {
        ...blankEvent,
        title: "Fixture meeting",
        durations: [30, 45],
        default_duration: 30,
        host: { name: "Fixture host", timezone: "Asia/Kolkata" },
        availability_ready: true,
        schedule_timezone: "Asia/Kolkata",
      },
    });
  });
  await page.goto("/fixture/meeting");
  await page
    .locator("summary")
    .getByText("Find a time with the assistant")
    .click();
}

test("AI times require current-zone review and conflicts return to selection", async ({
  page,
}, info) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const requests: any[] = [];
  await publicPage(page, async (r) => {
    requests.push({
      path: new URL(r.request().url()).pathname,
      body: r.request().postDataJSON(),
    });
    if (requests.at(-1).path.endsWith("/bookings"))
      return r.fulfill({
        status: 409,
        json: { error: { message: "Time was taken." } },
      });
    return r.fulfill({
      json: {
        kind: "slots",
        message: "Suggested times are not reserved.",
        slots: [slot],
        timezone: "Europe/London",
        host_timezone: "Asia/Kolkata",
        duration: 30,
        expires_at: expiry,
      },
    });
  });
  const panel = page.locator(".assistant-panel");
  await panel
    .getByLabel("Describe when you would like to meet")
    .fill("Next Tuesday afternoon in London");
  await panel.getByRole("button", { name: "Ask assistant" }).click();
  await panel.locator(".assistant-slots button").click();
  await expect(panel.getByText("Check your current time zone.")).toBeVisible();
  await expect(panel.getByLabel("Your name")).toHaveCount(0);
  expect(requests).toHaveLength(1);
  await panel
    .getByRole("button", { name: "Yes, confirm zone & review" })
    .click();
  await expect(panel.getByText("Host:", { exact: false }).last()).toBeVisible();
  await page.screenshot({
    path: info.outputPath("assistant-mobile.png"),
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  for (const button of await panel.getByRole("button").all()) {
    if (await button.isVisible())
      expect((await button.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  }
  await panel.getByLabel("Your name").fill("Fixture invitee");
  await panel.getByLabel("Email address").fill("fixture@example.com");
  await panel.getByRole("button", { name: "Confirm booking" }).click();
  await expect(panel.getByRole("alert")).toContainText("no longer available");
  expect(requests).toHaveLength(2);
  expect(requests[0].body.messages).toEqual([
    "Next Tuesday afternoon in London",
  ]);
  await expect(
    page.getByRole("heading", { name: "Choose a time" }),
  ).toBeVisible();
});

test("AI errors leave manual slots usable and changed duration clears proposals", async ({
  page,
}) => {
  let fail = true;
  await publicPage(page, async (r) =>
    r.fulfill(
      fail
        ? {
            status: 503,
            json: { error: { message: "API credits exhausted." } },
          }
        : {
            json: {
              kind: "slots",
              message: "Available now",
              slots: [slot],
              timezone: "Europe/London",
              host_timezone: "Asia/Kolkata",
              duration: 30,
              expires_at: expiry,
            },
          },
    ),
  );
  const panel = page.locator(".assistant-panel");
  await panel
    .getByLabel("Describe when you would like to meet")
    .fill("Tuesday afternoon");
  await panel.getByRole("button", { name: "Ask assistant" }).click();
  await expect(panel.getByRole("alert")).toContainText("manual controls");
  await expect(page.locator(".picker-slot").first()).toBeEnabled();
  fail = false;
  await panel.getByRole("button", { name: "Ask assistant" }).click();
  await expect(panel.locator(".assistant-slots button")).toHaveCount(1);
  await page.getByRole("button", { name: "45 min", exact: true }).click();
  await expect(page.locator(".assistant-slots button")).toHaveCount(0);
});

async function hostSession(page: Page) {
  await page.clock.setFixedTime(new Date("2030-01-01T10:00:00Z"));
  await page.route("**/api/auth/config", (r) =>
    r.fulfill({
      json: {
        configured: true,
        supabase_url: "https://assistant-test.supabase.co",
        publishable_key: "sb_publishable_test",
      },
    }),
  );
  await page.addInitScript(() => {
    const encode = (v: object) =>
      btoa(JSON.stringify(v))
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
      "sb-assistant-test-auth-token",
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

test("host settings stay a draft until explicit apply and exact retry", async ({
  page,
}, info) => {
  await page.setViewportSize({ width: 1280, height: 1000 });
  await hostSession(page);
  let event = {
    ...blankEvent,
    id: "22222222-2222-4222-8222-222222222222",
    title: "Fixture meeting",
    durations: [30],
    default_duration: 30,
    revision: 1,
  };
  const confirmations: any[] = [];
  await page.route("**/api/me/event-types", (r) =>
    r.fulfill({ json: { events: [event] } }),
  );
  await page.route("**/api/me/assistant**", (r) => {
    expect(r.request().headers().authorization).toMatch(/^Bearer /);
    if (r.request().url().endsWith("/confirm")) {
      confirmations.push(r.request().postDataJSON());
      if (confirmations.length === 1)
        return r.fulfill({
          status: 503,
          json: { error: { message: "Outcome not verified." } },
        });
      event = { ...event, durations: [45], default_duration: 45, revision: 2 };
      return r.fulfill({ json: { event } });
    }
    return r.fulfill({
      json: {
        kind: "proposal",
        action: "event",
        message: "Review before applying.",
        proposal: "synthetic-bound-proposal",
        expires_at: expiry,
        diff: [
          { field: "default_duration", before: 30, after: 45 },
          { field: "buffer_before", before: 10, after: 15 },
        ],
      },
    });
  });
  await page.goto("/app/event-types");
  await page
    .getByText("Draft settings with the assistant", { exact: true })
    .click();
  const panel = page.locator(".assistant-panel");
  await panel
    .getByLabel("Describe the settings change")
    .fill("Make it 45 minutes with a 15 minute buffer");
  await panel.getByRole("button", { name: "Ask assistant" }).click();
  await expect(panel.getByText("Proposed: 45", { exact: true })).toBeVisible();
  expect(confirmations).toHaveLength(0);
  await page.screenshot({
    path: info.outputPath("assistant-host-desktop.png"),
    fullPage: true,
  });
  await panel.getByRole("button", { name: "Apply reviewed changes" }).click();
  await expect(panel.getByLabel("Describe the settings change")).toBeDisabled();
  await panel.getByRole("button", { name: "Retry same proposal" }).click();
  await expect(page.getByText("Assistant changes saved.")).toBeVisible();
  expect(confirmations).toHaveLength(2);
  expect(confirmations[0]).toEqual(confirmations[1]);
});

test("private AI cancellation sends capability only in headers after confirmation", async ({
  page,
}) => {
  await page.clock.setFixedTime(new Date("2030-01-01T10:00:00Z"));
  const id = "44444444-4444-4444-8444-444444444444",
    capability = "a".repeat(64);
  let booking = {
    id,
    start_at: slot.start,
    end_at: slot.end,
    duration: 30,
    status: "confirmed",
    revision: 1,
    invitee_name: "Fixture",
    invitee_email: "fixture@example.com",
    invitee_timezone: "Europe/London",
    snapshot: {
      title: "Fixture meeting",
      location: "Online",
      host_name: "Fixture host",
      host_timezone: "Asia/Kolkata",
      cancellation_hours: 12,
      reschedule_hours: 12,
      reschedule_requires_approval: false,
      allow_alternatives: true,
    },
  };
  const confirm: any[] = [];
  await page.route("**/api/bookings/**", (r) => {
    expect(r.request().headers()["x-booking-capability"]).toBe(capability);
    expect(r.request().url()).not.toContain(capability);
    if (r.request().url().endsWith("/assistant/confirm")) {
      confirm.push(r.request().postDataJSON());
      booking = { ...booking, status: "cancelled", revision: 2 };
      return r.fulfill({ json: { booking } });
    }
    if (r.request().url().endsWith("/assistant"))
      return r.fulfill({
        json: {
          kind: "proposal",
          action: "cancel",
          message: "Confirm to release this time.",
          proposal: "private-cancel-proposal",
          expires_at: expiry,
          diff: [{ field: "status", before: "confirmed", after: "cancelled" }],
        },
      });
    return r.fulfill({ json: { booking } });
  });
  await page.goto(`/booking/${id}#${capability}`);
  await page
    .getByText("Find a time with the assistant", { exact: true })
    .click();
  const panel = page.locator(".assistant-panel");
  await panel
    .getByLabel("Describe when you would like to meet")
    .fill("Cancel this booking");
  await panel.getByRole("button", { name: "Ask assistant" }).click();
  expect(confirm).toHaveLength(0);
  await panel
    .getByRole("button", { name: "Confirm cancellation", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Booking cancelled" }),
  ).toBeVisible();
  expect(confirm).toHaveLength(1);
});

test("signed-in booking uses verified contact without typing or sending it to AI", async ({
  page,
}, info) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await hostSession(page);
  await page.route("**/api/me/booking-contact", (r) => {
    expect(r.request().headers().authorization).toMatch(/^Bearer /);
    return r.fulfill({
      json: { name: "Signed fixture", email: "signed@example.com" },
    });
  });
  const requests: any[] = [];
  await publicPage(page, async (r) => {
    requests.push({
      path: r.request().url(),
      body: r.request().postDataJSON(),
    });
    if (r.request().url().endsWith("/bookings"))
      return r.fulfill({
        status: 409,
        json: { error: { message: "Time was taken." } },
      });
    return r.fulfill({
      json: {
        kind: "slots",
        message: "Available times",
        slots: [slot],
        timezone: "Europe/London",
        host_timezone: "Asia/Kolkata",
        duration: 30,
        expires_at: expiry,
      },
    });
  });
  const panel = page.locator(".assistant-panel");
  await panel
    .getByLabel("Describe when you would like to meet")
    .fill("Book me a meeting");
  await panel.getByRole("button", { name: "Ask assistant" }).click();
  await panel.locator(".assistant-slots button").click();
  await panel
    .getByRole("button", { name: "Yes, confirm zone & review" })
    .click();
  await expect(
    panel.getByText("Booking as Signed fixture", { exact: true }),
  ).toBeVisible();
  await expect(panel.getByLabel("Your name")).toHaveCount(0);
  await expect(panel.getByLabel("Email address")).toHaveCount(0);
  expect(JSON.stringify(requests[0].body)).not.toContain("signed@example.com");
  await page.screenshot({
    path: info.outputPath("assistant-known-contact-mobile.png"),
    fullPage: true,
  });
  await panel
    .getByRole("button", { name: "Confirm booking", exact: true })
    .click();
  expect(requests[1].body.name).toBe("Signed fixture");
  expect(requests[1].body.email).toBe("signed@example.com");
  await expect(panel.getByRole("alert")).toContainText("no longer available");
});

test("guest contact survives changing times without another contact request", async ({
  page,
}) => {
  await page.route("**/api/auth/config", (r) =>
    r.fulfill({ json: { configured: false } }),
  );
  await publicPage(page, (r) =>
    r.fulfill({
      json: {
        kind: "slots",
        message: "Available times",
        slots: [slot],
        timezone: "Europe/London",
        host_timezone: "Asia/Kolkata",
        duration: 30,
        expires_at: expiry,
      },
    }),
  );
  const panel = page.locator(".assistant-panel");
  async function choose() {
    await panel.locator(".assistant-slots button").click();
    await panel
      .getByRole("button", { name: "Yes, confirm zone & review" })
      .click();
  }
  await panel
    .getByLabel("Describe when you would like to meet")
    .fill("Find a time");
  await panel.getByRole("button", { name: "Ask assistant" }).click();
  await choose();
  await panel.getByLabel("Your name").fill("Guest fixture");
  await panel.getByLabel("Email address").fill("guest@example.com");
  await panel
    .getByLabel("Describe when you would like to meet")
    .fill("Try Wednesday instead");
  await panel.getByRole("button", { name: "Ask assistant" }).click();
  await choose();
  await expect(panel.getByLabel("Your name")).toHaveValue("Guest fixture");
  await expect(panel.getByLabel("Email address")).toHaveValue(
    "guest@example.com",
  );
});
