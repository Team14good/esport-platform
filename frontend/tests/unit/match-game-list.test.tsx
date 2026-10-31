import { render, screen, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { MatchGameList } from "@/features/competition/MatchGameList"
import { matchDetail, TEAM_A, TEAM_B } from "./match-detail-fixture"

function rows() {
  return [...document.querySelectorAll<HTMLElement>("[data-slot=game-row]")]
}

function cells(row: HTMLElement) {
  return [...row.querySelectorAll<HTMLElement>("[data-slot=game-score]")] as [
    HTMLElement,
    HTMLElement,
  ]
}

describe("各局列表", () => {
  it("rounds：表頭「局」＋兩隊隊名，每局「第 N 局」＋「13 : 11」，勝方 foreground、敗方 status-eliminated", () => {
    render(
      <MatchGameList
        detail={matchDetail({
          status: "live",
          wins_a: 1,
          wins_b: 1,
          score_type: "rounds",
          games: [
            { game_no: 1, winner_side: "a", score_a: 13, score_b: 11 },
            { game_no: 2, winner_side: "b", score_a: 9, score_b: 13 },
          ],
        })}
      />,
    )

    const headers = screen.getAllByRole("columnheader")
    expect(headers.map((h) => h.textContent)).toEqual([
      "局",
      TEAM_A.name,
      TEAM_B.name,
    ])
    for (const header of headers) {
      expect(header).toHaveClass("text-overline", "text-muted-foreground")
    }

    const [first, second] = rows()
    expect(within(first).getByRole("rowheader")).toHaveTextContent("第 1 局")
    expect(first).toHaveTextContent("13:11")
    const [a1, b1] = cells(first)
    expect(a1).toHaveClass("text-foreground", "font-mono", "tabular-nums")
    expect(b1).toHaveClass("text-status-eliminated")

    expect(within(second).getByRole("rowheader")).toHaveTextContent("第 2 局")
    const [a2, b2] = cells(second)
    expect(a2).toHaveTextContent("9")
    expect(a2).toHaveClass("text-status-eliminated")
    expect(b2).toHaveClass("text-foreground")
  })

  it("win_loss：第 1 局 A 勝 → A 欄「勝」（foreground）、B 欄「負」（status-eliminated）", () => {
    render(
      <MatchGameList
        detail={matchDetail({
          status: "live",
          wins_a: 1,
          score_type: "win_loss",
          games: [
            { game_no: 1, winner_side: "a", score_a: null, score_b: null },
          ],
        })}
      />,
    )

    const [a, b] = cells(rows()[0])
    expect(a).toHaveTextContent("勝")
    expect(a).toHaveClass("text-foreground")
    expect(b).toHaveTextContent("負")
    expect(b).toHaveClass("text-status-eliminated")
  })

  it("沒有已登錄的局時整個 Card 不顯示", () => {
    const { container } = render(<MatchGameList detail={matchDetail()} />)
    expect(container).toBeEmptyDOMElement()
  })
})
