import "@testing-library/jest-dom/vitest"
import { cleanup } from "@testing-library/react"
import { afterEach, vi } from "vitest"

// jsdom 沒有實作 scrollTo（router 捲動復原會呼叫）
window.scrollTo = () => {}

// jsdom 沒有的瀏覽器 API：Radix Popover 量尺寸用 ResizeObserver，cmdk 會捲動選取項目
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??= ResizeObserverStub as typeof ResizeObserver
Element.prototype.scrollIntoView ??= () => {}
Element.prototype.hasPointerCapture ??= () => false

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  window.localStorage.clear()
  document.documentElement.className = "dark"
})
