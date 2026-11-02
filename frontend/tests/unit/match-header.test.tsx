import { render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { MatchHeader } from "@/features/competition/MatchHeader"
import type { PublicMatchDetail } from "@/features/competition/match-types"
import { matchDetail } from "./match-detail-fixture"

function renderHeader(detail: PublicMatchDetail) {
  render(<MatchHeader detail={detail} />)
  return screen.getByRole("banner")
}

describe("Match header", () => {
  beforeEach(() => {
    // formatMatchDateTime 與今天不同年時會加年份
    vi.useFakeTimers({ toFake: ["Date"] })
    vi.setSystemTime(new Date("2026-10-17T00:00:00Z"))
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it("三行：返回連結 → S3、「32 強 · M3」＋徽章、「特戰英豪 · BO3 · 10/18（日）13:00」", () => {
    renderHeader(matchDetail())

    const back = screen.getByRole("link", { name: "← 2026 秋季校際盃" })
    expect(back).toHaveAttribute("href", "/tournaments/t1/bracket")
    expect(back).toHaveClass("text-body", "text-muted-foreground")
    const title = screen.getByRole("heading", { level: 1 })
    expect(title).toHaveTextContent("32 強 · M3")
    expect(title).toHaveClass("text-heading-lg")
    expect(screen.getByText("待開打")).toHaveAttribute("data-tone", "muted")
    const subtitle = screen.getByText("特戰英豪 · BO3 · 10/18（日）13:00")
    expect(subtitle).toHaveClass("text-caption")
  })

  it("決賽：「決賽 · M31」", () => {
    renderHeader(matchDetail({ code: "M31", round_name: "決賽", round_no: 5 }))
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "決賽 · M31",
    )
  })

  it("季軍賽：標題只寫「季軍賽」", () => {
    renderHeader(
      matchDetail({ code: "M32", round_name: "決賽", is_third_place: true }),
    )
    const title = screen.getByRole("heading", { level: 1 })
    expect(title).toHaveTextContent(/^季軍賽$/)
  })

  it.each([
    ["live", "進行中", "live", true],
    ["appeal_window", "申訴期", "appeal", false],
    ["appealed", "申訴中", "appeal", true],
    ["confirmed", "已確認", "confirmed", false],
    ["voided", "已取消", "muted", false],
  ] as const)("%s：徽章「%s」", (status, label, tone, pulse) => {
    renderHeader(matchDetail({ status }))
    const badge = screen.getByText(label)
    expect(badge).toHaveAttribute("data-tone", tone)
    expect(badge.querySelector("[data-slot=status-badge-pulse]") !== null).toBe(
      pulse,
    )
  })
})
