import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import {
  CompetitionService,
  type PublicMatchDetail,
  type ScoreEntryState,
} from "@/client"
import {
  scoreErrorReason,
  useMatchScoreEntry,
} from "@/features/competition/MatchScoreEntry"
import { ACCESS_TOKEN_STORAGE_KEY } from "@/features/identity/auth"
import * as feedback from "@/lib/feedback"
import { httpError } from "./helpers"
import { matchDetail } from "./match-detail-fixture"

vi.mock("@/lib/feedback", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/feedback")>()),
  notifyError: vi.fn(),
}))

type ReadScoreEntryResult = Awaited<
  ReturnType<typeof CompetitionService.readScoreEntry>
>
type WriteResult = Awaited<ReturnType<typeof CompetitionService.recordGame>>

const SERIES_EMPTY = {
  wins_a: 0,
  wins_b: 0,
  winner: null,
  can_submit: false,
  wins_needed: 2,
  reason: "not_decided" as const,
}

/** 記分者、兩隊都已報到、還沒有任何一局 */
function scorerState(
  overrides: Partial<ScoreEntryState> = {},
): ScoreEntryState {
  return {
    is_scorer: true,
    reason: null,
    games: [],
    series: SERIES_EMPTY,
    submitted_by_name: null,
    submitted_at: null,
    ...overrides,
  }
}

function mockState(state: ScoreEntryState) {
  return vi
    .spyOn(CompetitionService, "readScoreEntry")
    .mockResolvedValue({ data: state } as unknown as ReadScoreEntryResult)
}

function signIn() {
  window.localStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, "token-1")
}

function Harness({
  detail,
  refresh,
}: {
  detail: PublicMatchDetail
  refresh: () => Promise<unknown>
}) {
  const panel = useMatchScoreEntry({ detail, refresh })
  return <div data-testid="slot">{panel ?? "沒有面板"}</div>
}

function renderScoreEntry(
  detail: PublicMatchDetail = matchDetail({ status: "live" }),
) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  // 重抓：讓這一場的查詢重新取得（跟 S4 路由一樣 invalidate）
  const refresh = vi.fn(() => queryClient.invalidateQueries())
  render(
    <QueryClientProvider client={queryClient}>
      <Harness detail={detail} refresh={refresh} />
    </QueryClientProvider>,
  )
  return { refresh }
}

async function typeGame(scoreA: string, scoreB: string) {
  await userEvent.type(
    await screen.findByRole("textbox", { name: "第 1 局 成大 Kraken 分數" }),
    scoreA,
  )
  await userEvent.type(
    screen.getByRole("textbox", { name: "第 1 局 北科 Ember 分數" }),
    scoreB,
  )
  await userEvent.click(screen.getByRole("button", { name: "登錄" }))
}

describe("寫入錯誤碼轉成面板的原因代碼", () => {
  it.each([
    ["SCORE_TIE", "tie"],
    ["SCORE_INVALID", "invalid_score"],
    ["SERIES_DECIDED", "series_decided"],
    ["REDUNDANT_GAMES", "redundant_games"],
    ["INVALID_GAME_NO", "invalid_game_no"],
    ["NOT_LAST_GAME", "not_last_game"],
    ["SERIES_NOT_DECIDED", "not_decided"],
  ])("%s → %s", (code, reason) => {
    expect(
      scoreErrorReason(httpError(409, { detail: { code, message: "x" } })),
    ).toBe(reason)
  })

  it("其他錯誤（已送出、連線中斷、欄位錯誤）不轉換", () => {
    expect(
      scoreErrorReason(
        httpError(409, {
          detail: { code: "RESULT_ALREADY_SUBMITTED", message: "x" },
        }),
      ),
    ).toBeNull()
    expect(scoreErrorReason(new Error("network"))).toBeNull()
    expect(
      scoreErrorReason(
        httpError(422, { detail: [{ loc: ["body", "score_a"], msg: "x" }] }),
      ),
    ).toBeNull()
  })
})

describe("S4 比分登錄面板的資料轉接", () => {
  beforeEach(() => {
    vi.mocked(feedback.notifyError).mockClear()
  })

  it("未登入：沒有面板，不呼叫比分登錄 API", async () => {
    const read = vi.spyOn(CompetitionService, "readScoreEntry")
    renderScoreEntry()
    expect(screen.getByTestId("slot")).toHaveTextContent("沒有面板")
    expect(read).not.toHaveBeenCalled()
  })

  it("非記分者登入：沒有面板", async () => {
    signIn()
    const read = mockState({ is_scorer: false, games: [], series: null })
    renderScoreEntry()
    await waitFor(() => expect(read).toHaveBeenCalled())
    expect(screen.getByTestId("slot")).toHaveTextContent("沒有面板")
  })

  it("記分者：顯示比分登錄面板", async () => {
    signIn()
    mockState(scorerState())
    renderScoreEntry()
    expect(
      await screen.findByRole("heading", { name: "比分登錄" }),
    ).toBeInTheDocument()
    expect(screen.getByText("可開始")).toBeInTheDocument()
  })

  it("兩隊尚未都報到：面板停用並寫「等待雙方報到」", async () => {
    signIn()
    mockState(scorerState({ reason: "check_in_incomplete" }))
    renderScoreEntry(matchDetail())
    expect(await screen.findByText("等待雙方報到")).toBeInTheDocument()
  })

  it("判棄權（已送出卻沒有送出者）：沒有面板", async () => {
    signIn()
    const read = mockState(
      scorerState({
        reason: "result_submitted",
        series: { ...SERIES_EMPTY, wins_a: 2 },
      }),
    )
    renderScoreEntry(
      matchDetail({ status: "appeal_window", outcome: "forfeit" }),
    )
    await waitFor(() => expect(read).toHaveBeenCalled())
    expect(screen.getByTestId("slot")).toHaveTextContent("沒有面板")
  })

  it("登錄成功：送出比分、重抓後才完成", async () => {
    signIn()
    const read = mockState(scorerState())
    const record = vi
      .spyOn(CompetitionService, "recordGame")
      .mockResolvedValue({ data: scorerState() } as unknown as WriteResult)
    const { refresh } = renderScoreEntry()

    read.mockResolvedValue({
      data: scorerState({
        games: [{ game_no: 1, winner_side: "a", score_a: 13, score_b: 9 }],
        series: { ...SERIES_EMPTY, wins_a: 1 },
      }),
    } as unknown as ReadScoreEntryResult)
    await typeGame("13", "9")

    expect(record).toHaveBeenCalledWith({
      path: { tournament_id: "t1", match_id: "match-M3", game_no: 1 },
      body: { score_a: 13, score_b: 9 },
    })
    expect(refresh).toHaveBeenCalled()
    expect(await screen.findByText("已登錄")).toBeInTheDocument()
  })

  it("勝負型態：只送勝方", async () => {
    signIn()
    mockState(scorerState())
    const record = vi
      .spyOn(CompetitionService, "recordGame")
      .mockResolvedValue({ data: scorerState() } as unknown as WriteResult)
    renderScoreEntry(matchDetail({ status: "live", score_type: "win_loss" }))

    await userEvent.click(
      await screen.findByRole("button", { name: "北科 Ember" }),
    )
    await userEvent.click(screen.getByRole("button", { name: "登錄" }))

    expect(record).toHaveBeenCalledWith(
      expect.objectContaining({ body: { winner_side: "b" } }),
    )
  })

  it("比分規則錯誤：該列顯示原因，不跳 Toast", async () => {
    signIn()
    mockState(scorerState())
    vi.spyOn(CompetitionService, "recordGame").mockRejectedValue(
      httpError(409, {
        detail: { code: "SCORE_INVALID", message: "比分不符合比分型態。" },
      }),
    )
    renderScoreEntry()

    await typeGame("13", "9")

    expect(await screen.findByRole("alert")).toHaveTextContent("比分格式不正確")
    expect(feedback.notifyError).not.toHaveBeenCalled()
  })

  it("非比分規則錯誤（已送出）：Toast 顯示伺服器訊息並重抓", async () => {
    signIn()
    mockState(scorerState())
    const error = httpError(409, {
      detail: {
        code: "RESULT_ALREADY_SUBMITTED",
        message: "這場的結果已經送出。",
      },
    })
    vi.spyOn(CompetitionService, "recordGame").mockRejectedValue(error)
    const { refresh } = renderScoreEntry()

    await typeGame("13", "9")

    await waitFor(() =>
      expect(feedback.notifyError).toHaveBeenCalledWith(error),
    )
    expect(refresh).toHaveBeenCalled()
    expect(screen.queryByRole("alert")).toBeNull()
  })

  it("送出系列結果：重抓後面板唯讀「{送出者} 送出 · 時間」", async () => {
    signIn()
    const decided = {
      ...SERIES_EMPTY,
      wins_a: 2,
      winner: "a" as const,
      can_submit: true,
      reason: null,
    }
    const games = [
      { game_no: 1, winner_side: "a" as const, score_a: 13, score_b: 9 },
      { game_no: 2, winner_side: "a" as const, score_a: 13, score_b: 7 },
    ]
    const read = mockState(scorerState({ games, series: decided }))
    const submit = vi
      .spyOn(CompetitionService, "submitResult")
      .mockResolvedValue({ data: scorerState() } as unknown as WriteResult)
    renderScoreEntry()

    read.mockResolvedValue({
      data: scorerState({
        reason: "result_submitted",
        games,
        series: decided,
        submitted_by_name: "裁判小明",
        // 台北 10/18（日）13:40
        submitted_at: "2026-10-18T05:40:00Z",
      }),
    } as unknown as ReadScoreEntryResult)
    await userEvent.click(
      await screen.findByRole("button", { name: "送出系列結果" }),
    )
    const dialog = await screen.findByRole("alertdialog")
    await userEvent.click(
      within(dialog).getByRole("button", { name: "送出系列結果" }),
    )

    expect(submit).toHaveBeenCalledWith({
      path: { tournament_id: "t1", match_id: "match-M3" },
    })
    expect(
      await screen.findByText(/裁判小明 送出 · 10\/18（日）13:40/),
    ).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "送出系列結果" })).toBeNull()
  })
})

describe("比分登錄查詢的重抓與換場", () => {
  function renderWithRerender(detail: PublicMatchDetail) {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    const refresh = () => queryClient.invalidateQueries()
    const view = (d: PublicMatchDetail) => (
      <QueryClientProvider client={queryClient}>
        <Harness detail={d} refresh={refresh} />
      </QueryClientProvider>
    )
    const { rerender } = render(view(detail))
    return (d: PublicMatchDetail) => rerender(view(d))
  }

  it("對手報到後 updated_at 沒變：仍因報到時間改變而重抓，面板解鎖", async () => {
    signIn()
    const read = vi
      .spyOn(CompetitionService, "readScoreEntry")
      .mockResolvedValueOnce({
        data: scorerState({ reason: "check_in_incomplete" }),
      } as unknown as ReadScoreEntryResult)
      .mockResolvedValue({
        data: scorerState(),
      } as unknown as ReadScoreEntryResult)
    const before = matchDetail({
      check_in_a_at: "2026-11-04T09:40:00.000Z",
      check_in_b_at: null,
    })
    const rerender = renderWithRerender(before)
    expect(await screen.findByText("等待雙方報到")).toBeInTheDocument()

    rerender({ ...before, check_in_b_at: "2026-11-04T09:45:00.000Z" })

    expect(await screen.findByText("可開始")).toBeInTheDocument()
    expect(screen.queryByText("等待雙方報到")).not.toBeInTheDocument()
    expect(read).toHaveBeenCalledTimes(2)
  })

  it("換到另一場：回應前不沿用上一場的面板", async () => {
    signIn()
    vi.spyOn(CompetitionService, "readScoreEntry")
      .mockResolvedValueOnce({
        data: scorerState(),
      } as unknown as ReadScoreEntryResult)
      .mockReturnValue(new Promise(() => {}) as never)
    const first = matchDetail({ status: "live" })
    const rerender = renderWithRerender(first)
    expect(await screen.findByText("比分登錄")).toBeInTheDocument()

    rerender({ ...first, id: "match-other" })

    expect(screen.getByTestId("slot")).toHaveTextContent("沒有面板")
  })
})
