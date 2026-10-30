import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { MatchScoreDisplay } from "@/features/competition/MatchScoreDisplay"
import type { PublicMatchDetail } from "@/features/competition/match-types"
import { matchDetail, TEAM_A, TEAM_B } from "./match-detail-fixture"

function renderScore(detail: PublicMatchDetail, flash = false) {
  render(<MatchScoreDisplay detail={detail} flash={flash} />)
  const display = document.querySelector<HTMLElement>(
    "[data-slot=score-display]",
  )!
  const [teamA, teamB] = display.querySelectorAll<HTMLElement>(
    "[data-slot=score-team]",
  )
  const score = display.querySelector<HTMLElement>("[data-slot=score]")!
  return { display, teamA, teamB, score }
}

function nameOf(team: HTMLElement) {
  return team.querySelector<HTMLElement>("[data-slot=score-team-name]")!
}

function marksOf(team: HTMLElement) {
  return [
    ...team.querySelectorAll<HTMLElement>("[data-slot=bracket-mark-tag]"),
  ].map((tag) => tag.textContent)
}

describe("Score display", () => {
  it("已確認、正常完賽：「隊A 2 : 1 隊B」，A 粗體、B status-eliminated", () => {
    const { display, teamA, teamB, score } = renderScore(
      matchDetail({
        status: "confirmed",
        outcome: "played",
        winner_id: TEAM_A.id,
        wins_a: 2,
        wins_b: 1,
      }),
    )

    expect(display).toHaveTextContent(`${TEAM_A.name}2:1${TEAM_B.name}`)
    expect(score).toHaveClass("text-score", "font-mono")
    expect(screen.getByText(":")).toHaveClass("text-muted-foreground")
    expect(nameOf(teamA)).toHaveClass("font-bold")
    expect(teamB).toHaveClass("text-status-eliminated")
    expect(display.querySelector("[data-slot=score-b]")).toHaveClass(
      "text-status-eliminated",
    )
    expect(display.querySelector("[data-slot=score-a]")).not.toHaveClass(
      "text-status-eliminated",
    )
  })

  it("進行中 1 : 0：顯示比分，不套勝敗樣式", () => {
    const { teamA, teamB, score } = renderScore(
      matchDetail({ status: "live", wins_a: 1, wins_b: 0 }),
    )

    expect(score).toHaveTextContent("1:0")
    for (const team of [teamA, teamB]) {
      expect(team).not.toHaveAttribute("data-winner")
      expect(team).not.toHaveAttribute("data-eliminated")
    }
    expect(nameOf(teamA)).not.toHaveClass("font-bold")
  })

  it("申訴期 2 : 0：顯示比分，不套勝敗樣式", () => {
    const { teamA, teamB, score } = renderScore(
      matchDetail({
        status: "appeal_window",
        outcome: "played",
        winner_id: TEAM_A.id,
        wins_a: 2,
        wins_b: 0,
      }),
    )

    expect(score).toHaveTextContent("2:0")
    expect(nameOf(teamA)).not.toHaveClass("font-bold")
    expect(teamB).not.toHaveClass("text-status-eliminated")
  })

  it("待開打、隊伍已定：兩隊隊名＋muted 的「—」", () => {
    const { display, score } = renderScore(matchDetail())

    expect(display).toHaveTextContent(`${TEAM_A.name}—${TEAM_B.name}`)
    expect(score).toHaveTextContent("—")
    expect(score).toHaveClass("text-muted-foreground")
  })

  it("隊伍未定：B 側顯示「M4 勝者」（muted）", () => {
    const { teamB } = renderScore(
      matchDetail({ team_b: null, source_b: "M4 勝者" }),
    )

    expect(teamB).toHaveTextContent("M4 勝者")
    expect(teamB).toHaveClass("text-muted-foreground")
  })

  it("一方棄權：「—」；B 帶「棄權」並套淘汰樣式，A 套勝方樣式", () => {
    const { teamA, teamB, score } = renderScore(
      matchDetail({
        status: "confirmed",
        outcome: "forfeit",
        winner_id: TEAM_A.id,
      }),
    )

    expect(score).toHaveTextContent("—")
    expect(marksOf(teamB)).toEqual(["棄權"])
    expect(teamB).toHaveClass("text-status-eliminated")
    expect(marksOf(teamA)).toEqual([])
    expect(nameOf(teamA)).toHaveClass("font-bold")
  })

  it("雙方棄權（申訴期）：「—」；兩隊都帶「棄權」，不套樣式", () => {
    const { teamA, teamB, score } = renderScore(
      matchDetail({ status: "appeal_window", outcome: "double_forfeit" }),
    )

    expect(score).toHaveTextContent("—")
    for (const team of [teamA, teamB]) {
      expect(marksOf(team)).toEqual(["棄權"])
      expect(team).not.toHaveAttribute("data-eliminated")
      expect(nameOf(team)).not.toHaveClass("font-bold")
    }
  })

  it.each([
    [
      "輪空",
      {
        status: "confirmed",
        outcome: "walkover",
        team_b: null,
        winner_id: TEAM_A.id,
      },
      "輪空",
    ],
    [
      "取消資格",
      {
        status: "confirmed",
        outcome: "disqualified",
        winner_id: TEAM_A.id,
        wins_a: 1,
        wins_b: 1,
      },
      "取消資格",
    ],
  ] as const)("%s：沒有比分，B 帶「%s」", (_, patch, mark) => {
    const { teamB, score } = renderScore(matchDetail(patch))

    expect(score).toHaveTextContent("—")
    expect(marksOf(teamB)).toEqual([mark])
  })

  it("已取消：沒有比分", () => {
    const { score } = renderScore(matchDetail({ status: "voided" }))
    expect(score).toHaveTextContent("—")
  })

  it("有變動時套用 update-flash", () => {
    const { display } = renderScore(matchDetail({ status: "live" }), true)
    expect(display).toHaveClass("update-flash")
  })
})
