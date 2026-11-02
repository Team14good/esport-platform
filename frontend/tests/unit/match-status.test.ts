import { describe, expect, it } from "vitest"

import {
  hasScore,
  MATCH_STATUS_BADGES,
  matchLabel,
  sideView,
} from "@/features/competition/match-status"
import { publicMatch, TEAM_A, TEAM_B } from "./match-detail-fixture"

describe("場次狀態徽章對照", () => {
  it.each([
    ["scheduled", "待開打", "muted", false],
    ["live", "進行中", "live", true],
    ["appeal_window", "申訴期", "appeal", false],
    ["appealed", "申訴中", "appeal", true],
    ["confirmed", "已確認", "confirmed", false],
    ["voided", "已取消", "muted", false],
  ] as const)("%s → 「%s」（%s）", (status, label, tone, pulse) => {
    const badge = MATCH_STATUS_BADGES[status]
    expect(badge.label).toBe(label)
    expect(badge.tone).toBe(tone)
    expect(badge.pulse ?? false).toBe(pulse)
  })
})

describe("場次名稱與比分", () => {
  it("季軍賽寫「季軍賽」，其他寫編號", () => {
    expect(matchLabel(publicMatch())).toBe("M3")
    expect(matchLabel(publicMatch({ code: "M32", is_third_place: true }))).toBe(
      "季軍賽",
    )
  })

  it.each([
    ["待開打", { status: "scheduled" }, false],
    ["進行中", { status: "live" }, true],
    ["申訴期", { status: "appeal_window", outcome: "played" }, true],
    ["已確認", { status: "confirmed", outcome: "played" }, true],
    ["棄權", { status: "confirmed", outcome: "forfeit" }, false],
    ["雙方棄權", { status: "appeal_window", outcome: "double_forfeit" }, false],
    ["輪空", { status: "confirmed", outcome: "walkover" }, false],
    ["取消資格", { status: "confirmed", outcome: "disqualified" }, false],
    ["已取消", { status: "voided" }, false],
  ] as const)("%s：顯示比分 = %s", (_, patch, expected) => {
    expect(hasScore(publicMatch(patch))).toBe(expected)
  })
})

describe("一方隊伍的顯示", () => {
  it("已確認的一方棄權：棄權方帶「棄權」並淘汰，對手為勝方", () => {
    const m = publicMatch({
      status: "confirmed",
      outcome: "forfeit",
      winner_id: TEAM_A.id,
    })
    expect(sideView(m, "b")).toMatchObject({
      name: TEAM_B.name,
      marks: [{ label: "棄權", tone: "default" }],
      eliminated: true,
      winner: false,
    })
    expect(sideView(m, "a")).toMatchObject({ winner: true, eliminated: false })
  })

  it("申訴期：不套勝敗樣式", () => {
    const m = publicMatch({
      status: "appeal_window",
      outcome: "played",
      winner_id: TEAM_A.id,
      wins_a: 2,
    })
    expect(sideView(m, "a")).toMatchObject({ winner: false, eliminated: false })
    expect(sideView(m, "b")).toMatchObject({ winner: false, eliminated: false })
  })

  it("隊伍未定：顯示來源、muted", () => {
    const view = sideView(
      publicMatch({ team_b: null, source_b: "M4 勝者" }),
      "b",
    )
    expect(view).toMatchObject({ name: "M4 勝者", pending: true, marks: [] })
  })
})
