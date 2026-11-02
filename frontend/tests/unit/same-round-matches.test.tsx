import { screen, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { createBracketFixture } from "@/features/competition/bracket-fixtures"
import { matchDetailFromBracket } from "@/features/competition/match-fixtures"
import { SameRoundMatches } from "@/features/competition/SameRoundMatches"
import { publicMatch } from "./match-detail-fixture"
import { renderInRouter } from "./render-router"

describe("同輪其他場次", () => {
  it("每場一個連到該場 S4 的連結：等寬編號＋狀態徽章", async () => {
    await renderInRouter(
      <SameRoundMatches
        tournamentId="t1"
        matches={[
          publicMatch({ id: "match-M1", code: "M1", status: "confirmed" }),
          publicMatch({ id: "match-M2", code: "M2", status: "live" }),
        ]}
      />,
    )

    expect(
      await screen.findByRole("heading", { name: "同輪其他場次" }),
    ).toBeInTheDocument()
    const links = screen.getAllByRole("link")
    expect(links.map((l) => l.getAttribute("href"))).toEqual([
      "/tournaments/t1/matches/match-M1",
      "/tournaments/t1/matches/match-M2",
    ])
    expect(within(links[0]).getByText("M1")).toHaveClass("font-mono")
    expect(within(links[0]).getByText("已確認")).toHaveAttribute(
      "data-tone",
      "confirmed",
    )
    expect(
      within(links[1])
        .getByText("進行中")
        .querySelector("[data-slot=status-badge-pulse]"),
    ).not.toBeNull()
    expect(screen.getByRole("list")).toHaveClass("flex-wrap")
  })

  it("同輪沒有其他場次時整塊不顯示", async () => {
    await renderInRouter(
      <div data-testid="host">
        <SameRoundMatches tournamentId="t1" matches={[]} />
      </div>,
    )
    expect(await screen.findByTestId("host")).toBeEmptyDOMElement()
  })
})

describe("同輪場次的推導（假資料）", () => {
  const bracket = createBracketFixture({
    teamCount: 32,
    scenario: "in_progress",
  })

  it("8 強 M25：列出 M26、M27、M28，不含自己", () => {
    const detail = matchDetailFromBracket(bracket, "match-M25")!
    expect(detail.same_round.map((m) => m.code)).toEqual(["M26", "M27", "M28"])
  })

  it("季軍賽與決賽互相列出", async () => {
    const third = matchDetailFromBracket(bracket, "match-M32")!
    expect(third.is_third_place).toBe(true)
    expect(third.same_round.map((m) => m.code)).toEqual(["M31"])
    const final = matchDetailFromBracket(bracket, "match-M31")!
    expect(final.same_round.map((m) => m.code)).toEqual(["M32"])

    await renderInRouter(
      <SameRoundMatches tournamentId="t1" matches={final.same_round} />,
    )
    expect(await screen.findByRole("link")).toHaveTextContent("季軍賽")
  })

  it("決賽、沒有季軍賽（2 隊）：同輪沒有其他場次", () => {
    const two = createBracketFixture({ teamCount: 2 })
    const final = matchDetailFromBracket(two, two.matches[0].id)!
    expect(final.same_round).toEqual([])
  })
})
