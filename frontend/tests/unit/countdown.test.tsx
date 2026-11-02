import { act, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import {
  Countdown,
  EXPIRE_TIMEOUT_TEXT,
  EXPIRED_TEXT,
  formatRemaining,
} from "@/components/common/Countdown"

// 台北 2025/10/18（六）19:00
const DEADLINE = "2025-10-18T11:00:00Z"
const DEADLINE_MS = new Date(DEADLINE).getTime()
const SECOND = 1000
const MINUTE = 60 * SECOND
const HOUR = 60 * MINUTE
const DAY = 24 * HOUR

/** 把裝置時間設在截止前 remainingMs。 */
function setRemaining(remainingMs: number) {
  vi.setSystemTime(new Date(DEADLINE_MS - remainingMs))
}

function advance(ms: number) {
  act(() => {
    vi.advanceTimersByTime(ms)
  })
}

function countdownRoot() {
  const root = document.querySelector("[data-slot=countdown]")
  if (!root) throw new Error("找不到倒數")
  return root
}

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

describe("formatRemaining", () => {
  it.each([
    [2 * DAY + 5 * HOUR + 30 * MINUTE, "剩 2 天 5 小時"],
    [DAY, "剩 1 天 0 小時"],
    [DAY - SECOND, "剩 23 小時 59 分"],
    [5 * HOUR + 12 * MINUTE + 40 * SECOND, "剩 5 小時 12 分"],
    [HOUR, "剩 1 小時 0 分"],
    [HOUR - SECOND, "59:59"],
    [59 * MINUTE + 30 * SECOND, "59:30"],
    [5 * SECOND, "00:05"],
    // 不足一秒時進位，歸零那一刻才顯示 00:00
    [400, "00:01"],
    [0, "00:00"],
    [-5 * SECOND, "00:00"],
  ])("剩 %i 毫秒 → %s", (remaining, expected) => {
    expect(formatRemaining(remaining)).toBe(expected)
  })
})

describe("Countdown", () => {
  it("說明文字＋數字，下方「{絕對時間} 截止」；muted 沒有進度條", () => {
    setRemaining(2 * DAY + 5 * HOUR)
    render(<Countdown label="報名截止" deadline={DEADLINE} />)

    expect(screen.getByText("報名截止")).toBeInTheDocument()
    expect(screen.getByRole("timer")).toHaveTextContent("剩 2 天 5 小時")
    expect(screen.getByText("10/18（六）19:00 截止")).toBeInTheDocument()
    expect(countdownRoot()).toHaveAttribute("data-variant", "muted")
    expect(screen.queryByTestId("countdown-bar")).toBeNull()
  })

  it.each([
    ["muted", "text-muted-foreground"],
    ["live", "text-status-live"],
    ["appeal", "text-status-appeal"],
    ["destructive", "text-destructive"],
  ] as const)("變體 %s 的數字顏色為 %s", (variant, className) => {
    setRemaining(30 * MINUTE)
    render(<Countdown label="倒數" deadline={DEADLINE} variant={variant} />)

    expect(screen.getByRole("timer")).toHaveClass(className)
    // 只有 appeal 有進度條
    if (variant === "appeal") {
      expect(screen.getByTestId("countdown-bar")).toBeInTheDocument()
    } else {
      expect(screen.queryByTestId("countdown-bar")).toBeNull()
    }
  })

  it("appeal 進度條依起點到截止的剩餘比例縮短", () => {
    setRemaining(15 * MINUTE)
    render(
      <Countdown
        label="申訴期"
        deadline={DEADLINE}
        startsAt={new Date(DEADLINE_MS - 30 * MINUTE).toISOString()}
        variant="appeal"
      />,
    )

    const fill = screen.getByTestId("countdown-bar").firstElementChild
    expect(fill).toHaveStyle({ width: "50%" })
  })

  it("appeal 沒有傳 startsAt：以截止前 24 小時為起點（剩 12 小時為 50%）", () => {
    setRemaining(12 * HOUR)
    render(<Countdown label="報名截止" deadline={DEADLINE} variant="appeal" />)

    const fill = screen.getByTestId("countdown-bar").firstElementChild
    expect(fill).toHaveStyle({ width: "50%" })
  })

  it("後綴可由呼叫端指定：「{絕對時間} 開放報名」", () => {
    setRemaining(2 * DAY)
    render(<Countdown label="報名開始" deadline={DEADLINE} suffix="開放報名" />)

    expect(screen.getByText("10/18（六）19:00 開放報名")).toBeInTheDocument()
    expect(screen.queryByText(/截止/)).toBeNull()
  })

  it("variant 傳函式時依剩餘時間決定：跨過門檻後換變體", () => {
    setRemaining(DAY + 2 * SECOND)
    render(
      <Countdown
        label="報名截止"
        deadline={DEADLINE}
        variant={(remaining) => (remaining <= DAY ? "appeal" : "muted")}
      />,
    )
    expect(countdownRoot()).toHaveAttribute("data-variant", "muted")

    advance(3 * SECOND)

    expect(countdownRoot()).toHaveAttribute("data-variant", "appeal")
    expect(screen.getByRole("timer")).toHaveTextContent("剩 23 小時 59 分")
  })

  it("未滿 1 小時：mm:ss 每秒跳動", () => {
    setRemaining(59 * MINUTE + 30 * SECOND)
    render(<Countdown label="報到開放" deadline={DEADLINE} />)
    expect(screen.getByRole("timer")).toHaveTextContent("59:30")

    advance(SECOND)
    expect(screen.getByRole("timer")).toHaveTextContent("59:29")

    advance(SECOND)
    expect(screen.getByRole("timer")).toHaveTextContent("59:28")
  })

  it("歸零：顯示「已截止 · 系統處理中」，立即並每 5 秒呼叫 onExpire；2 分鐘後停止並顯示提示", () => {
    setRemaining(2 * SECOND)
    const onExpire = vi.fn()
    render(
      <Countdown
        label="報名截止"
        deadline={DEADLINE}
        variant="appeal"
        onExpire={onExpire}
      />,
    )
    expect(onExpire).not.toHaveBeenCalled()

    advance(2 * SECOND)

    expect(screen.queryByRole("timer")).toBeNull()
    expect(screen.getByRole("status")).toHaveTextContent(EXPIRED_TEXT)
    expect(screen.queryByTestId("countdown-bar")).toBeNull()
    expect(onExpire).toHaveBeenCalledTimes(1)

    advance(5 * SECOND)
    expect(onExpire).toHaveBeenCalledTimes(2)

    advance(5 * SECOND)
    expect(onExpire).toHaveBeenCalledTimes(3)

    // 歸零後滿 2 分鐘：不再重抓，改顯示提示
    advance(2 * MINUTE - 10 * SECOND)
    const calls = onExpire.mock.calls.length
    expect(screen.getByRole("status")).toHaveTextContent(EXPIRE_TIMEOUT_TEXT)
    expect(screen.getByRole("status")).not.toHaveTextContent(EXPIRED_TEXT)

    advance(MINUTE)
    expect(onExpire).toHaveBeenCalledTimes(calls)
    expect(calls).toBeLessThanOrEqual(25)
  })

  it("deadline 改變時重設「已截止」與 2 分鐘逾時", () => {
    setRemaining(SECOND)
    const onExpire = vi.fn()
    const { rerender } = render(
      <Countdown label="報名截止" deadline={DEADLINE} onExpire={onExpire} />,
    )
    advance(SECOND)
    advance(2 * MINUTE)
    expect(screen.getByRole("status")).toHaveTextContent(EXPIRE_TIMEOUT_TEXT)

    const later = new Date(DEADLINE_MS + 2 * MINUTE + 30 * SECOND).toISOString()
    // 用 variant 函式記下每次 render 算出的剩餘時間
    const rendered: number[] = []
    rerender(
      <Countdown
        label="報名截止"
        deadline={later}
        onExpire={onExpire}
        variant={(remaining) => {
          rendered.push(remaining)
          return "muted"
        }}
      />,
    )

    // 換了目標時間後立即以目前時間計算，不閃現停止當下的剩餘時間（2:30）
    expect(rendered.length).toBeGreaterThan(0)
    expect(rendered.every((remaining) => remaining <= 30 * SECOND)).toBe(true)
    expect(screen.getByRole("status")).toBeEmptyDOMElement()
    expect(screen.getByRole("timer")).toHaveTextContent("00:30")
    const calls = onExpire.mock.calls.length

    // 新的目標時間歸零：重新顯示「系統處理中」並重新開始重抓與計時
    advance(30 * SECOND)
    expect(screen.getByRole("status")).toHaveTextContent(EXPIRED_TEXT)
    expect(onExpire).toHaveBeenCalledTimes(calls + 1)
  })

  it("歸零文字可由呼叫端指定", () => {
    setRemaining(SECOND)
    render(
      <Countdown
        label="報名開始"
        deadline={DEADLINE}
        expiredText="報名開放中 · 系統處理中"
      />,
    )
    advance(SECOND)

    expect(screen.getByRole("status")).toHaveTextContent(
      "報名開放中 · 系統處理中",
    )
    expect(screen.queryByText(EXPIRED_TEXT)).toBeNull()
  })

  it("歸零前後是同一個 live region（只換內容）", () => {
    setRemaining(SECOND)
    render(<Countdown label="報名截止" deadline={DEADLINE} />)
    const region = screen.getByRole("status")
    expect(region).toBeEmptyDOMElement()

    advance(SECOND)

    expect(screen.getByRole("status")).toBe(region)
    expect(region).toHaveTextContent(EXPIRED_TEXT)
  })

  it("開啟頁面時已過期：直接顯示「已截止 · 系統處理中」並開始重抓", () => {
    setRemaining(-10 * SECOND)
    const onExpire = vi.fn()
    render(
      <Countdown label="報名開始" deadline={DEADLINE} onExpire={onExpire} />,
    )

    expect(screen.getByRole("status")).toHaveTextContent(EXPIRED_TEXT)
    expect(onExpire).toHaveBeenCalledTimes(1)
  })

  it("時間格式錯誤時不顯示", () => {
    const { container } = render(
      <Countdown label="報名截止" deadline="not-a-date" />,
    )
    expect(container).toBeEmptyDOMElement()
  })
})
