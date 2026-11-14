import { defineConfig } from "@playwright/test";

// Uses the Chrome already installed on this PC (no browser download).
// The dev server is started if it is not already running; the specs need the local engine too.
export default defineConfig({
  testDir: "./e2e",
  timeout: 45_000,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:5173",
    channel: "chrome",
    headless: true,
    viewport: { width: 1440, height: 900 },
    screenshot: "only-on-failure",
  },
  webServer: {
    command: "npx vite --host 127.0.0.1",
    url: "http://127.0.0.1:5173",
    reuseExistingServer: true,
    timeout: 60_000,
  },
});
