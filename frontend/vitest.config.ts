import path from "node:path"
import react from "@vitejs/plugin-react-swc"
import { defineConfig } from "vitest/config"

// 前端單元測試（jsdom）；端對端測試仍由 Playwright 執行 tests/ 下其他檔案。
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "./src"),
    },
  },
  test: {
    environment: "jsdom",
    include: ["tests/unit/**/*.test.{ts,tsx}"],
    setupFiles: ["tests/unit/setup.ts"],
  },
})
