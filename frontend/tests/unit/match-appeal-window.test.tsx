import { render, screen, within } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { createBracketFixture } from "@/features/competition/bracket-fixtures"
import type { MatchStatus } from "@/features/competition/bracket-types"
import { MatchAppealWindow } from "@/features/competition/MatchAppealWindow"
import { MatchSpectatorView } from "@/features/competition/MatchSpectatorView"
import { matchDetailFromBracket } from "@/features/competition/match-fixtures"
import { matchDetail, publicMatch } from "./match-detail-fixture"
import { renderInRouter } from "./render-router"

// 台北時間 2026/10/18（日）14:22
const DEADLINE = "2026-10-18T06:22:00Z"

function appealRegion() {
  return screen.queryByRole("region", { name: "申訴期" })
}

describe("申訴期區塊", () => {
  beforeEach(() => {
    // formatMatchDateTime 與今天不同年時會加年份
    vi.useFakeTimers({ toFake: ["Date"] })
    vi.setSystemTime(new Date("2026-10-17T00:00:00Z"))
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it("申訴期：顯示「申訴期」與「10/18（日）14:22 截止」，沒有倒數時不留插槽", () => {
    render(
      <MatchAppealWindow
        detail={{ status: "appeal_window", appeal_deadline: DEADLINE }}
      />,
    )

    const region = appealRegion()
    expect(region).not.toBeNull()
    expect(region).toHaveAttribute("data-slot", "match-appeal-window")
    // 放在 Card 裡
    expect(region?.className).toContain("bg-card")
    const title = screen.getByRole("heading", { level: 2, name: "申訴期" })
    expect(title).toHaveClass("text-label", "text-status-appeal")
    const deadline = screen.getByText("10/18（日）14:22 截止")
    expect(deadline).toHaveClass("text-caption", "text-muted-foreground")
    expect(
      region?.querySelector("[data-slot=appeal-countdown]") ?? null,
    ).toBeNull()
    // 標題後直接是截止時間，中間沒有空白元素
    expect(title.nextElementSibling).toBe(deadline)
  })

  it("申訴中：同樣顯示申訴期與截止時間", () => {
    render(
      <MatchAppealWindow
        detail={{ status: "appealed", appeal_deadline: DEADLINE }}
      />,
    )

    expect(appealRegion()).not.toBeNull()
    expect(screen.getByText("10/18（日）14:22 截止")).toBeInTheDocument()
  })

  it("有倒數插槽：插槽在標題與截止時間之間", () => {
    render(
      <MatchAppealWindow
        detail={{ status: "appeal_window", appeal_deadline: DEADLINE }}
        countdown={<span>剩 1:22:00</span>}
      />,
    )

    const title = screen.getByRole("heading", { name: "申訴期" })
    const slot = screen.getByText("剩 1:22:00").parentElement
    expect(slot).toHaveAttribute("data-slot", "appeal-countdown")
    expect(title.nextElementSibling).toBe(slot)
    expect(slot?.nextElementSibling).toHaveTextContent("10/18（日）14:22 截止")
  })

  it.each<MatchStatus>(["scheduled", "live", "confirmed", "voided"])(
    "其他狀態（%s）：即使有截止時間也不顯示",
    (status) => {
      const { container } = render(
        <MatchAppealWindow detail={{ status, appeal_deadline: DEADLINE }} />,
      )
      expect(container).toBeEmptyDOMElement()
    },
  )

  it("缺截止時間：申訴期但 appeal_deadline 為 null 時不顯示", () => {
    const { container } = render(
      <MatchAppealWindow
        detail={{ status: "appeal_window", appeal_deadline: null }}
        countdown={<span>剩 1:22:00</span>}
      />,
    )
    expect(container).toBeEmptyDOMElement()
  })
})

describe("場次頁的申訴期位置", () => {
  // 申訴期、有已登錄的局與同輪場次，四個區塊都會出現
  const detail = matchDetail({
    status: "appeal_window",
    outcome: "played",
    winner_id: "team-a",
    wins_a: 2,
    wins_b: 0,
    games: [
      { game_no: 1, winner_side: "a", score_a: 13, score_b: 7 },
      { game_no: 2, winner_side: "a", score_a: 13, score_b: 11 },
    ],
    same_round: [publicMatch({ id: "match-M4", code: "M4" })],
    appeal_deadline: DEADLINE,
  })

  function block(slot: string) {
    const el = document.querySelector<HTMLElement>(`[data-slot=${slot}]`)
    if (el === null) throw new Error(`找不到 ${slot}`)
    return el
  }

  /** `< lg` 的 order class（max-lg:order-N） */
  function mobileOrder(el: HTMLElement) {
    const match = el.className.match(/(?:^|\s)max-lg:order-(\d+)(?:\s|$)/)
    if (match === null) throw new Error(`${el.dataset.slot} 沒有 order`)
    return Number(match[1])
  }

  it("手機：兩欄容器是 display: contents，順序為 Score display → 申訴期 → 各局 → 同輪", async () => {
    await renderInRouter(<MatchSpectatorView detail={detail} />)
    await screen.findByRole("heading", { name: "申訴期" })

    // 兩欄容器在 < lg 不產生方框，四個區塊直接排進外層單欄 grid
    const main = block("match-main")
    const aside = block("match-aside")
    for (const column of [main, aside]) {
      expect(column).toHaveClass("contents", "lg:flex", "lg:flex-col")
      expect(column.parentElement).toHaveClass("grid", "grid-cols-1")
    }
    const slots = [
      "score-display",
      "game-list",
      "match-appeal-window",
      "same-round-matches",
    ]
    const ordered = slots
      .map((slot) => block(slot))
      .sort((a, b) => mobileOrder(a) - mobileOrder(b))
      .map((el) => el.dataset.slot)
    expect(ordered).toEqual([
      "score-display",
      "match-appeal-window",
      "game-list",
      "same-round-matches",
    ])
    // 頁首在外層，排在所有區塊之前
    const header = block("match-header")
    expect(header.nextElementSibling).toBe(main.parentElement)
  })

  it("桌機：右欄最上方是申訴期、下方是同輪其他場次；左欄是 Score display 與各局", async () => {
    await renderInRouter(<MatchSpectatorView detail={detail} />)
    await screen.findByRole("heading", { name: "申訴期" })

    const main = block("match-main")
    const aside = block("match-aside")
    expect(main.parentElement).toHaveClass(
      "lg:grid-cols-[minmax(0,1fr)_var(--spacing-match-aside-width)]",
    )
    expect(
      Array.from(main.children).map((el) => (el as HTMLElement).dataset.slot),
    ).toEqual(["score-display", "game-list"])
    expect(
      Array.from(aside.children).map((el) => (el as HTMLElement).dataset.slot),
    ).toEqual(["match-appeal-window", "same-round-matches"])
    // 每個區塊只渲染一次
    expect(screen.getAllByRole("region", { name: "申訴期" })).toHaveLength(1)
  })

  it("倒數插槽由 appealCountdown 傳入申訴期區塊", async () => {
    await renderInRouter(
      <MatchSpectatorView
        detail={detail}
        appealCountdown={<span>剩 1:22:00</span>}
      />,
    )
    const region = await screen.findByRole("region", { name: "申訴期" })
    expect(within(region).getByText("剩 1:22:00")).toBeInTheDocument()
  })

  it("已確認的場次不顯示申訴期，其他區塊不受影響", async () => {
    await renderInRouter(
      <MatchSpectatorView
        detail={{ ...detail, status: "confirmed", appeal_deadline: null }}
      />,
    )
    await screen.findByRole("heading", { name: "同輪其他場次" })
    expect(appealRegion()).toBeNull()
    expect(block("match-aside").children).toHaveLength(1)
  })
})

describe("假資料的申訴截止時間", () => {
  const bracket = createBracketFixture({
    teamCount: 32,
    scenario: "in_progress",
  })

  it("申訴期與申訴中的場次為預定時間加 2 小時，其他狀態為 null", () => {
    let appealCount = 0
    for (const match of bracket.matches) {
      const detail = matchDetailFromBracket(bracket, match.id)
      if (match.status === "appeal_window" || match.status === "appealed") {
        appealCount += 1
        expect(detail?.appeal_deadline).toBe(
          new Date(
            Date.parse(match.scheduled_at) + 2 * 60 * 60 * 1000,
          ).toISOString(),
        )
      } else {
        expect(detail?.appeal_deadline).toBeNull()
      }
    }
    // 申訴期、申訴中兩種都有
    expect(bracket.matches.some((m) => m.status === "appeal_window")).toBe(true)
    expect(bracket.matches.some((m) => m.status === "appealed")).toBe(true)
    expect(appealCount).toBeGreaterThan(0)
  })
})
