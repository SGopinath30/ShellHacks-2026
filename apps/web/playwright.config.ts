import { defineConfig } from "@playwright/test";
const port = Number(process.env.PLAYWRIGHT_PORT ?? 3100);
const baseURL = `http://127.0.0.1:${port}`;
export default defineConfig({
  testDir: "./tests",
  use: { baseURL, channel: "chrome", headless: true },
  webServer: {
    command: `npm run start -- --port ${port}`,
    url: baseURL,
    reuseExistingServer: false,
    timeout: 60000,
  },
});
