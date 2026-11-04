import { createMemoryHistory, createRouter } from "@tanstack/react-router"
import { fireEvent, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { RouteErrorPage } from "@/components/layout/ErrorPage"
import { DEV_MATCH_SOURCE_TOURNAMENT_ID } from "@/features/competition/match-source"
import { routeTree } from "@/routeTree.gen"
import { renderRouter } from "./render-router"

// 開發工具在測試裡不需要
vi.mock("@tanstack/react-router-devtools", () => ({
  TanStackRouterDevtools: () => null,
}))
vi.mock("@tanstack/react-query-devtools", () => ({
  ReactQueryDevtools: () => null,
}))

function renderAt(path: string) {
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: [path] }),
    defaultErrorComponent: RouteErrorPage,
  })
  renderRouter(router)
  return router
}

const M3 = `/tournaments/${DEV_MATCH_SOURCE_TOURNAMENT_ID}/matches/match-M3`

describe("S4 場次頁路由", () => {
  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it("開發模式：顯示標題、比分、各局與同輪場次，頁面標題含賽事名稱", async () => {
    renderAt(M3)

    expect(
      await screen.findByRole("heading", { level: 1, name: "32 強 · M3" }),
    ).toBeInTheDocument()
    expect(document.querySelector("[data-slot=score-display]")).not.toBeNull()
    expect(document.querySelector("[data-slot=game-list]")).not.toBeNull()
    expect(
      screen.getByRole("heading", { name: "同輪其他場次" }),
    ).toBeInTheDocument()
    await waitFor(() =>
      expect(document.title).toBe("32 強 · M3 · 2026 秋季校際盃 · FLOW"),
    )
  })

  it("點同輪其他場次可以切到另一場", async () => {
    const router = renderAt(M3)

    const link = await screen.findByRole("link", { name: /^M4/ })
    fireEvent.click(link)

    expect(
      await screen.findByRole("heading", { level: 1, name: "32 強 · M4" }),
    ).toBeInTheDocument()
    expect(router.state.location.pathname).toBe(
      `/tournaments/${DEV_MATCH_SOURCE_TOURNAMENT_ID}/matches/match-M4`,
    )
  })

  it("申訴期的場次：申訴期區塊放 Countdown（appeal 變體），截止時間只出現一次", async () => {
    // 假資料第二輪位置 1（M18）是申訴期
    renderAt(`/tournaments/${DEV_MATCH_SOURCE_TOURNAMENT_ID}/matches/match-M18`)

    const region = await screen.findByRole("region", { name: "申訴期" })
    const countdown = region.querySelector("[data-slot=countdown]")
    expect(countdown).not.toBeNull()
    expect(countdown).toHaveAttribute("data-variant", "appeal")
    expect(region.querySelector("[data-slot=appeal-deadline]")).toBeNull()
    expect(region.textContent?.match(/截止/g)).toHaveLength(
      // Countdown 下方「{絕對時間} 截止」一次；已過期時另有「已截止 · 系統處理中」
      region.textContent?.includes("已截止") ? 2 : 1,
    )
  })

  it("找不到場次：顯示 404", async () => {
    renderAt(`/tournaments/${DEV_MATCH_SOURCE_TOURNAMENT_ID}/matches/nope`)
    expect(await screen.findByText("找不到這個頁面。")).toBeInTheDocument()
  })

  it("正式 build（DEV 為 false）：任何 S4 網址都顯示 404，沒有假資料", async () => {
    vi.stubEnv("DEV", false)
    renderAt(M3)
    expect(await screen.findByText("找不到這個頁面。")).toBeInTheDocument()
    expect(screen.queryByText("32 強 · M3")).toBeNull()
  })
})
