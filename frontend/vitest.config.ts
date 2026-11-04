import { defineConfig, mergeConfig } from "vitest/config"

import viteConfig from "./vite.config"

// 前端單元測試（jsdom）；端對端測試仍由 Playwright 執行 tests/ 下其他檔案。
// 合併 vite.config.ts：別名與外掛（包含產生 routeTree.gen.ts 的 TanStack Router 外掛）只維護一份，
// 新增路由後不必先跑 dev 或 build，測試就會用到最新的路由樹。
export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: "jsdom",
      include: ["tests/unit/**/*.test.{ts,tsx}"],
      setupFiles: ["tests/unit/setup.ts"],
      // 每個測試的上限（預設 5 秒）：要大於 setup.ts 的 asyncUtilTimeout（5 秒），一個測試裡等好幾次也不會先被砍掉
      testTimeout: 15000,
    },
  }),
)
