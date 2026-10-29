import { describe, expect, it } from "vitest"

import { createBracketFixture } from "@/features/competition/bracket-fixtures"
import {
  BRACKET_CARD_HEIGHT,
  BRACKET_THIRD_PLACE_GAP,
  layoutBracket,
} from "@/features/competition/bracket-layout"

function cardOf(layout: ReturnType<typeof layoutBracket>, code: string) {
  const card = layout.cards.find((c) => c.match.code === code)
  if (!card) throw new Error(`找不到 ${code}`)
  return card
}

describe("對戰樹版面計算", () => {
  it("32 隊：五欄、總寬 1112px，欄的 x 與示意圖相同", () => {
    const layout = layoutBracket(createBracketFixture({ teamCount: 32 }))

    expect(layout.width).toBe(1112)
    expect(layout.columns.map((c) => c.name)).toEqual([
      "32 強",
      "16 強",
      "8 強",
      "4 強",
      "決賽",
    ])
    expect(layout.columns.map((c) => c.x)).toEqual([0, 228, 456, 684, 912])
  })

  it("32 隊：M1～M31 加季軍賽 M32，直排位置與示意圖相同", () => {
    const layout = layoutBracket(createBracketFixture({ teamCount: 32 }))

    expect(layout.cards.map((c) => c.match.code)).toEqual(
      Array.from({ length: 32 }, (_, i) => `M${i + 1}`),
    )
    expect(cardOf(layout, "M1")).toMatchObject({ x: 0, y: 19 })
    expect(cardOf(layout, "M2")).toMatchObject({ x: 0, y: 104 })
    expect(cardOf(layout, "M17")).toMatchObject({ x: 228, y: 61.5 })
    expect(cardOf(layout, "M31")).toMatchObject({ x: 912, y: 656.5 })
    // 最後一張第一輪卡片的底部
    expect(layout.height).toBe(1294 + BRACKET_CARD_HEIGHT)
  })

  it("季軍賽卡放在決賽卡下方、不與決賽相連", () => {
    const layout = layoutBracket(createBracketFixture({ teamCount: 32 }))
    const final = cardOf(layout, "M31")
    const third = layout.cards.find((c) => c.match.is_third_place)!

    expect(third.x).toBe(final.x)
    expect(third.y).toBe(
      final.y + BRACKET_CARD_HEIGHT + BRACKET_THIRD_PLACE_GAP,
    )
    expect(layout.connectors.map((c) => c.id)).not.toContain(third.match.id)
  })

  it("連接線是直角折線，前後各 14px", () => {
    const layout = layoutBracket(createBracketFixture({ teamCount: 32 }))
    const m17 = cardOf(layout, "M17")

    expect(layout.connectors).toHaveLength(15)
    expect(layout.connectors.find((c) => c.id === m17.match.id)?.d).toBe(
      "M200 52.5 H214 V137.5 H200 M214 95 H228",
    )
  })

  it("13 隊：4 輪、第一輪只排實際存在的 5 場，後一輪照完整的 2 的次方排", () => {
    const layout = layoutBracket(createBracketFixture({ teamCount: 13 }))

    expect(layout.columns.map((c) => c.name)).toEqual([
      "16 強",
      "8 強",
      "4 強",
      "決賽",
    ])
    expect(layout.cards).toHaveLength(13)
    const firstRound = layout.cards.filter((c) => c.match.round_no === 1)
    expect(firstRound.map((c) => c.match.code)).toEqual([
      "M1",
      "M2",
      "M3",
      "M4",
      "M5",
    ])
    // 輪空的位置（第 1、3、5 格）不畫卡片，但仍佔位置
    expect(firstRound.map((c) => c.match.slot_no)).toEqual([2, 4, 6, 7, 8])
    expect(firstRound.map((c) => c.y)).toEqual([104, 274, 444, 529, 614])
    // 第二輪每張卡對齊兩個來源位置的正中間
    expect(
      layout.cards.filter((c) => c.match.round_no === 2).map((c) => c.y),
    ).toEqual([61.5, 231.5, 401.5, 571.5])
  })

  it("13 隊：輪空的一側沒有連接線", () => {
    const layout = layoutBracket(createBracketFixture({ teamCount: 13 }))
    const m6 = cardOf(layout, "M6")

    expect(m6.match.bye_side).toBe("a")
    // 只有 M1（第 2 格）接到 M6
    expect(layout.connectors.find((c) => c.id === m6.match.id)?.d).toBe(
      "M200 137.5 H214 V95 H228",
    )
  })

  it.each([2, 3])("%i 隊：沒有季軍賽", (teamCount) => {
    const layout = layoutBracket(createBracketFixture({ teamCount }))

    expect(layout.cards.some((c) => c.match.is_third_place)).toBe(false)
  })

  it("2 隊：只有決賽一欄", () => {
    const layout = layoutBracket(createBracketFixture({ teamCount: 2 }))

    expect(layout.width).toBe(200)
    expect(layout.columns.map((c) => c.name)).toEqual(["決賽"])
    expect(layout.cards).toHaveLength(1)
    expect(layout.connectors).toHaveLength(0)
  })

  it("4 隊：季軍賽卡在最下面，畫布高度包含它", () => {
    const layout = layoutBracket(createBracketFixture({ teamCount: 4 }))
    const third = layout.cards.find((c) => c.match.is_third_place)!

    expect(layout.height).toBe(third.y + BRACKET_CARD_HEIGHT)
  })
})
