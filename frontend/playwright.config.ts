import { defineConfig, devices } from '@playwright/test';
import 'dotenv/config'

// 端對端測試放在 frontend/tests/（之後的 Story 再加入規格）
const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://localhost:5173'

/**
 * See https://playwright.dev/docs/test-configuration.
 */
export default defineConfig({
  testDir: './tests',
  // tests/unit/ 是 Vitest 單元測試（bun run test:unit），不由 Playwright 執行
  testIgnore: /[\\/]tests[\\/]unit[\\/]/,
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? 'blob' : 'html',
  use: {
    baseURL,
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: process.env.PLAYWRIGHT_BASE_URL
    ? undefined
    : {
        command: 'bun run dev',
        url: baseURL,
        reuseExistingServer: !process.env.CI,
      },
});
