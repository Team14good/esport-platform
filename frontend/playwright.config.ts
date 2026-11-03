import { defineConfig, devices } from "@playwright/test"
import "dotenv/config"

// 端對端測試放在 frontend/tests/e2e/；在 compose 裡執行：docker compose --profile e2e run --rm e2e
const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:5173"

/**
 * 設定說明：https://playwright.dev/docs/test-configuration
 */
export default defineConfig({
  testDir: "./tests",
  // tests/unit/ 是 Vitest 單元測試（bun run test:unit），不由 Playwright 執行
  testIgnore: /[\\/]tests[\\/]unit[\\/]/,
  // 有 E2E_PROXY 時把 localhost 的埠轉到 compose 服務，並等前端與 API 就緒
  globalSetup: "./tests/e2e/support/proxy.ts",
  outputDir: "test-results",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  // HTML 報告不自動開啟：在容器裡開啟會一直等待
  reporter: process.env.CI
    ? "blob"
    : [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "desktop",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      // NFR-7：同一組測試以 375 px 寬的手機視窗再跑一次
      name: "mobile-375",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 375, height: 812 },
        isMobile: true,
        hasTouch: true,
      },
    },
  ],
  webServer: process.env.PLAYWRIGHT_BASE_URL
    ? undefined
    : {
        command: "bun run dev",
        url: baseURL,
        reuseExistingServer: !process.env.CI,
      },
})
