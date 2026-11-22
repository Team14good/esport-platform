import { describe, expect, it } from "vitest"

import type { PublicBracket, PublicMatch } from "@/client"
import { createBracketFixture } from "@/features/competition/bracket-fixtures"
import {
  bracketTeamPath,
  searchBracketTeams,
} from "@/features/competition/bracket-search"

// 8 隊「進行中」：M1 中興 Titan 勝輔大 Blaze、M2 交大 Nova 勝清大 Hydra、M3 台大 Phoenix 勝成大 Kraken、
// M4 師大 Aurora 勝政大 Viper（棄權）；第二輪 M5 Titan 對 Nova 進行中、M6 Phoenix 對 Aurora 申訴期。
// 8 隊「全部已確認」：M5 Nova 勝、M6 Phoenix 勝、決賽 M7 Nova 勝（冠軍）、季軍賽 M8 Titan 對 Aurora。

function teamId(bracket: PublicBracket, name: string): string {
  for (const match of bracket.matches) {
    for (const team of [match.team_a, match.team_b]) {
      if (team?.name === name) return team.id
    }
  }
  throw new Error(`對戰表上沒有 ${name}`)
}

function matchByCode(bracket: PublicBracket, code: string): PublicMatch {
  const match = bracket.matches.find((m) => m.code === code)
  if (!match) throw new Error(`沒有 ${code}`)
  return match
}

function id(code: string) {
  return `match-${code}`
}

describe("searchBracketTeams", () => {
  const bracket = createBracketFixture({ teamCount: 8 })

  it("去掉前後空白、不分大小寫、部分符合", () => {
    expect(searchBracketTeams(bracket, "  HYDRA ").map((t) => t.name)).toEqual([
      "清大 Hydra",
    ])
    expect(searchBracketTeams(bracket, "ph").map((t) => t.name)).toEqual([
      "台大 Phoenix",
    ])
  })

  it("全形英數與空白不影響比對：搜尋字與隊名都做 NFKC 並去掉空白", () => {
    expect(
      searchBracketTeams(bracket, "ｔｉｔａｎ").map((t) => t.name),
    ).toEqual(["中興 Titan"])
    expect(searchBracketTeams(bracket, "清大Hydra").map((t) => t.name)).toEqual(
      ["清大 Hydra"],
    )
    expect(
      searchBracketTeams(bracket, "台大　ＰＨＯ").map((t) => t.name),
    ).toEqual(["台大 Phoenix"])
  })

  it.each(["", "   ", "\u3000"])("空字串（%j）視為沒有搜尋", (query) => {
    expect(searchBracketTeams(bracket, query)).toEqual([])
  })

  it("零結果回傳空陣列", () => {
    expect(searchBracketTeams(bracket, "不存在的隊")).toEqual([])
  })

  it("依第一次出現的位置排序：輪次、同輪由上到下、同場 A 方在前", () => {
    // matches 陣列倒過來也一樣
    const reversed = { ...bracket, matches: [...bracket.matches].reverse() }
    expect(searchBracketTeams(reversed, "大").map((t) => t.name)).toEqual([
      "輔大 Blaze",
      "清大 Hydra",
      "交大 Nova",
      "台大 Phoenix",
      "成大 Kraken",
      "政大 Viper",
      "師大 Aurora",
    ])
  })

  it("一隊出現在多場只算一次", () => {
    const finished = createBracketFixture({
      teamCount: 8,
      scenario: "finished",
    })
    expect(searchBracketTeams(finished, "nova")).toHaveLength(1)
  })

  it("第一輪輪空的隊伍排在第一輪出現的隊伍之後", () => {
    // 13 隊：中山 Tempest 由輪空直接進第二輪 M6
    const byes = createBracketFixture({ teamCount: 13 })
    expect(searchBracketTeams(byes, "中").map((t) => t.name)).toEqual([
      "中興 Titan",
      "中央 Vortex",
      "中正 Falcon",
      "中山 Tempest",
    ])
  })

  it("同一輪的季軍賽排在決賽之後", () => {
    const finished = createBracketFixture({
      teamCount: 8,
      scenario: "finished",
    })
    const matches = finished.matches.map((m) => {
      if (m.code === "M8") return { ...m, team_a: { id: "z", name: "Alpha Z" } }
      if (m.code === "M7") return { ...m, team_b: { id: "y", name: "Alpha Y" } }
      return m
    })
    expect(
      searchBracketTeams(
        { ...finished, matches: matches.reverse() },
        "alpha",
      ).map((t) => t.name),
    ).toEqual(["Alpha Y", "Alpha Z"])
  })
})

describe("bracketTeamPath", () => {
  it("進行中：命中列、實線連接線、下一輪虛線待定列、最遠輪次", () => {
    const bracket = createBracketFixture({
      teamCount: 8,
      scenario: "in_progress",
    })
    const path = bracketTeamPath(bracket, teamId(bracket, "中興 Titan"))

    expect(path.hits).toEqual([
      { matchId: id("M1"), side: "a" },
      { matchId: id("M5"), side: "a" },
    ])
    expect(path.pending).toEqual({ matchId: id("M7"), side: "a" })
    expect(path.connectors).toEqual([
      {
        child: { matchId: id("M1"), side: "a" },
        parent: { matchId: id("M5"), side: "a" },
        dashed: false,
      },
      {
        child: { matchId: id("M5"), side: "a" },
        parent: { matchId: id("M7"), side: "a" },
        dashed: true,
      },
    ])
    expect(path.farthestRound).toBe(2)
  })

  it("申訴期仍有虛線列；slot 偶數的勝者到下一輪的 B 方", () => {
    const bracket = createBracketFixture({
      teamCount: 8,
      scenario: "in_progress",
    })
    const path = bracketTeamPath(bracket, teamId(bracket, "台大 Phoenix"))

    expect(matchByCode(bracket, "M6").status).toBe("appeal_window")
    expect(path.pending).toEqual({ matchId: id("M7"), side: "b" })
  })

  it("已淘汰：出現過的列都命中，沒有虛線列", () => {
    const bracket = createBracketFixture({
      teamCount: 8,
      scenario: "in_progress",
    })
    const path = bracketTeamPath(bracket, teamId(bracket, "清大 Hydra"))

    expect(path.hits).toEqual([{ matchId: id("M2"), side: "a" }])
    expect(path.pending).toBeNull()
    expect(path.connectors).toEqual([])
    expect(path.farthestRound).toBe(1)
  })

  it("冠軍：每一輪的列與連接線，沒有虛線列", () => {
    const bracket = createBracketFixture({ teamCount: 8, scenario: "finished" })
    const path = bracketTeamPath(bracket, teamId(bracket, "交大 Nova"))

    expect(path.hits).toEqual([
      { matchId: id("M2"), side: "b" },
      { matchId: id("M5"), side: "b" },
      { matchId: id("M7"), side: "a" },
    ])
    expect(
      path.connectors.map((c) => [c.child.matchId, c.parent.matchId]),
    ).toEqual([
      [id("M2"), id("M5")],
      [id("M5"), id("M7")],
    ])
    expect(path.connectors.every((c) => !c.dashed)).toBe(true)
    expect(path.pending).toBeNull()
    expect(path.farthestRound).toBe(3)
  })

  it("打季軍賽：季軍賽的列也命中，但不畫連接線；季軍賽算最後一輪", () => {
    const bracket = createBracketFixture({ teamCount: 8, scenario: "finished" })
    const path = bracketTeamPath(bracket, teamId(bracket, "中興 Titan"))

    expect(path.hits).toEqual([
      { matchId: id("M1"), side: "a" },
      { matchId: id("M5"), side: "a" },
      { matchId: id("M8"), side: "a" },
    ])
    expect(path.connectors.map((c) => c.parent.matchId)).toEqual([id("M5")])
    expect(path.pending).toBeNull()
    expect(path.farthestRound).toBe(3)
  })

  it("第一輪輪空：從第二輪開始命中，沒有第一輪的連接線", () => {
    const bracket = createBracketFixture({ teamCount: 13 })
    const path = bracketTeamPath(bracket, teamId(bracket, "中山 Tempest"))

    expect(path.hits).toEqual([{ matchId: id("M6"), side: "a" }])
    expect(path.connectors.filter((c) => !c.dashed)).toEqual([])
    // 第二輪待開打：第三輪留給它的位置是虛線列
    expect(path.pending).toEqual({ matchId: id("M10"), side: "a" })
    expect(path.farthestRound).toBe(2)
  })

  it("決賽沒有虛線列", () => {
    const bracket = createBracketFixture({ teamCount: 2 })
    const path = bracketTeamPath(bracket, teamId(bracket, "中興 Titan"))

    expect(path.hits).toEqual([{ matchId: id("M1"), side: "a" }])
    expect(path.pending).toBeNull()
    expect(path.connectors).toEqual([])
  })

  it("已取消（voided）的場次不算未確認，沒有虛線列", () => {
    const bracket = createBracketFixture({ teamCount: 4 })
    const voided = {
      ...bracket,
      matches: bracket.matches.map((m) =>
        m.code === "M1" ? { ...m, status: "voided" as const } : m,
      ),
    }
    const path = bracketTeamPath(voided, teamId(voided, "中興 Titan"))

    expect(path.pending).toBeNull()
  })

  it("下一輪的位置已由它填入時沒有虛線列", () => {
    const bracket = createBracketFixture({
      teamCount: 8,
      scenario: "in_progress",
    })
    // M5 仍顯示進行中，但決賽 A 方已經有 Titan（例如資料剛更新到一半）
    const titan = matchByCode(bracket, "M1").team_a
    const seated = {
      ...bracket,
      matches: bracket.matches.map((m) =>
        m.code === "M7" ? { ...m, team_a: titan, source_a: null } : m,
      ),
    }
    const path = bracketTeamPath(seated, teamId(seated, "中興 Titan"))

    expect(path.pending).toBeNull()
    expect(path.hits.map((h) => h.matchId)).toContain(id("M7"))
  })

  it("一方棄權（forfeit）的敗方：只命中那一場，沒有虛線列", () => {
    const bracket = createBracketFixture({
      teamCount: 8,
      scenario: "in_progress",
    })
    expect(matchByCode(bracket, "M4").outcome).toBe("forfeit")
    const path = bracketTeamPath(bracket, teamId(bracket, "政大 Viper"))

    expect(path.hits).toEqual([{ matchId: id("M4"), side: "a" }])
    expect(path.connectors).toEqual([])
    expect(path.pending).toBeNull()
    expect(path.farthestRound).toBe(1)
  })

  it("雙方棄權（double_forfeit）：兩隊都停在那一場，下一輪的空位不畫虛線列", () => {
    const bracket = createBracketFixture({
      teamCount: 8,
      scenario: "third_place_voided",
    })
    const m5 = matchByCode(bracket, "M5")
    expect(m5.outcome).toBe("double_forfeit")
    // 下一輪等它勝者的位置是空的，但場次已確認，不是「等結果」
    expect(matchByCode(bracket, "M7").team_a).toBeNull()

    for (const team of [m5.team_a, m5.team_b]) {
      const path = bracketTeamPath(bracket, team!.id)
      expect(path.pending).toBeNull()
      expect(path.connectors.every((c) => !c.dashed)).toBe(true)
      expect(path.hits.map((h) => h.matchId)).not.toContain(id("M7"))
      expect(path.farthestRound).toBe(2)
    }
  })

  it("取消資格（disqualified）：被取消資格的一方停在那一場，對手晉級並接上連接線", () => {
    const bracket = createBracketFixture({ teamCount: 8, scenario: "finished" })
    const m6 = matchByCode(bracket, "M6")
    expect(m6.outcome).toBe("disqualified")
    const winner = m6.team_a!
    const loser = m6.team_b!

    const loserPath = bracketTeamPath(bracket, loser.id)
    expect(loserPath.pending).toBeNull()
    expect(loserPath.connectors.map((c) => c.parent.matchId)).not.toContain(
      id("M7"),
    )

    const winnerPath = bracketTeamPath(bracket, winner.id)
    expect(winnerPath.pending).toBeNull()
    expect(winnerPath.connectors).toContainEqual({
      child: { matchId: id("M6"), side: "a" },
      parent: { matchId: id("M7"), side: "b" },
      dashed: false,
    })
  })

  it("不在對戰表上的隊伍：沒有任何路徑", () => {
    const bracket = createBracketFixture({ teamCount: 8 })
    expect(bracketTeamPath(bracket, "nobody")).toEqual({
      hits: [],
      connectors: [],
      pending: null,
      farthestRound: null,
    })
  })
})
