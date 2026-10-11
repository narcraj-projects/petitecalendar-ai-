import { test, expect, type Page } from "@playwright/test";
import { blankEvent, type EventType } from "../src/components/EventEditor";

async function setup(page: Page) {
  await page.route("**/api/auth/config", (r) =>
    r.fulfill({
      json: {
        configured: true,
        supabase_url: "https://events-test.supabase.co",
        publishable_key: "sb_publishable_test",
      },
    }),
  );
  await page.addInitScript(() => {
    const encode = (obj: object) =>
      btoa(JSON.stringify(obj))
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
      "sb-events-test-auth-token",
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
  const events: EventType[] = [];
  await page.route("**/api/me/event-types**", (r) => {
    const request = r.request();
    if (request.method() === "GET") return r.fulfill({ json: { events } });
    const body = request.postDataJSON();
    const id = new URL(request.url()).pathname.split("/")[4];
    if (events.some((e) => e.slug === body.slug && e.id !== id))
      return r.fulfill({
        status: 409,
        json: {
          error: { message: "You already have an event with this slug." },
        },
      });
    let event: EventType;
    if (request.method() === "POST") {
      event = {
        ...blankEvent,
        ...body,
        id: "22222222-2222-4222-8222-222222222222",
        published: false,
        revision: 1,
      };
      events.push(event);
    } else {
      const index = events.findIndex((e) => e.id === id);
      event = { ...body, id, revision: body.revision + 1 };
      events[index] = event;
    }
    return r.fulfill({ json: { event } });
  });
  await page.route("**/api/public/events/test-host/**", (r) => {
    const slug = new URL(r.request().url()).pathname.split("/").at(-1);
    const event = events.find((e) => e.slug === slug && e.published);
    return event
      ? r.fulfill({
          json: {
            ...event,
            host: { name: "Test Host", timezone: "Asia/Kolkata" },
            availability_ready: false,
          },
        })
      : r.fulfill({
          status: 404,
          json: { error: { message: "This event is not available." } },
        });
  });
  return events;
}

test("create, edit policies, reload, publish and unpublish an event", async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  const events = await setup(page);
  await page.goto("/app/event-types");
  await page
    .getByRole("button", { name: "Create your first event", exact: false })
    .click();
  await page.getByLabel("Event title", { exact: true }).fill("Career strategy");
  await expect(page.getByLabel("Booking link slug")).toHaveValue(
    "career-strategy",
  );
  await page.getByLabel("Description").fill("Discuss your next career move.");
  await page.getByRole("button", { name: "Save draft", exact: true }).click();
  await expect(page.getByRole("status")).toHaveText("Draft saved.");
  expect(events[0].published).toBe(false);
  await page
    .getByRole("button", { name: "Limits & policies", exact: true })
    .click();
  await page.getByLabel("Minimum notice (minutes)").fill("180");
  await page.getByLabel("Reschedules need my approval").check();
  await page.screenshot({
    path: testInfo.outputPath("event-editor-desktop.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "Save changes", exact: true }).click();
  expect(events[0].notice_minutes).toBe(180);
  expect(events[0].reschedule_requires_approval).toBe(true);
  await page.reload();
  await page.getByRole("button", { name: "Publication", exact: true }).click();
  await page.getByLabel("Publish this event").check();
  await page.getByRole("button", { name: "Save changes", exact: true }).click();
  await expect(page.getByRole("status")).toHaveText(
    "Event saved and published.",
  );
  await page.goto("/test-host/career-strategy");
  await expect(
    page.getByRole("heading", { name: "Career strategy", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Scheduling will open soon.")).toBeVisible();
  await page.getByRole("button", { name: "60 min", exact: true }).click();
  await expect(page.getByText("60 minutes", { exact: true })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: testInfo.outputPath("event-public-mobile.png"),
    fullPage: true,
  });
  await page.goto("/app/event-types/" + events[0].id);
  await page.getByRole("button", { name: "Publication", exact: true }).click();
  await page.getByLabel("Publish this event").uncheck();
  await page.getByRole("button", { name: "Save changes", exact: true }).click();
  await page.goto("/test-host/career-strategy");
  await expect(
    page.getByRole("heading", {
      name: "This event is not available.",
      exact: true,
    }),
  ).toBeVisible();
});

test("invalid durations and duplicate slug keep the editor open on mobile", async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const events = await setup(page);
  events.push({
    ...blankEvent,
    title: "Existing event",
    slug: "existing-event",
    id: "33333333-3333-4333-8333-333333333333",
    revision: 1,
  });
  await page.goto("/app/event-types/new");
  await page.getByLabel("Event title", { exact: true }).fill("New event");
  await page.getByLabel("Duration options (minutes)").fill("30, 30");
  await page.getByRole("button", { name: "Save draft", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("unique durations");
  await page.getByLabel("Duration options (minutes)").fill("30, 45, 60");
  await page.getByLabel("Booking link slug").fill("existing-event");
  await page.getByRole("button", { name: "Save draft", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("already have an event");
  await expect(page.getByLabel("Event title", { exact: true })).toHaveValue(
    "New event",
  );
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: testInfo.outputPath("event-editor-mobile.png"),
    fullPage: true,
  });
});
