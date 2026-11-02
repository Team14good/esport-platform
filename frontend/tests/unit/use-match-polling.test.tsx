import {
  focusManager,
  notifyManager,
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query"
import { act, render, renderHook } from "@testing-library/react"
import type { ReactNode } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { MatchSpectatorView } from "@/features/competition/MatchSpectatorView"
import { MatchNotFoundError } from "@/features/competition/match-source"
import type { PublicMatchDetail } from "@/features/competition/match-types"
import {
  isMatchScoreChanged,
  MATCH_POLL_INTERVAL_MS,
  useMatchPolling,
} from "@/features/competition/use-match-polling"
import { matchDetail } from "./match-detail-fixture"

function wrapper({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={new QueryClient()}>
      {children}
    </QueryClientProvider>
  )
}

function renderPolling(queryFn: () => Promise<PublicMatchDetail>) {
  return renderHook(
    () => useMatchPolling({ queryKey: ["match", "t1", "m3"], queryFn }),
    { wrapper },
  )
}

/** 推進假時鐘，並在 act 內讓請求結果與通知跑完 */
async function advance(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms)
  })
}

const LIVE_1_0 = matchDetail({
  status: "live",
  wins_a: 1,
  games: [{ game_no: 1, winner_side: "a", score_a: 13, score_b: 11 }],
})
const LIVE_2_0 = matchDetail({
  status: "live",
  wins_a: 2,
  games: [
    { game_no: 1, winner_side: "a", score_a: 13, score_b: 11 },
    { game_no: 2, winner_side: "a", score_a: 13, score_b: 7 },
  ],
  updated_at: "2026-10-18T05:00:05Z",
})

describe("場次輪詢", () => {
  beforeEach(() => {
    vi.useFakeTimers()
    // TanStack Query 預設用 setTimeout(0) 批次通知元件，在假時鐘下會晚一輪才反映；測試改用 microtask
    notifyManager.setScheduler(queueMicrotask)
    vi.setSystemTime(new Date("2026-10-18T05:00:00Z"))
  })
  afterEach(() => {
    focusManager.setFocused(undefined)
    notifyManager.setScheduler((callback) => setTimeout(callback, 0))
    vi.useRealTimers()
  })

  it("每 5 秒重抓一次", async () => {
    const queryFn = vi
      .fn<() => Promise<PublicMatchDetail>>()
      .mockResolvedValue(LIVE_1_0)
    renderPolling(queryFn)

    await advance(0)
    expect(queryFn).toHaveBeenCalledTimes(1)
    await advance(MATCH_POLL_INTERVAL_MS - 1)
    expect(queryFn).toHaveBeenCalledTimes(1)
    await advance(1)
    expect(queryFn).toHaveBeenCalledTimes(2)
  })

  it("分頁在背景時暫停，回到前景立即重抓", async () => {
    const queryFn = vi
      .fn<() => Promise<PublicMatchDetail>>()
      .mockResolvedValue(LIVE_1_0)
    renderPolling(queryFn)
    await advance(0)

    act(() => focusManager.setFocused(false))
    await advance(MATCH_POLL_INTERVAL_MS * 3)
    expect(queryFn).toHaveBeenCalledTimes(1)

    act(() => focusManager.setFocused(true))
    await advance(0)
    expect(queryFn).toHaveBeenCalledTimes(2)
  })

  it("重抓時保留舊資料、不回到 loading", async () => {
    const queryFn = vi
      .fn<() => Promise<PublicMatchDetail>>()
      .mockResolvedValueOnce(LIVE_1_0)
      .mockReturnValue(new Promise<never>(() => {}))
    const { result } = renderPolling(queryFn)
    await advance(0)

    await advance(MATCH_POLL_INTERVAL_MS)
    expect(queryFn).toHaveBeenCalledTimes(2)
    expect(result.current.detail).toEqual(LIVE_1_0)
    expect(result.current.isLoading).toBe(false)
  })

  it("比分 1:0 → 2:0：更新比分並標記 changed；內容相同的下一份不改變", async () => {
    const queryFn = vi
      .fn<() => Promise<PublicMatchDetail>>()
      .mockResolvedValueOnce(LIVE_1_0)
      .mockResolvedValueOnce(LIVE_2_0)
      .mockResolvedValue(structuredClone(LIVE_2_0))
    const { result } = renderPolling(queryFn)

    await advance(0)
    expect(result.current.changed).toBe(false)

    await advance(MATCH_POLL_INTERVAL_MS)
    expect(result.current.detail?.wins_a).toBe(2)
    expect(result.current.changed).toBe(true)
    const detail = result.current.detail

    // structural sharing：內容相同時沿用同一份資料，不會再 flash
    await advance(MATCH_POLL_INTERVAL_MS)
    expect(queryFn).toHaveBeenCalledTimes(3)
    expect(result.current.detail).toBe(detail)
  })

  it("只有各局以外的欄位變動（例如更新時間）：changed 為 false", async () => {
    const queryFn = vi
      .fn<() => Promise<PublicMatchDetail>>()
      .mockResolvedValueOnce(LIVE_1_0)
      .mockResolvedValue({ ...LIVE_1_0, updated_at: "2026-10-18T05:00:09Z" })
    const { result } = renderPolling(queryFn)
    await advance(0)
    await advance(MATCH_POLL_INTERVAL_MS)
    expect(result.current.detail?.updated_at).toBe("2026-10-18T05:00:09Z")
    expect(result.current.changed).toBe(false)
  })

  it("連續 3 次失敗才顯示連線中斷，保留舊畫面；成功一次就消失", async () => {
    const fail = () => Promise.reject(new Error("network"))
    const queryFn = vi
      .fn<() => Promise<PublicMatchDetail>>()
      .mockResolvedValueOnce(LIVE_1_0)
      .mockImplementationOnce(fail)
      .mockImplementationOnce(fail)
      .mockImplementationOnce(fail)
      .mockResolvedValue(LIVE_1_0)
    const { result } = renderPolling(queryFn)
    await advance(0)

    await advance(MATCH_POLL_INTERVAL_MS * 2)
    expect(result.current.connectionLost).toBe(false)
    await advance(MATCH_POLL_INTERVAL_MS)
    expect(result.current.connectionLost).toBe(true)
    expect(result.current.detail).toEqual(LIVE_1_0)
    expect(result.current.lastUpdatedAt?.toISOString()).toBe(
      "2026-10-18T05:00:00.000Z",
    )

    await advance(MATCH_POLL_INTERVAL_MS)
    expect(result.current.connectionLost).toBe(false)
  })

  it("找不到場次：notFound，並停止定時重抓", async () => {
    const queryFn = vi
      .fn<() => Promise<PublicMatchDetail>>()
      .mockRejectedValue(new MatchNotFoundError())
    const { result } = renderPolling(queryFn)
    await advance(0)

    expect(result.current.notFound).toBe(true)
    expect(result.current.isLoading).toBe(false)
    expect(result.current.error).toBeNull()
    await advance(MATCH_POLL_INTERVAL_MS * 3)
    expect(queryFn).toHaveBeenCalledTimes(1)
  })

  it("其他錯誤不算找不到場次", async () => {
    const queryFn = vi
      .fn<() => Promise<PublicMatchDetail>>()
      .mockRejectedValue(new Error("network"))
    const { result } = renderPolling(queryFn)
    await advance(0)

    expect(result.current.notFound).toBe(false)
    expect(result.current.error).toBeInstanceOf(Error)
  })
})

describe("比分變動的判斷", () => {
  const CONFIRMED_2_0 = matchDetail({
    ...LIVE_2_0,
    status: "confirmed",
    outcome: "played",
    winner_id: "team-a",
  })

  it("更正結果時只改結果、勝隊或某一局比分，也算變動", () => {
    expect(
      isMatchScoreChanged(CONFIRMED_2_0, {
        ...CONFIRMED_2_0,
        outcome: "disqualified",
      }),
    ).toBe(true)
    expect(
      isMatchScoreChanged(CONFIRMED_2_0, {
        ...CONFIRMED_2_0,
        winner_id: "team-b",
      }),
    ).toBe(true)
    expect(
      isMatchScoreChanged(CONFIRMED_2_0, {
        ...CONFIRMED_2_0,
        games: [
          CONFIRMED_2_0.games[0],
          { ...CONFIRMED_2_0.games[1], score_b: 9 },
        ],
      }),
    ).toBe(true)
  })

  it("各局內容相同但是不同的物件：不算變動", () => {
    expect(
      isMatchScoreChanged(CONFIRMED_2_0, {
        ...CONFIRMED_2_0,
        games: CONFIRMED_2_0.games.map((game) => ({ ...game })),
      }),
    ).toBe(false)
  })
})

describe("場次頁的 flash", () => {
  function scoreDisplay() {
    return document.querySelector("[data-slot=score-display]")!
  }

  it("第一次顯示不 flash；比分變動時 flash，連續兩次變動會重新掛載讓動畫重播", () => {
    const { rerender } = render(<MatchSpectatorView detail={LIVE_1_0} />)
    expect(scoreDisplay()).not.toHaveClass("update-flash")

    rerender(<MatchSpectatorView detail={LIVE_2_0} changed />)
    const first = scoreDisplay()
    expect(first).toHaveClass("update-flash")

    // 同一份資料重新渲染：不重新掛載
    rerender(<MatchSpectatorView detail={LIVE_2_0} changed />)
    expect(scoreDisplay()).toBe(first)

    const next = { ...LIVE_2_0, status: "appeal_window" as const }
    rerender(<MatchSpectatorView detail={next} changed />)
    expect(scoreDisplay()).not.toBe(first)
    expect(scoreDisplay()).toHaveClass("update-flash")
  })
})
