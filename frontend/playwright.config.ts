import { defineConfig, devices } from "@playwright/test";

const PORT = 3100;
const MOCK_API_PORT = 8100;
const isCI = !!process.env.CI;

export default defineConfig({
  testDir: "e2e",
  forbidOnly: isCI,
  retries: isCI ? 2 : 0,
  reporter: isCI ? [["github"], ["html", { open: "never" }]] : "list",
  use: { baseURL: `http://localhost:${PORT}`, trace: "on-first-retry" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      // Stand-in for FastAPI; the Next server below is pointed at it.
      command: "node e2e/mock-api.mjs",
      url: `http://127.0.0.1:${MOCK_API_PORT}/shoes`,
      reuseExistingServer: !isCI,
      timeout: 30_000,
    },
    {
      // CI serves the production build made by an earlier step.
      command: isCI ? `npx next start -p ${PORT}` : `npx next dev -p ${PORT}`,
      url: `http://localhost:${PORT}`,
      reuseExistingServer: !isCI,
      timeout: 120_000,
      env: { CRUXUP_API_URL: `http://127.0.0.1:${MOCK_API_PORT}` },
    },
  ],
});
