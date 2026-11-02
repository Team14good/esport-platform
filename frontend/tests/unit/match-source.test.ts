import { afterEach, describe, expect, it, vi } from "vitest"

import {
  createBracketFixture,
  FIXTURE_TOURNAMENT_ID,
} from "@/features/competition/bracket-fixtures"
import {
  fixtureScoreType,
  gameWinners,
  matchDetailFromBracket,
} from "@/features/competition/match-fixtures"
import {
  DEV_MATCH_SOURCE_TOURNAMENT_ID,
  fetchMatchDetail,
  MatchNotFoundError,
  matchPath,
} from "@/features/competition/match-source"

describe("場次資料來源", () => {
  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it("開發模式：從 32 隊「進行中」假對戰樹取得場次", async () => {
    const detail = await fetchMatchDetail({
      tournamentId: DEV_MATCH_SOURCE_TOURNAMENT_ID,
      matchId: "match-M3",
    })

    expect(detail).toMatchObject({
      id: "match-M3",
      code: "M3",
      round_name: "32 強",
      game_name: "特戰英豪",
      best_of: 3,
      tournament: { id: DEV_MATCH_SOURCE_TOURNAMENT_ID },
    })
    expect(detail.same_round).toHaveLength(15)
    expect(detail.same_round.some((m) => m.id === detail.id)).toBe(false)
  })

  it("賽事 id 與對戰樹假資料一致", () => {
    expect(DEV_MATCH_SOURCE_TOURNAMENT_ID).toBe(FIXTURE_TOURNAMENT_ID)
  })

  it.each([
    ["不存在的場次", DEV_MATCH_SOURCE_TOURNAMENT_ID, "match-M99"],
    ["其他賽事", "other", "match-M3"],
  ])("%s：拋出 MatchNotFoundError", async (_, tournamentId, matchId) => {
    await expect(
      fetchMatchDetail({ tournamentId, matchId }),
    ).rejects.toBeInstanceOf(MatchNotFoundError)
  })

  it("正式 build（DEV 為 false）：一律拋出 MatchNotFoundError，不回傳假資料", async () => {
    vi.stubEnv("DEV", false)
    await expect(
      fetchMatchDetail({
        tournamentId: DEV_MATCH_SOURCE_TOURNAMENT_ID,
        matchId: "match-M3",
      }),
    ).rejects.toBeInstanceOf(MatchNotFoundError)
  })

  it("S4 網址", () => {
    expect(matchPath("t 1", "match-M3")).toBe(
      "/tournaments/t%201/matches/match-M3",
    )
  })
})

describe("場次假資料的推導", () => {
  const bracket = createBracketFixture({
    teamCount: 32,
    scenario: "in_progress",
  })

  it.each([
    [2, 1, ["a", "b", "a"]],
    [1, 2, ["b", "a", "b"]],
    [0, 2, ["b", "b"]],
    [1, 1, ["a", "b"]],
    [0, 0, []],
  ] as const)(
    "系列 %i : %i → 局序固定、系列勝方拿下最後一局",
    (a, b, order) => {
      expect(gameWinners(a, b)).toEqual(order)
    },
  )

  it("各局由系列比分產生；比分型態依場次交替", () => {
    const m1 = matchDetailFromBracket(bracket, "match-M1")!
    expect(m1.score_type).toBe("rounds")
    expect(m1.games).toHaveLength(m1.wins_a + m1.wins_b)
    for (const game of m1.games) {
      const winner = game.winner_side === "a" ? game.score_a : game.score_b
      const loser = game.winner_side === "a" ? game.score_b : game.score_a
      expect(winner).toBe(13)
      expect(loser).toBeLessThan(13)
    }

    const m2 = matchDetailFromBracket(bracket, "match-M2")!
    expect(m2.score_type).toBe("win_loss")
    expect(
      m2.games.every((g) => g.score_a === null && g.score_b === null),
    ).toBe(true)
    expect(fixtureScoreType(m1)).not.toBe(fixtureScoreType(m2))
  })

  it("沒有比分的場次（棄權、待開打）沒有局", () => {
    expect(matchDetailFromBracket(bracket, "match-M4")!.games).toEqual([])
    expect(matchDetailFromBracket(bracket, "match-M25")!.games).toEqual([])
  })

  it("找不到場次時回傳 undefined", () => {
    expect(matchDetailFromBracket(bracket, "missing")).toBeUndefined()
  })
})
