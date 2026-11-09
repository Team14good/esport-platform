import { createMemoryHistory, createRouter } from "@tanstack/react-router"
import { fireEvent, screen, waitFor, within } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import {
  CompetitionService,
  DisputesService,
  type PublicMatchDetail,
  type ScoreEntryState,
} from "@/client"
import { RouteErrorPage } from "@/components/layout/ErrorPage"
import { createBracketFixture } from "@/features/competition/bracket-fixtures"
import { matchDetailFromBracket } from "@/features/competition/match-fixtures"
import { routeTree } from "@/routeTree.gen"
import { signInAs } from "./auth-fixtures"
import { httpError } from "./helpers"
import { renderRouter } from "./render-router"

// 開發工具在測試裡不需要
vi.mock("@tanstack/react-router-devtools", () => ({
  TanStackRouterDevtools: () => null,
}))
vi.mock("@tanstack/react-query-devtools", () => ({
  ReactQueryDevtools: () => null,
}))

type ReadScoreEntryResult = Awaited<
  ReturnType<typeof CompetitionService.readScoreEntry>
>
type ReadStatusResult = Awaited<
  ReturnType<typeof CompetitionService.readCheckInStatus>
>
type ReadAppealStateResult = Awaited<
  ReturnType<typeof DisputesService.readAppealState>
>

// 單元測試的場次資料：32 隊「進行中」對戰樹推導（match-fixtures 只給測試用）
const BRACKET = createBracketFixture({ teamCount: 32, scenario: "in_progress" })
const TOURNAMENT_ID = BRACKET.tournament_id

function detailOf(matchId: string): PublicMatchDetail | undefined {
  return matchDetailFromBracket(BRACKET, matchId)
}

const NOT_FOUND = httpError(404, {
  detail: { code: "MATCH_NOT_FOUND", message: "找不到這個場次。" },
})

/** 公開單場 API：依 match_id 回傳推導出的場次，找不到回 404 */
function mockPublicMatch(
  override?: (detail: PublicMatchDetail) => PublicMatchDetail,
) {
  return vi
    .spyOn(CompetitionService, "readPublicMatch")
    .mockImplementation((async ({ path }: { path: { match_id: string } }) => {
      const detail = detailOf(path.match_id)
      if (!detail) throw NOT_FOUND
      return { data: override ? override(detail) : detail }
    }) as unknown as typeof CompetitionService.readPublicMatch)
}

function renderAt(path: string) {
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: [path] }),
    defaultErrorComponent: RouteErrorPage,
  })
  renderRouter(router)
  return router
}

const matchUrl = (matchId: string) =>
  `/tournaments/${TOURNAMENT_ID}/matches/${matchId}`

describe("S4 場次頁路由", () => {
  it("顯示標題、比分、各局與同輪場次，頁面標題含賽事名稱", async () => {
    const read = mockPublicMatch()
    renderAt(matchUrl("match-M3"))

    expect(
      await screen.findByRole("heading", { level: 1, name: "32 強 · M3" }),
    ).toBeInTheDocument()
    expect(read).toHaveBeenCalledWith({
      path: { tournament_id: TOURNAMENT_ID, match_id: "match-M3" },
    })
    expect(document.querySelector("[data-slot=score-display]")).not.toBeNull()
    expect(document.querySelector("[data-slot=game-list]")).not.toBeNull()
    expect(
      screen.getByRole("heading", { name: "同輪其他場次" }),
    ).toBeInTheDocument()
    await waitFor(() =>
      expect(document.title).toBe("32 強 · M3 · 2026 秋季校際盃 · FLOW"),
    )
  })

  it("返回連結指向賽事的對戰表", async () => {
    mockPublicMatch()
    renderAt(matchUrl("match-M3"))

    const back = await screen.findByRole("link", { name: /^← / })
    expect(back).toHaveAttribute(
      "href",
      `/tournaments/${TOURNAMENT_ID}/bracket`,
    )
  })

  it("點同輪其他場次可以切到另一場", async () => {
    mockPublicMatch()
    const router = renderAt(matchUrl("match-M3"))

    const link = await screen.findByRole("link", { name: /^M4/ })
    fireEvent.click(link)

    expect(
      await screen.findByRole("heading", { level: 1, name: "32 強 · M4" }),
    ).toBeInTheDocument()
    expect(router.state.location.pathname).toBe(matchUrl("match-M4"))
  })

  it("申訴期的場次：申訴期區塊放 Countdown（appeal 變體），截止時間只出現一次", async () => {
    mockPublicMatch()
    // 假資料第二輪位置 1（M18）是申訴期
    renderAt(matchUrl("match-M18"))

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

  it("申訴期的場次：隊長在申訴期區塊看到「提出申訴」", async () => {
    signInAs()
    mockPublicMatch()
    vi.spyOn(CompetitionService, "readScoreEntry").mockResolvedValue({
      data: {
        is_scorer: false,
        reason: null,
        games: [],
        series: null,
        submitted_by_name: null,
        submitted_at: null,
      },
    } as unknown as ReadScoreEntryResult)
    const readAppeal = vi
      .spyOn(DisputesService, "readAppealState")
      .mockResolvedValue({
        data: {
          can_file: true,
          already_filed: false,
          deadline: "2026-10-18T06:22:00Z",
          reason: null,
        },
      } as unknown as ReadAppealStateResult)
    // 假資料第二輪位置 1（M18）是申訴期
    renderAt(matchUrl("match-M18"))

    const region = await screen.findByRole("region", { name: "申訴期" })
    expect(
      await within(region).findByRole("button", { name: "提出申訴" }),
    ).toBeEnabled()
    expect(readAppeal).toHaveBeenCalledWith({
      path: { tournament_id: TOURNAMENT_ID, match_id: "match-M18" },
    })
  })

  it("找不到場次（API 404）：顯示 404", async () => {
    mockPublicMatch()
    renderAt(matchUrl("nope"))
    expect(await screen.findByText("找不到這個頁面。")).toBeInTheDocument()
  })

  it("未登入觀眾：報到面板在右欄最上方，沒有按鈕，不呼叫報到與比分登錄 API", async () => {
    const readStatus = vi.spyOn(CompetitionService, "readCheckInStatus")
    const readScore = vi.spyOn(CompetitionService, "readScoreEntry")
    mockPublicMatch((detail) => ({
      ...detail,
      status: "scheduled",
      outcome: null,
      winner_id: null,
      wins_a: 0,
      wins_b: 0,
      games: [],
    }))
    renderAt(matchUrl("match-M3"))

    expect(
      await screen.findByRole("heading", { level: 2, name: "報到" }),
    ).toBeInTheDocument()
    const aside = document.querySelector("[data-slot=match-aside]")
    expect(aside?.firstElementChild).toHaveAttribute(
      "data-slot",
      "match-check-in",
    )
    expect(screen.queryByRole("button", { name: "報到" })).toBeNull()
    expect(readStatus).not.toHaveBeenCalled()
    expect(readScore).not.toHaveBeenCalled()
  })

  it("記分者：左欄是比分登錄面板，不顯示公開各局列表", async () => {
    signInAs()
    mockPublicMatch()
    vi.spyOn(CompetitionService, "readCheckInStatus").mockResolvedValue({
      data: {
        side: null,
        reason: "not_captain",
        opens_at: "2026-10-18T04:30:00Z",
      },
    } as unknown as ReadStatusResult)
    const state: ScoreEntryState = {
      is_scorer: true,
      reason: null,
      games: [{ game_no: 1, winner_side: "a", score_a: 13, score_b: 9 }],
      series: {
        wins_a: 1,
        wins_b: 0,
        winner: null,
        can_submit: false,
        wins_needed: 2,
        reason: "not_decided",
      },
      submitted_by_name: null,
      submitted_at: null,
    }
    vi.spyOn(CompetitionService, "readScoreEntry").mockResolvedValue({
      data: state,
    } as unknown as ReadScoreEntryResult)
    // 假資料第二輪第一場（M17）是進行中、有已登錄的局
    renderAt(matchUrl("match-M17"))

    expect(
      await screen.findByRole("heading", { name: "比分登錄" }),
    ).toBeInTheDocument()
    expect(document.querySelector("[data-slot=game-list]")).toBeNull()
  })

  it("非記分者登入：只有觀眾檢視", async () => {
    signInAs()
    mockPublicMatch()
    vi.spyOn(CompetitionService, "readCheckInStatus").mockResolvedValue({
      data: {
        side: null,
        reason: "not_captain",
        opens_at: "2026-10-18T04:30:00Z",
      },
    } as unknown as ReadStatusResult)
    const readScore = vi
      .spyOn(CompetitionService, "readScoreEntry")
      .mockResolvedValue({
        data: { is_scorer: false, games: [], series: null },
      } as unknown as ReadScoreEntryResult)
    renderAt(matchUrl("match-M17"))

    expect(
      await screen.findByRole("heading", { level: 1, name: "16 強 · M17" }),
    ).toBeInTheDocument()
    await waitFor(() => expect(readScore).toHaveBeenCalled())
    expect(document.querySelector("[data-slot=game-list]")).not.toBeNull()
    expect(screen.queryByRole("heading", { name: "比分登錄" })).toBeNull()
  })

  it("API 回傳的資料直接顯示，不經過任何假資料", async () => {
    mockPublicMatch((detail) => ({
      ...detail,
      tournament: { ...detail.tournament, name: "真資料盃" },
    }))
    renderAt(matchUrl("match-M3"))
    expect(await screen.findByText("← 真資料盃")).toBeInTheDocument()
  })
})
