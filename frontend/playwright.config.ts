import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  use: {
    baseURL: "http://127.0.0.1:8017",
    browserName: "chromium",
    channel: "chrome",
    timezoneId: "Asia/Kolkata",
    headless: true,
  },
  reporter: "list",
  workers: 1,
});
