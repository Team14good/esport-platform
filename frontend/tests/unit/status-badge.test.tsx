import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { StatusBadge, type StatusTone } from "@/components/common/StatusBadge"
import { APPLICATION_STATUS_BADGES } from "@/features/identity/organizer-application"

describe("Status badge", () => {
  it.each<[StatusTone, string]>([
    ["live", "status-live"],
    ["appeal", "status-appeal"],
    ["confirmed", "status-confirmed"],
    ["waitlist", "status-waitlist"],
    ["eliminated", "status-eliminated"],
    ["brand", "brand"],
    ["destructive", "destructive"],
    ["muted", "muted-foreground"],
  ])("tone %s：文字為該色、底色 15%、外框 38%，藥丸形", (tone, color) => {
    render(<StatusBadge tone={tone}>狀態</StatusBadge>)

    const badge = screen.getByText("狀態")
    expect(badge).toHaveAttribute("data-tone", tone)
    expect(badge).toHaveClass(
      `text-${color}`,
      `bg-${color}/15`,
      `border-${color}/38`,
      "rounded-full",
      "border",
      "text-label",
    )
  })

  it("預設沒有脈動點", () => {
    render(<StatusBadge tone="appeal">申訴期</StatusBadge>)

    expect(
      screen
        .getByText("申訴期")
        .querySelector("[data-slot=status-badge-pulse]"),
    ).toBeNull()
  })

  it("pulse：文字前有 6px 脈動圓點，對輔助技術隱藏，減少動態時不動", () => {
    render(
      <StatusBadge tone="live" pulse>
        進行中
      </StatusBadge>,
    )

    const badge = screen.getByText("進行中")
    const dot = badge.querySelector("[data-slot=status-badge-pulse]")
    expect(dot).not.toBeNull()
    expect(badge.firstChild).toBe(dot)
    expect(dot).toHaveAttribute("aria-hidden", "true")
    expect(dot).toHaveClass(
      "size-1.5",
      "rounded-full",
      "animate-pulse",
      "motion-reduce:animate-none",
    )
    expect(badge).toHaveTextContent(/^進行中$/)
  })
})

describe("主辦方申請的狀態對照", () => {
  it("待審核 appeal、核准 confirmed、退回 destructive", () => {
    expect(APPLICATION_STATUS_BADGES).toEqual({
      pending: { label: "待審核", tone: "appeal" },
      approved: { label: "核准", tone: "confirmed" },
      rejected: { label: "退回", tone: "destructive" },
    })
  })
})
