import { test, expect } from "@playwright/test";

test("host reviews recipients and branded email before sending; uncertain retry is identical", async ({
  page,
}) => {
  await page.route("**/api/auth/config", (r) =>
    r.fulfill({
      json: {
        configured: true,
        supabase_url: "https://sharing-test.supabase.co",
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
      "sb-sharing-test-auth-token",
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
          display_name: "Sample Host",
          username: "sample-host",
          timezone: "UTC",
        },
      },
    }),
  );
  const event = {
    id: "22222222-2222-4222-8222-222222222222",
    revision: 3,
    title: "Project Review",
    slug: "project-review",
    durations: [30, 45],
    default_duration: 45,
    location: "Google Meet",
    published: true,
  };
  await page.route("**/api/me/event-types", (r) =>
    r.fulfill({ json: { events: [event] } }),
  );
  const posts: object[] = [];
  let accepted = false;
  await page.route(`**/api/me/event-types/${event.id}/invitations**`, (r) => {
    if (r.request().method() === "POST") {
      posts.push(r.request().postDataJSON());
      if (posts.length === 1) return r.abort();
      return r.fulfill({
        json: { invitation: { id: "batch", counts: { queued: 2 } } },
      });
    }
    return r.fulfill({
      json: {
        invitation: {
          id: "batch",
          counts: accepted ? { accepted: 2 } : { queued: 2 },
        },
      },
    });
  });
  await page.goto("/app/event-types");
  await page
    .getByRole("button", { name: "Share Project Review by email" })
    .click();
  await page.getByLabel("Guest email addresses").fill("bad-address");
  await page.getByRole("button", { name: "Review invitation" }).click();
  await expect(page.getByRole("alert")).toContainText("unique email addresses");
  await page
    .getByLabel("Guest email addresses")
    .fill("guest@example.com, friend@example.com");
  await page.getByRole("button", { name: "Review invitation" }).click();
  await expect(page.getByLabel("Invitation email preview")).toContainText(
    "A conversation worth making time for.",
  );
  expect(posts).toHaveLength(0);
  await page
    .getByRole("button", { name: "Send booking link", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Retry same invitation" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Edit recipients" }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Retry same invitation" }).click();
  expect(posts[0]).toEqual(posts[1]);
  await expect(page.getByRole("status")).toContainText("Invitations queued.");
  accepted = true;
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page.getByRole("status")).toContainText(
    "2 accepted by the email service",
  );
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
