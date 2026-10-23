import "@testing-library/jest-dom/vitest"
import { cleanup } from "@testing-library/react"
import { afterEach, vi } from "vitest"

// jsdom 沒有實作 scrollTo（router 捲動復原會呼叫）
window.scrollTo = () => {}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  window.localStorage.clear()
  document.documentElement.className = "dark"
})
