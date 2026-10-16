import { defineConfig, devices } from "@playwright/test";
export default defineConfig({
  testDir: "./tests/kernel",
  timeout: 60000,
  workers: 1,
  use: {
    baseURL: process.env.LEAKSCOPE_KERNEL_URL || "http://127.0.0.1:7833",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  reporter: "list",
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
