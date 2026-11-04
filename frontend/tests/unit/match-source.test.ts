import { afterEach, describe, expect, it, vi } from "vitest"

import { CompetitionService } from "@/client"
import { createBracketFixture } from "@/features/competition/bracket-fixtures"
import {
  fixtureScoreType,
  gameWinners,
  matchDetailFromBracket,
} from "@/features/competition/match-fixtures"
import {
  fetchMatchDetail,
  MatchNotFoundError,
  matchPath,
  matchQueryKey,
} from "@/features/competition/match-source"
import { httpError } from "./helpers"
import { matchDetail } from "./match-detail-fixture"

type ReadMatchResult = Awaited<
  ReturnType<typeof CompetitionService.readPublicMatch>
>

describe("場次資料來源", () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("呼叫公開單場 API，回傳場次資料", async () => {
    const detail = matchDetail()
    const read = vi
      .spyOn(CompetitionService, "readPublicMatch")
      .mockResolvedValue({ data: detail } as unknown as ReadMatchResult)

    await expect(
      fetchMatchDetail({ tournamentId: "t1", matchId: "match-M3" }),
    ).resolves.toBe(detail)
    expect(read).toHaveBeenCalledWith({
      path: { tournament_id: "t1", match_id: "match-M3" },
    })
  })

  it.each([
    [
      "404 MATCH_NOT_FOUND",
      httpError(404, {
        detail: { code: "MATCH_NOT_FOUND", message: "找不到這個場次。" },
      }),
    ],
    [
      "id 不是 UUID（422）",
      httpError(422, {
        detail: [
          { loc: ["path", "match_id"], msg: "Input should be a valid UUID" },
        ],
      }),
    ],
  ])("%s：拋出 MatchNotFoundError", async (_, error) => {
    vi.spyOn(CompetitionService, "readPublicMatch").mockRejectedValue(error)
    await expect(
      fetchMatchDetail({ tournamentId: "t1", matchId: "nope" }),
    ).rejects.toBeInstanceOf(MatchNotFoundError)
  })

  it("其他錯誤（伺服器錯誤、連線中斷）照原樣拋出，算連線失敗", async () => {
    const error = httpError(500, {})
    vi.spyOn(CompetitionService, "readPublicMatch").mockRejectedValue(error)
    await expect(
      fetchMatchDetail({ tournamentId: "t1", matchId: "match-M3" }),
    ).rejects.toBe(error)
  })

  it("S4 網址與 query key", () => {
    expect(matchPath("t 1", "match-M3")).toBe(
      "/tournaments/t%201/matches/match-M3",
    )
    expect(matchQueryKey("t1", "m1")).toEqual([
      "competition",
      "match",
      "t1",
      "m1",
    ])
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
