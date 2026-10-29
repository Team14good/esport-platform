import {
  focusManager,
  notifyManager,
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query"
import { act, renderHook } from "@testing-library/react"
import type { ReactNode } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import {
  createBracketFixture,
  simulateBracketChange,
} from "@/features/competition/bracket-fixtures"
import type { PublicBracket } from "@/features/competition/bracket-types"
import {
  BRACKET_POLL_INTERVAL_MS,
  diffBracketMatches,
  useBracketPolling,
} from "@/features/competition/use-bracket-polling"

function renderPolling(queryFn: () => Promise<PublicBracket>) {
  const client = new QueryClient()
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  return renderHook(
    () => useBracketPolling({ queryKey: ["bracket", "t1"], queryFn }),
    { wrapper },
  )
}

/** 推進假時鐘，並在 act 內讓請求結果與通知跑完 */
async function advance(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms)
  })
}

describe("對戰樹輪詢", () => {
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
      .fn<() => Promise<PublicBracket>>()
      .mockResolvedValue(createBracketFixture({ teamCount: 8 }))
    renderPolling(queryFn)

    await advance(0)
    expect(queryFn).toHaveBeenCalledTimes(1)
    await advance(BRACKET_POLL_INTERVAL_MS - 1)
    expect(queryFn).toHaveBeenCalledTimes(1)
    await advance(1)
    expect(queryFn).toHaveBeenCalledTimes(2)
    await advance(BRACKET_POLL_INTERVAL_MS)
    expect(queryFn).toHaveBeenCalledTimes(3)
  })

  it("分頁在背景時暫停，回到前景立即重抓", async () => {
    const queryFn = vi
      .fn<() => Promise<PublicBracket>>()
      .mockResolvedValue(createBracketFixture({ teamCount: 8 }))
    renderPolling(queryFn)
    await advance(0)

    act(() => focusManager.setFocused(false))
    await advance(BRACKET_POLL_INTERVAL_MS * 3)
    expect(queryFn).toHaveBeenCalledTimes(1)

    act(() => focusManager.setFocused(true))
    await advance(0)
    expect(queryFn).toHaveBeenCalledTimes(2)
  })

  it("重抓時保留舊資料、不回到 loading", async () => {
    const bracket = createBracketFixture({ teamCount: 8 })
    const queryFn = vi
      .fn<() => Promise<PublicBracket>>()
      .mockResolvedValueOnce(bracket)
      .mockReturnValue(new Promise<never>(() => {}))
    const { result } = renderPolling(queryFn)
    await advance(0)

    await advance(BRACKET_POLL_INTERVAL_MS)
    expect(queryFn).toHaveBeenCalledTimes(2)
    expect(result.current.bracket).toEqual(bracket)
    expect(result.current.isLoading).toBe(false)
  })

  it("連續 3 次失敗才顯示連線中斷，成功一次就恢復", async () => {
    const bracket = createBracketFixture({ teamCount: 8 })
    const fail = () => Promise.reject(new Error("network"))
    const queryFn = vi
      .fn<() => Promise<PublicBracket>>()
      .mockResolvedValueOnce(bracket)
      .mockImplementationOnce(fail)
      .mockImplementationOnce(fail)
      .mockImplementationOnce(fail)
      .mockResolvedValue(bracket)
    const { result } = renderPolling(queryFn)
    await advance(0)
    const firstSuccess = result.current.lastUpdatedAt

    await advance(BRACKET_POLL_INTERVAL_MS)
    expect(result.current.connectionLost).toBe(false)
    await advance(BRACKET_POLL_INTERVAL_MS)
    expect(result.current.connectionLost).toBe(false)
    await advance(BRACKET_POLL_INTERVAL_MS)
    expect(result.current.connectionLost).toBe(true)
    // 保留舊對戰樹與最後成功的時間
    expect(result.current.bracket).toEqual(bracket)
    expect(result.current.lastUpdatedAt).toEqual(firstSuccess)
    expect(result.current.lastUpdatedAt?.toISOString()).toBe(
      "2026-10-18T05:00:00.000Z",
    )

    await advance(BRACKET_POLL_INTERVAL_MS)
    expect(result.current.connectionLost).toBe(false)
  })

  it("失敗兩次後成功，計數歸零：之後再失敗兩次也不顯示", async () => {
    const bracket = createBracketFixture({ teamCount: 8 })
    const fail = () => Promise.reject(new Error("network"))
    const queryFn = vi
      .fn<() => Promise<PublicBracket>>()
      .mockResolvedValueOnce(bracket)
      .mockImplementationOnce(fail)
      .mockImplementationOnce(fail)
      .mockResolvedValueOnce(bracket)
      .mockImplementation(fail)
    const { result } = renderPolling(queryFn)
    await advance(0)

    await advance(BRACKET_POLL_INTERVAL_MS * 5)
    expect(queryFn).toHaveBeenCalledTimes(6)
    expect(result.current.connectionLost).toBe(false)
    await advance(BRACKET_POLL_INTERVAL_MS)
    expect(result.current.connectionLost).toBe(true)
  })

  it("第一次載入不 flash；之後只有變動的場次在 changedMatchIds", async () => {
    const before = createBracketFixture({
      teamCount: 8,
      scenario: "in_progress",
    })
    const after = simulateBracketChange(before)
    const live = before.matches.find((m) => m.status === "live")!
    const queryFn = vi
      .fn<() => Promise<PublicBracket>>()
      .mockResolvedValueOnce(before)
      .mockResolvedValueOnce(after)
      .mockResolvedValue(structuredClone(after))
    const { result } = renderPolling(queryFn)

    await advance(0)
    expect(result.current.bracket).toEqual(before)
    expect(result.current.changedMatchIds.size).toBe(0)

    await advance(BRACKET_POLL_INTERVAL_MS)
    expect([...result.current.changedMatchIds]).toEqual([live.id])

    // 內容相同的資料：沿用同一個 Set，卡片不會再 flash
    const changed = result.current.changedMatchIds
    await advance(BRACKET_POLL_INTERVAL_MS)
    expect(queryFn).toHaveBeenCalledTimes(3)
    expect(result.current.changedMatchIds).toBe(changed)
  })
})

describe("逐場比較", () => {
  const base = createBracketFixture({ teamCount: 8, scenario: "in_progress" })

  it.each([
    ["status", { status: "live" }],
    ["outcome", { outcome: "forfeit" }],
    ["隊伍", { team_a: { id: "x", name: "新隊伍" } }],
    ["比分", { wins_b: 2 }],
    ["時間", { scheduled_at: "2026-10-19T05:00:00Z" }],
    ["來源", { source_a: "M9 勝者" }],
  ] as const)("%s 改變時列入變動", (_, patch) => {
    const next = {
      ...base,
      matches: base.matches.map((m, i) => (i === 0 ? { ...m, ...patch } : m)),
    }

    expect([...diffBracketMatches(base, next)]).toEqual([base.matches[0].id])
  })

  it("沒有變動時回傳空集合", () => {
    expect(diffBracketMatches(base, structuredClone(base)).size).toBe(0)
  })
})
