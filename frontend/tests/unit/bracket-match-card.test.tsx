import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { BracketMatchCard } from "@/features/competition/BracketMatchCard"
import { BracketTree } from "@/features/competition/BracketTree"
import { createBracketFixture } from "@/features/competition/bracket-fixtures"
import type { PublicMatch } from "@/features/competition/bracket-types"
import {
  DEV_MATCH_SOURCE_TOURNAMENT_ID,
  matchPath,
} from "@/features/competition/match-source"
import { renderInRouter } from "./render-router"

const TEAM_A = { id: "team-a", name: "清大 Hydra" }
const TEAM_B = { id: "team-b", name: "交大 Nova" }

function match(overrides: Partial<PublicMatch> = {}): PublicMatch {
  return {
    id: "match-1",
    code: "M5",
    round_no: 2,
    slot_no: 1,
    is_third_place: false,
    team_a: TEAM_A,
    team_b: TEAM_B,
    source_a: null,
    source_b: null,
    bye_a: false,
    bye_b: false,
    // 台北時間 2026/10/18（日）13:00
    scheduled_at: "2026-10-18T05:00:00Z",
    status: "scheduled",
    outcome: null,
    winner_id: null,
    wins_a: 0,
    wins_b: 0,
    ...overrides,
  }
}

function renderCard(m: PublicMatch, flash = false) {
  render(<BracketMatchCard match={m} flash={flash} />)
  const card = screen.getByRole("article")
  const rows = card.querySelectorAll<HTMLElement>(
    "[data-slot=bracket-team-row]",
  )
  return { card, rowA: rows[0], rowB: rows[1] }
}

function headerOf(card: HTMLElement) {
  return card.querySelector("[data-slot=bracket-match-header]")
}

function scoreOf(row: HTMLElement) {
  return row.querySelector("[data-slot=bracket-score]")?.textContent
}

function nameOf(row: HTMLElement) {
  return row.querySelector<HTMLElement>("[data-slot=bracket-team-name]")!
}

function marksOf(row: HTMLElement) {
  return [
    ...row.querySelectorAll<HTMLElement>("[data-slot=bracket-mark-tag]"),
  ].map((tag) => tag.textContent)
}

describe("對戰樹場次卡", () => {
  beforeEach(() => {
    // formatMatchDateTime 與今天不同年時會加年份
    vi.useFakeTimers({ toFake: ["Date"] })
    vi.setSystemTime(new Date("2026-10-17T00:00:00Z"))
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it("待開打：標頭「M5 · 10/18（日）13:00」、沒有徽章、比分欄留空", () => {
    const { card, rowA, rowB } = renderCard(match())

    expect(card).toHaveAccessibleName("M5")
    expect(headerOf(card)).toHaveTextContent("M5 · 10/18（日）13:00")
    expect(card.querySelector("[data-slot=status-badge]")).toBeNull()
    expect(scoreOf(rowA)).toBe("")
    expect(scoreOf(rowB)).toBe("")
  })

  it("待開打、隊伍未定：待定列顯示來源（muted-foreground）", () => {
    const { rowA, rowB } = renderCard(
      match({
        team_a: null,
        team_b: null,
        source_a: "M1 勝者",
        source_b: "M2 勝者",
      }),
    )

    expect(rowA).toHaveTextContent("M1 勝者")
    expect(rowB).toHaveTextContent("M2 勝者")
    expect(rowA).toHaveClass("text-muted-foreground")
    expect(marksOf(rowA)).toEqual([])
  })

  it("季軍賽：標頭用「季軍賽」取代編號", () => {
    const { card } = renderCard(
      match({
        code: "M32",
        is_third_place: true,
        team_a: null,
        team_b: null,
        source_a: "M29 敗者",
        source_b: "M30 敗者",
      }),
    )

    expect(card).toHaveAccessibleName("季軍賽")
    expect(headerOf(card)).toHaveTextContent("季軍賽 · 10/18（日）13:00")
    expect(card).not.toHaveTextContent("M32")
    expect(card).toHaveTextContent("M29 敗者")
  })

  it("進行中：徽章帶脈動點、顯示比分、live 外框與光環、不套勝隊／淘汰樣式", () => {
    const { card, rowA, rowB } = renderCard(
      match({ status: "live", wins_a: 1, wins_b: 1 }),
    )

    const badge = within(card).getByText("進行中")
    expect(badge).toHaveAttribute("data-tone", "live")
    expect(badge.querySelector("[data-slot=status-badge-pulse]")).not.toBeNull()
    expect(headerOf(card)).not.toHaveTextContent("10/18")
    expect(card.className).toContain("var(--status-live)_55%")
    expect(card.className).toContain("shadow-[0_0_0_3px")
    expect(scoreOf(rowA)).toBe("1")
    expect(scoreOf(rowB)).toBe("1")
    for (const row of [rowA, rowB]) {
      expect(row).not.toHaveAttribute("data-winner")
      expect(row).not.toHaveAttribute("data-eliminated")
    }
  })

  it.each([
    ["appeal_window", "申訴期", false],
    ["appealed", "申訴中", true],
  ] as const)(
    "%s：徽章「%s」、顯示比分、兩列都不套勝隊／淘汰樣式",
    (status, label, pulse) => {
      const { card, rowA, rowB } = renderCard(
        match({
          status,
          outcome: "played",
          winner_id: TEAM_A.id,
          wins_a: 2,
          wins_b: 1,
        }),
      )

      const badge = within(card).getByText(label)
      expect(badge).toHaveAttribute("data-tone", "appeal")
      expect(
        badge.querySelector("[data-slot=status-badge-pulse]") !== null,
      ).toBe(pulse)
      expect(card.className).not.toContain("status-live")
      expect(scoreOf(rowA)).toBe("2")
      expect(scoreOf(rowB)).toBe("1")
      expect(nameOf(rowA)).not.toHaveClass("font-bold")
      expect(rowB).not.toHaveClass("text-status-eliminated")
      expect(nameOf(rowB)).not.toHaveClass("line-through")
    },
  )

  it("已確認：勝隊粗體、比分 primary；淘汰列 status-eliminated＋刪除線", () => {
    const { card, rowA, rowB } = renderCard(
      match({
        status: "confirmed",
        outcome: "played",
        winner_id: TEAM_B.id,
        wins_a: 0,
        wins_b: 2,
      }),
    )

    expect(within(card).getByText("已確認")).toHaveAttribute(
      "data-tone",
      "confirmed",
    )
    expect(nameOf(rowB)).toHaveClass("font-bold")
    expect(rowB.querySelector("[data-slot=bracket-score]")).toHaveClass(
      "text-primary",
    )
    expect(scoreOf(rowB)).toBe("2")
    expect(scoreOf(rowA)).toBe("0")
    expect(rowA).toHaveClass("text-status-eliminated")
    expect(nameOf(rowA)).toHaveClass("line-through")
    // 淘汰只用樣式表達，沒有「淘汰」標籤
    expect(card).not.toHaveTextContent("淘汰")
  })

  it("一隊棄權：沒有比分，棄權的一方帶「棄權」；已確認時棄權隊用淘汰列樣式", () => {
    const { rowA, rowB } = renderCard(
      match({ status: "confirmed", outcome: "forfeit", winner_id: TEAM_B.id }),
    )

    expect(marksOf(rowA)).toEqual(["棄權"])
    expect(marksOf(rowB)).toEqual([])
    expect(scoreOf(rowA)).toBe("")
    expect(scoreOf(rowB)).toBe("")
    expect(rowA).toHaveAttribute("data-eliminated")
    expect(rowB).toHaveAttribute("data-winner")
  })

  it("一隊棄權、申訴期內：仍帶「棄權」，兩列都不套樣式", () => {
    const { rowA, rowB } = renderCard(
      match({
        status: "appeal_window",
        outcome: "forfeit",
        winner_id: TEAM_B.id,
      }),
    )

    expect(marksOf(rowA)).toEqual(["棄權"])
    expect(scoreOf(rowA)).toBe("")
    expect(rowA).not.toHaveAttribute("data-eliminated")
    expect(rowB).not.toHaveAttribute("data-winner")
  })

  it("雙方棄權：兩方都帶「棄權」、都用淘汰列樣式、沒有比分", () => {
    const { rowA, rowB } = renderCard(
      match({ status: "confirmed", outcome: "double_forfeit" }),
    )

    for (const row of [rowA, rowB]) {
      expect(marksOf(row)).toEqual(["棄權"])
      expect(row).toHaveAttribute("data-eliminated")
      expect(scoreOf(row)).toBe("")
    }
  })

  it("取消資格：被取消資格的一方帶「取消資格」（destructive）、沒有比分", () => {
    const { rowA, rowB } = renderCard(
      match({
        status: "confirmed",
        outcome: "disqualified",
        winner_id: TEAM_A.id,
        wins_a: 1,
        wins_b: 1,
      }),
    )

    expect(marksOf(rowB)).toEqual(["取消資格"])
    expect(within(rowB).getByText("取消資格")).toHaveClass("text-destructive")
    expect(marksOf(rowA)).toEqual([])
    expect(scoreOf(rowA)).toBe("")
    expect(scoreOf(rowB)).toBe("")
  })

  it("輪空：bye_a 那一方帶「輪空」，標記為 muted-foreground 外框標籤", () => {
    const { rowA, rowB } = renderCard(
      match({ team_b: null, source_b: "M1 勝者", bye_a: true }),
    )

    expect(marksOf(rowA)).toEqual(["輪空"])
    expect(within(rowA).getByText("輪空")).toHaveClass(
      "text-muted-foreground",
      "border-current",
      "rounded-xs",
      "text-caption",
    )
    expect(marksOf(rowB)).toEqual([])
  })

  it("確定不會有隊伍（沒有隊伍也沒有來源）：顯示「—」＋「輪空」", () => {
    const { rowA, rowB } = renderCard(
      match({
        status: "confirmed",
        outcome: "walkover",
        team_a: null,
        winner_id: TEAM_B.id,
      }),
    )

    expect(nameOf(rowA)).toHaveTextContent("—")
    expect(marksOf(rowA)).toEqual(["輪空"])
    expect(rowA).not.toHaveAttribute("data-eliminated")
    expect(rowB).toHaveAttribute("data-winner")
    expect(scoreOf(rowB)).toBe("")
  })

  it("兩方都由輪空進入（例如 9 隊的第二輪）：兩列都帶「輪空」", () => {
    const { rowA, rowB } = renderCard(match({ bye_a: true, bye_b: true }))

    expect(nameOf(rowA)).toHaveTextContent(TEAM_A.name)
    expect(nameOf(rowB)).toHaveTextContent(TEAM_B.name)
    expect(marksOf(rowA)).toEqual(["輪空"])
    expect(marksOf(rowB)).toEqual(["輪空"])
  })

  it("已確認的 walkover 空缺方還帶著來源說明：仍顯示「—」＋「輪空」，不像待定", () => {
    const { rowA, rowB } = renderCard(
      match({
        status: "confirmed",
        outcome: "walkover",
        team_b: null,
        source_b: "M14 勝者",
        winner_id: TEAM_A.id,
      }),
    )

    expect(nameOf(rowB)).toHaveTextContent("—")
    expect(screen.queryByText("M14 勝者")).toBeNull()
    expect(marksOf(rowB)).toEqual(["輪空"])
    expect(rowA).toHaveAttribute("data-winner")
  })

  it("還沒確認的場次：沒有隊伍但有來源時照常顯示來源（待定）", () => {
    const { rowB } = renderCard(match({ team_b: null, source_b: "M14 勝者" }))

    expect(nameOf(rowB)).toHaveTextContent("M14 勝者")
    expect(rowB).toHaveAttribute("data-pending")
    expect(marksOf(rowB)).toEqual([])
  })

  it("季軍賽已取消：徽章「已取消」（muted-foreground）、兩列灰色、沒有比分", () => {
    const { card, rowA, rowB } = renderCard(
      match({
        code: "M4",
        is_third_place: true,
        status: "voided",
        team_a: null,
        source_a: "M2 敗者",
      }),
    )

    expect(within(card).getByText("已取消")).toHaveAttribute(
      "data-tone",
      "muted",
    )
    for (const row of [rowA, rowB]) {
      expect(row).toHaveClass("text-muted-foreground")
      expect(scoreOf(row)).toBe("")
    }
  })

  it("有變動時套用 update-flash，沒有變動時不套用", () => {
    const { card } = renderCard(match(), true)
    expect(card).toHaveClass("update-flash")

    const { rerender } = render(<BracketMatchCard match={match({ id: "x" })} />)
    rerender(<BracketMatchCard match={match({ id: "x" })} />)
    expect(screen.getAllByRole("article")[1]).not.toHaveClass("update-flash")
  })
})

describe("場次卡連到 S4", () => {
  beforeEach(() => {
    // formatMatchDateTime 與今天不同年時會加年份；只假 Date，router 仍用真的計時器
    vi.useFakeTimers({ toFake: ["Date"] })
    vi.setSystemTime(new Date("2026-10-17T00:00:00Z"))
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it("提供 matchHref 時整張卡是連結，可用鍵盤 focus、focus 時有外框", async () => {
    await renderInRouter(
      <BracketMatchCard
        match={match({ id: "match-M3", code: "M3" })}
        matchHref={(id) => `/tournaments/t1/matches/${id}`}
        className="absolute"
      />,
    )

    const link = await screen.findByRole("link")
    expect(link).toHaveAttribute("href", "/tournaments/t1/matches/match-M3")
    // 定位樣式移到外層連結，卡片內容不變
    expect(link).toHaveClass("absolute", "focus-visible:outline-2")
    // 連結內的 article 沒有自己的名稱，讀螢幕軟體聽到的是整句
    expect(link).toHaveAccessibleName(
      `M3，10/18（日）13:00，${TEAM_A.name} 對 ${TEAM_B.name}，待開打`,
    )
    expect(within(link).getByRole("article")).not.toHaveAttribute("aria-label")

    link.focus()
    expect(link).toHaveFocus()
  })

  it("連結的可及名稱：已確認含比分；輪空、棄權等標記接在隊名後；季軍賽用「季軍賽」", async () => {
    const href = (id: string) => `/tournaments/t1/matches/${id}`
    const { unmount } = await renderInRouter(
      <BracketMatchCard
        match={match({
          code: "M3",
          status: "confirmed",
          outcome: "played",
          winner_id: TEAM_A.id,
          wins_a: 2,
          wins_b: 1,
        })}
        matchHref={href}
      />,
    )
    expect(await screen.findByRole("link")).toHaveAccessibleName(
      `M3，${TEAM_A.name} 對 ${TEAM_B.name}，2 比 1，已確認`,
    )
    unmount()

    await renderInRouter(
      <BracketMatchCard
        match={match({
          code: "M9",
          is_third_place: true,
          status: "confirmed",
          outcome: "forfeit",
          winner_id: TEAM_A.id,
        })}
        matchHref={href}
      />,
    )
    expect(await screen.findByRole("link")).toHaveAccessibleName(
      `季軍賽，${TEAM_A.name} 對 ${TEAM_B.name}（棄權），已確認`,
    )
  })

  it("沒有 matchHref 時維持原本的樣子，沒有連結", () => {
    render(<BracketMatchCard match={match()} className="absolute" />)

    expect(screen.queryByRole("link")).toBeNull()
    expect(screen.getByRole("article")).toHaveClass("absolute")
  })

  it("對戰樹上點 M3：進入 /tournaments/{id}/matches/{M3 的 id}", async () => {
    const bracket = createBracketFixture({ teamCount: 8 })
    const { router } = await renderInRouter(
      <BracketTree
        bracket={bracket}
        matchHref={(id) => matchPath(DEV_MATCH_SOURCE_TOURNAMENT_ID, id)}
      />,
    )

    const card = await screen.findByRole("link", { name: /^M3，/ })
    fireEvent.click(card)
    await waitFor(() =>
      expect(router.state.location.pathname).toBe(
        `/tournaments/${DEV_MATCH_SOURCE_TOURNAMENT_ID}/matches/match-M3`,
      ),
    )
  })
})
