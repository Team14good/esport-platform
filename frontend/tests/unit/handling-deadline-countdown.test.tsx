import { act, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import {
  Countdown,
  EXPIRE_POLL_TIMEOUT_MS,
  EXPIRE_TIMEOUT_TEXT,
  EXPIRED_TEXT,
  PAUSED_TEXT,
  PausedCountdown,
} from "@/components/common/Countdown"
import {
  HANDLING_OVERDUE_TEXT,
  HandlingDeadlineCountdown,
  handlingDeadlineVariant,
} from "@/features/disputes/HandlingDeadlineCountdown"

// 台北 2025/10/18（六）19:00
const DEADLINE = "2025-10-18T11:00:00Z"
const DEADLINE_MS = new Date(DEADLINE).getTime()
const SECOND = 1000
const MINUTE = 60 * SECOND
const HOUR = 60 * MINUTE

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

describe("申訴處理期限倒數（S27、S32）", () => {
  it.each([
    [2 * HOUR, "muted"],
    [HOUR + SECOND, "muted"],
    [HOUR, "destructive"],
    [5 * MINUTE, "destructive"],
  ] as const)("剩 %i 毫秒 → %s", (remaining, variant) => {
    expect(handlingDeadlineVariant(remaining)).toBe(variant)
  })

  it("剩餘超過 1 小時為 muted，進入最後 1 小時改為 destructive", () => {
    setRemaining(HOUR + 2 * SECOND)
    render(<HandlingDeadlineCountdown deadline={DEADLINE} />)

    expect(screen.getByText("處理期限")).toBeInTheDocument()
    expect(countdownRoot()).toHaveAttribute("data-variant", "muted")
    expect(screen.getByRole("timer")).toHaveClass("text-muted-foreground")

    advance(3 * SECOND)
    expect(countdownRoot()).toHaveAttribute("data-variant", "destructive")
    expect(screen.getByRole("timer")).toHaveClass("text-destructive")
    expect(screen.getByRole("timer")).toHaveTextContent("59:59")
  })

  it("過了處理期限：顯示「已超過處理期限」（destructive），不寫系統處理中、不重抓", () => {
    setRemaining(2 * SECOND)
    render(<HandlingDeadlineCountdown deadline={DEADLINE} />)

    advance(3 * SECOND)
    const status = screen.getByRole("status")
    expect(status).toHaveTextContent(HANDLING_OVERDUE_TEXT)
    expect(status).toHaveClass("text-destructive")
    expect(status.querySelector(".animate-spin")).toBeNull()
    expect(screen.queryByText(EXPIRED_TEXT)).toBeNull()
    expect(screen.queryByRole("timer")).toBeNull()
    expect(countdownRoot()).toHaveAttribute("data-variant", "destructive")

    // 2 分鐘後也不改成逾時提示
    advance(EXPIRE_POLL_TIMEOUT_MS + 5 * SECOND)
    expect(screen.getByRole("status")).toHaveTextContent(HANDLING_OVERDUE_TEXT)
    expect(screen.queryByText(EXPIRE_TIMEOUT_TEXT)).toBeNull()
  })

  it("一開始就已過期也直接顯示「已超過處理期限」", () => {
    setRemaining(-HOUR)
    render(<HandlingDeadlineCountdown deadline={DEADLINE} label="剩餘時間" />)

    expect(screen.getByText("剩餘時間")).toBeInTheDocument()
    expect(screen.getByRole("status")).toHaveTextContent(HANDLING_OVERDUE_TEXT)
    expect(screen.getByText("10/18（六）19:00 截止")).toBeInTheDocument()
  })
})

describe("PausedCountdown", () => {
  it("說明文字＋「計時暫停」，沒有數字", () => {
    render(<PausedCountdown label="報到與棄權倒數" />)

    expect(screen.getByText("報到與棄權倒數")).toBeInTheDocument()
    expect(screen.getByText(PAUSED_TEXT)).toBeInTheDocument()
    expect(screen.queryByRole("timer")).toBeNull()
    expect(countdownRoot()).toHaveAttribute("data-variant", "paused")
  })
})

describe("Countdown expiredVariant", () => {
  it("到期後不呼叫 onExpire（系統不會自動處理，不必重抓）", () => {
    setRemaining(2 * SECOND)
    const onExpire = vi.fn()
    render(
      <Countdown
        label="處理期限"
        deadline={DEADLINE}
        expiredText={HANDLING_OVERDUE_TEXT}
        expiredVariant="destructive"
        onExpire={onExpire}
      />,
    )

    advance(2 * SECOND + 10 * SECOND)
    expect(screen.getByRole("status")).toHaveTextContent(HANDLING_OVERDUE_TEXT)
    expect(onExpire).not.toHaveBeenCalled()
  })
})
