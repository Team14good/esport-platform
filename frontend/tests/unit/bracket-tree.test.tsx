import { render, screen, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { BracketPending } from "@/features/competition/BracketPending"
import { BracketTree } from "@/features/competition/BracketTree"
import { createBracketFixture } from "@/features/competition/bracket-fixtures"
import { ConnectionLostBanner } from "@/features/competition/ConnectionLostBanner"

function cardByName(name: string) {
  return screen.getByRole("article", { name })
}

function rowsOf(card: HTMLElement) {
  return [...card.querySelectorAll<HTMLElement>("[data-slot=bracket-team-row]")]
}

describe("視覺化對戰樹", () => {
  it("32 隊：五欄欄頭、畫布寬 1112px、M1～M31 與季軍賽", () => {
    const { container } = render(
      <BracketTree bracket={createBracketFixture({ teamCount: 32 })} />,
    )

    const heads = container.querySelector("[data-slot=bracket-round-heads]")!
    expect(
      [...heads.querySelectorAll("span")].map((s) => s.textContent),
    ).toEqual(["32 強", "16 強", "8 強", "4 強", "決賽"])
    const canvas = container.querySelector<HTMLElement>(
      "[data-slot=bracket-canvas]",
    )!
    expect(canvas.style.width).toBe("1112px")

    const cards = screen.getAllByRole("article")
    expect(cards.map((c) => c.getAttribute("aria-label"))).toEqual([
      ...Array.from({ length: 31 }, (_, i) => `M${i + 1}`),
      "季軍賽",
    ])
    // 不顯示種子或籤位
    expect(container).not.toHaveTextContent("種子")
  })

  it("只有對戰樹容器可以橫向捲動", () => {
    const { container } = render(
      <BracketTree bracket={createBracketFixture({ teamCount: 16 })} />,
    )

    expect(container.querySelector("[data-slot=bracket-tree]")).toHaveClass(
      "overflow-x-auto",
      "max-w-full",
    )
  })

  it("待開打：待定列顯示「M1 勝者」，季軍賽為「M… 敗者」", () => {
    render(<BracketTree bracket={createBracketFixture({ teamCount: 8 })} />)

    // 8 隊：8 強 M1～M4、4 強 M5～M6、決賽 M7、季軍賽 M8
    expect(rowsOf(cardByName("M5")).map((r) => r.textContent)).toEqual([
      "M1 勝者",
      "M2 勝者",
    ])
    expect(rowsOf(cardByName("季軍賽")).map((r) => r.textContent)).toEqual([
      "M5 敗者",
      "M6 敗者",
    ])
  })

  it("13 隊：第一輪只畫 5 場，輪空隊伍直接出現在第二輪並帶「輪空」", () => {
    const bracket = createBracketFixture({ teamCount: 13 })
    render(<BracketTree bracket={bracket} />)

    expect(screen.getAllByRole("article")).toHaveLength(13)
    const m6 = cardByName("M6")
    const [rowA, rowB] = rowsOf(m6)
    expect(within(rowA).getByText("輪空")).toBeInTheDocument()
    expect(rowA).not.toHaveTextContent("勝者")
    expect(rowB).toHaveTextContent("M1 勝者")
  })

  it.each([2, 3])("%i 隊：沒有季軍賽卡", (teamCount) => {
    render(<BracketTree bracket={createBracketFixture({ teamCount })} />)

    expect(screen.queryByRole("article", { name: "季軍賽" })).toBeNull()
  })

  it("季軍賽取消情境：決賽一方「—」＋「輪空」、季軍賽「已取消」", () => {
    render(
      <BracketTree
        bracket={createBracketFixture({
          teamCount: 8,
          scenario: "third_place_voided",
        })}
      />,
    )

    const [finalA] = rowsOf(cardByName("M7"))
    expect(finalA).toHaveTextContent("—")
    expect(within(finalA).getByText("輪空")).toBeInTheDocument()
    expect(within(cardByName("季軍賽")).getByText("已取消")).toBeInTheDocument()
    const m5 = cardByName("M5")
    expect(within(m5).getAllByText("棄權")).toHaveLength(2)
  })

  it("只有變動的場次卡 flash，其他卡不重新掛載", () => {
    const bracket = createBracketFixture({ teamCount: 8 })
    const { rerender } = render(<BracketTree bracket={bracket} />)
    const m1 = cardByName("M1")
    const m2 = cardByName("M2")

    rerender(
      <BracketTree
        bracket={bracket}
        changedMatchIds={new Set([m2.dataset.matchId!])}
      />,
    )

    expect(cardByName("M1")).toBe(m1)
    expect(cardByName("M1")).not.toHaveClass("update-flash")
    expect(cardByName("M2")).toHaveClass("update-flash")
    expect(
      document.querySelectorAll("[data-slot=bracket-match-card].update-flash"),
    ).toHaveLength(1)
  })

  it("同一張卡連續兩次輪詢都有變動時，再 flash 一次（重新掛載）", () => {
    const bracket = createBracketFixture({ teamCount: 8 })
    const { rerender } = render(<BracketTree bracket={bracket} />)
    const id = cardByName("M2").dataset.matchId!

    rerender(<BracketTree bracket={bracket} changedMatchIds={new Set([id])} />)
    const first = cardByName("M2")
    rerender(<BracketTree bracket={bracket} changedMatchIds={new Set([id])} />)

    expect(cardByName("M2")).not.toBe(first)
    expect(cardByName("M2")).toHaveClass("update-flash")
  })
})

describe("尚未抽籤與連線中斷", () => {
  it("尚未抽籤：空狀態文字＋倒數插槽", () => {
    render(<BracketPending countdown={<span>報名截止倒數</span>} />)

    expect(
      screen.getByText("報名截止後抽籤，對戰表會出現在這裡。"),
    ).toBeInTheDocument()
    expect(screen.getByText("報名截止倒數")).toBeInTheDocument()
  })

  it("連線中斷 banner：顯示最後更新的台北時間 HH:mm:ss", () => {
    render(
      <ConnectionLostBanner lastUpdatedAt={new Date("2026-10-18T05:04:09Z")} />,
    )

    expect(screen.getByRole("alert")).toHaveTextContent(
      "連線中斷，正在重試 · 最後更新 13:04:09",
    )
  })

  it("從未成功取得資料時不寫最後更新", () => {
    render(<ConnectionLostBanner lastUpdatedAt={null} />)

    expect(screen.getByRole("alert")).toHaveTextContent("連線中斷，正在重試")
    expect(screen.getByRole("alert")).not.toHaveTextContent("最後更新")
  })
})
