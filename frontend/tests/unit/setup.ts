import "@testing-library/jest-dom/vitest"
import { cleanup, configure } from "@testing-library/react"
import { afterEach, vi } from "vitest"

// findBy*／waitFor 的等待上限（預設 1 秒）。路由以 autoCodeSplitting 延遲載入，閒置時就有測試第一次渲染要 3.7 秒，
// 機器忙碌（同時跑多份測試、CI）時更久，1 秒會偶發失敗；放寬上限不影響斷言，成功時照樣立即結束。
configure({ asyncUtilTimeout: 5000 })

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
