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

const empty = {status: "not_connected", revision: 0, blocking_ids: [], destination_id: null, create_meet: true};
const connected = {...empty, status: "connected", revision: 1};
const calendars = [
  {id: "primary", name: "Work calendar", writable: true, meet_supported: true, primary: true},
  {id: "shared", name: "Shared calendar", writable: false, meet_supported: false, primary: false},
];
test("connect starts separate consent without putting tokens in navigation", async ({page}) => {
  await authenticate(page);
  await page.route("**/api/me/integrations/google", r => r.fulfill({json: {configured: true, connection: empty, calendars: []}}));
  await page.route("**/api/me/integrations/google/connect", r => {
    expect(r.request().method()).toBe("POST");
    return r.fulfill({json: {authorization_url: new URL("/test-google-consent", page.url()).href}});
  });
  await page.route("**/test-google-consent", r => r.fulfill({body: "Synthetic Google consent"}));
  await page.goto("/app/integrations");
  await page.getByRole("button", {name: "Connect Google Calendar", exact: true}).click();
  await expect(page).toHaveURL(/test-google-consent$/);
});
test("calendar selections persist, destination blocks time, disconnect stops future sync", async ({page}, info) => {
  await authenticate(page);
  await page.setViewportSize({width: 1440, height: 1000});
  let connection: any = connected;
  await page.route("**/api/me/integrations/google", r => {
    if (r.request().method() === "PUT") {
      const b = r.request().postDataJSON();
      expect(b.revision).toBe(connection.revision);
      expect(b.blocking_ids).toContain("shared");
      connection = {...b, blocking_ids: [...new Set([...b.blocking_ids, b.destination_id])], status: "connected", revision: b.revision + 1};
      return r.fulfill({json: {connection}});
    }
    return r.fulfill({json: {configured: true, connection, calendars}});
  });
  await page.route("**/api/me/integrations/google/disconnect", r => {
    expect(r.request().postDataJSON().revision).toBe(2);
    connection = {...empty, status: "disconnected", revision: 3};
    return r.fulfill({json: {connection, google_revoked: true}});
  });
  await page.goto("/app/integrations?calendar=connected");
  await expect(page).toHaveURL(/app\/integrations$/);
  await page.getByLabel("Destination for new bookings", {exact: true}).selectOption("primary");
  await expect(page.getByRole("checkbox", {name: /Work calendar/})).toBeChecked();
  await expect(page.getByRole("checkbox", {name: /Work calendar/})).toBeDisabled();
  await page.getByRole("checkbox", {name: /Shared calendar/}).check();
  await page.getByRole("button", {name: "Save calendar settings", exact: true}).click();
  await expect(page.getByRole("status")).toContainText("Calendar settings saved");
  await page.screenshot({path: info.outputPath("calendar-desktop.png"), fullPage: true});
  await page.reload();
  await expect(page.getByRole("checkbox", {name: /Shared calendar/})).toBeChecked();
  await expect(page.getByLabel("Destination for new bookings", {exact: true})).toHaveValue("primary");
  await page.setViewportSize({width: 390, height: 844});
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({path: info.outputPath("calendar-mobile.png"), fullPage: true});
  await page.getByRole("button", {name: "Disconnect Google Calendar", exact: true}).click();
  await expect(page.getByRole("status")).toContainText("access revoked");
  await expect(page.getByRole("heading", {name: "Choose your calendars"})).not.toBeVisible();
});
test("failed calendar check offers reload and does not show saved success", async ({page}) => {
  await authenticate(page);
  let failed = true;
  await page.route("**/api/me/integrations/google", r => failed ? r.fulfill({status: 503, json: {error: {message: "Google Calendar could not be checked. Reconnect or retry."}}}) : r.fulfill({json: {configured: true, connection: connected, calendars}}));
  await page.goto("/app/integrations");
  await expect(page.getByRole("alert")).toContainText("Reconnect or retry");
  failed = false;
  await page.getByRole("button", {name: "Reload connection"}).click();
  await expect(page.getByRole("heading", {name: "Choose your calendars"})).toBeVisible();
  await expect(page.getByRole("alert")).not.toBeVisible();
});
test("private confirmation refresh shows the delivered Meet link", async ({page}, info) => {
  const booking = {id: "33333333-3333-4333-8333-333333333333", start_at: "2026-10-20T05:30:00Z", end_at: "2026-10-20T06:00:00Z", duration: 30, invitee_name: "Fixture", invitee_email: "fixture@example.com", invitee_timezone: "Asia/Kolkata", status: "confirmed", revision: 1, calendar_status: "queued", email_status: "not_enabled", snapshot: {title: "Calendar test", host_name: "Fixture host", host_timezone: "Asia/Kolkata", location: "Online", cancellation_hours: 12, reschedule_hours: 12}};
  let delivered = false;
  await page.route("**/api/bookings/**", r => {
    expect(r.request().headers()["x-booking-capability"]).toBe("a".repeat(64));
    return r.fulfill({json: {booking: {...booking, calendar_status: delivered ? "synced" : "queued", meet_url: delivered ? "https://meet.google.com/abc-defg-hij" : null}}});
  });
  await page.setViewportSize({width: 390, height: 844});
  await page.goto(`/booking/${booking.id}#${"a".repeat(64)}`);
  await expect(page.getByText("Calendar delivery queued", {exact: true})).toBeVisible();
  await expect(page.getByRole("link", {name: "Join Google Meet"})).not.toBeVisible();
  delivered = true;
  await page.getByRole("button", {name: "Refresh calendar status", exact: true}).click();
  await expect(page.getByText("Calendar event created", {exact: true})).toBeVisible();
  await expect(page.getByRole("link", {name: "Join Google Meet"})).toHaveAttribute("href", "https://meet.google.com/abc-defg-hij");
  await page.screenshot({path: info.outputPath("meet-confirmation-mobile.png"), fullPage: true});
});
