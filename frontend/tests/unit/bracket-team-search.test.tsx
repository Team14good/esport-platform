import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import type { PublicBracket } from "@/client"
import {
  BracketExplorer,
  TEAM_SEARCH_NOT_FOUND_TEXT,
} from "@/features/competition/BracketTeamSearch"
import {
  BracketTree,
  bracketScrollLeftForRound,
} from "@/features/competition/BracketTree"
import { createBracketFixture } from "@/features/competition/bracket-fixtures"

// 8 隊「進行中」：M1 中興 Titan 勝、第二輪 M5 Titan 對交大 Nova 進行中，決賽 M7 A 方待定（「M5 勝者」）。

function inProgress() {
  return createBracketFixture({ teamCount: 8, scenario: "in_progress" })
}

function searchbox() {
  return screen.getByRole("searchbox", { name: "搜尋隊名" })
}

function row(container: HTMLElement, code: string, side: "a" | "b") {
  const row = container.querySelector<HTMLElement>(
    `[data-match-id="match-${code}"] [data-slot=bracket-team-row][data-side=${side}]`,
  )
  if (!row) throw new Error(`沒有 ${code} ${side}`)
  return row
}

/** 目前命中的列：「M1a」這種格式 */
function hitRows(container: HTMLElement) {
  return [...container.querySelectorAll<HTMLElement>("[data-search-hit]")].map(
    (r) =>
      `${r.closest("[data-match-id]")?.getAttribute("data-match-id")?.replace("match-", "")}${r.dataset.side}`,
  )
}

function pendingRows(container: HTMLElement) {
  return [
    ...container.querySelectorAll<HTMLElement>("[data-search-pending]"),
  ].map(
    (r) =>
      `${r.closest("[data-match-id]")?.getAttribute("data-match-id")?.replace("match-", "")}${r.dataset.side}`,
  )
}

/** 讓 jsdom 的捲動容器有寬度，並記錄每一次程式設定 scrollLeft */
function instrumentTree(container: HTMLElement, clientWidth = 317) {
  const tree = container.querySelector<HTMLElement>("[data-slot=bracket-tree]")!
  let value = 0
  const setter = vi.fn((next: number) => {
    value = next
  })
  Object.defineProperty(tree, "clientWidth", {
    configurable: true,
    get: () => clientWidth,
  })
  Object.defineProperty(tree, "scrollLeft", {
    configurable: true,
    get: () => value,
    set: setter,
  })
  return { tree, setter }
}

/** M5 確認 Titan 勝：Titan 進決賽 A 方 */
function titanAdvances(bracket: PublicBracket): PublicBracket {
  const titan = bracket.matches.find((m) => m.code === "M1")!.team_a!
  return {
    ...bracket,
    matches: bracket.matches.map((m) => {
      if (m.code === "M5")
        return {
          ...m,
          status: "confirmed" as const,
          outcome: "played" as const,
          winner_id: titan.id,
          wins_a: 2,
          wins_b: 0,
        }
      if (m.code === "M7") return { ...m, team_a: titan, source_a: null }
      return m
    }),
    updated_at: new Date(Date.parse(bracket.updated_at) + 5000).toISOString(),
  }
}

describe("對戰樹隊伍搜尋", () => {
  it("輸入即篩選：不分大小寫、命中一隊時高亮晉級路徑與虛線待定列", async () => {
    const user = userEvent.setup()
    const { container } = render(<BracketExplorer bracket={inProgress()} />)

    expect(screen.getByRole("status")).toHaveTextContent("")
    await user.type(searchbox(), "TITAN")

    expect(screen.getByRole("status")).toHaveTextContent("找到 1 隊")
    expect(hitRows(container)).toEqual(["M1a", "M5a"])
    expect(pendingRows(container)).toEqual(["M7a"])
    expect(row(container, "M7", "a")).toHaveTextContent("M5 勝者")
    expect(
      container.querySelector("[data-slot=bracket-search-connectors]"),
    ).toHaveAttribute("stroke", "var(--search-highlight)")
    expect(
      container.querySelector("[data-slot=bracket-search-connectors-pending]"),
    ).toHaveAttribute("stroke-dasharray", "4 3")
    // 只有一隊：沒有切換鈕
    expect(screen.queryByRole("button", { name: "下一隊" })).toBeNull()
  })

  it("命中列隊名加粗；虛線列只有虛線外框", async () => {
    const user = userEvent.setup()
    const { container } = render(<BracketExplorer bracket={inProgress()} />)
    await user.type(searchbox(), "titan")

    const hit = row(container, "M5", "a")
    expect(hit.querySelector("[data-slot=bracket-team-name]")).toHaveClass(
      "font-bold",
    )
    expect(hit.className).toContain("var(--search-highlight)")
    expect(row(container, "M7", "a")).toHaveClass("outline-dashed")
    expect(row(container, "M7", "a")).not.toHaveAttribute("data-search-hit")
  })

  it("清除：輸入清空、回到完整對戰樹、焦點回到輸入框", async () => {
    const user = userEvent.setup()
    const { container } = render(<BracketExplorer bracket={inProgress()} />)
    await user.type(searchbox(), "titan")
    await user.click(screen.getByRole("button", { name: "清除搜尋" }))

    expect(searchbox()).toHaveValue("")
    expect(searchbox()).toHaveFocus()
    expect(screen.getByRole("status")).toHaveTextContent("")
    expect(hitRows(container)).toEqual([])
    expect(pendingRows(container)).toEqual([])
    expect(
      container.querySelector("[data-slot=bracket-search-connectors]"),
    ).toBeNull()
    expect(screen.queryByRole("button", { name: "清除搜尋" })).toBeNull()
  })

  it("只有空白視為沒有搜尋：不顯示命中數", async () => {
    const user = userEvent.setup()
    const { container } = render(<BracketExplorer bracket={inProgress()} />)
    await user.type(searchbox(), "   ")

    expect(screen.getByRole("status")).toHaveTextContent("")
    expect(screen.queryByText(TEAM_SEARCH_NOT_FOUND_TEXT)).toBeNull()
    expect(hitRows(container)).toEqual([])
  })

  it("多隊命中：一次只高亮一隊，上一隊／下一隊循環切換", async () => {
    const user = userEvent.setup()
    const { container } = render(<BracketExplorer bracket={inProgress()} />)
    await user.type(searchbox(), "大")

    // 輔大 Blaze、清大 Hydra、交大 Nova、台大 Phoenix、成大 Kraken、政大 Viper、師大 Aurora
    expect(screen.getByRole("status")).toHaveTextContent("找到 7 隊")
    expect(hitRows(container)).toEqual(["M1b"])

    await user.click(screen.getByRole("button", { name: "下一隊" }))
    expect(hitRows(container)).toEqual(["M2a"])

    await user.click(screen.getByRole("button", { name: "上一隊" }))
    await user.click(screen.getByRole("button", { name: "上一隊" }))
    // 第一隊再往上一隊是最後一隊：師大 Aurora（M4 勝、M6 申訴期）
    expect(hitRows(container)).toEqual(["M4b", "M6b"])
    expect(pendingRows(container)).toEqual(["M7b"])

    await user.click(screen.getByRole("button", { name: "下一隊" }))
    expect(hitRows(container)).toEqual(["M1b"])
  })

  it("換搜尋字時回到第一隊", async () => {
    const user = userEvent.setup()
    const { container } = render(<BracketExplorer bracket={inProgress()} />)
    await user.type(searchbox(), "大")
    await user.click(screen.getByRole("button", { name: "下一隊" }))
    await user.type(searchbox(), " ")

    expect(hitRows(container)).toEqual(["M1b"])
  })

  it("零結果：「找到 0 隊」、說明文字、沒有高亮、保留輸入、不捲動", async () => {
    const user = userEvent.setup()
    const { container } = render(<BracketExplorer bracket={inProgress()} />)
    const { setter } = instrumentTree(container)
    await user.type(searchbox(), "不存在")

    const status = screen.getByRole("status")
    expect(status).toHaveTextContent("找到 0 隊")
    expect(status).toHaveClass("text-muted-foreground")
    expect(screen.getByText(TEAM_SEARCH_NOT_FOUND_TEXT)).toBeInTheDocument()
    expect(searchbox()).toHaveValue("不存在")
    expect(hitRows(container)).toEqual([])
    expect(screen.queryByRole("button", { name: "下一隊" })).toBeNull()
    expect(setter).not.toHaveBeenCalled()
    // 說明文字不在固定的搜尋列裡
    expect(
      container
        .querySelector("[data-slot=bracket-toolbar]")
        ?.contains(screen.getByText(TEAM_SEARCH_NOT_FOUND_TEXT)),
    ).toBe(false)
  })

  it("輪詢帶來新資料：輸入與高亮的隊伍保留，虛線列變成命中列，不再自動捲動", async () => {
    const user = userEvent.setup()
    const bracket = inProgress()
    const { container, rerender } = render(
      <BracketExplorer bracket={bracket} />,
    )
    const { setter } = instrumentTree(container)
    await user.type(searchbox(), "titan")

    expect(setter).toHaveBeenCalledTimes(1)
    expect(setter).toHaveBeenLastCalledWith(bracketScrollLeftForRound(2, 317))

    rerender(<BracketExplorer bracket={titanAdvances(bracket)} />)

    expect(searchbox()).toHaveValue("titan")
    expect(hitRows(container)).toEqual(["M1a", "M5a", "M7a"])
    expect(pendingRows(container)).toEqual([])
    expect(
      container.querySelector("[data-slot=bracket-search-connectors-pending]"),
    ).toBeNull()
    expect(setter).toHaveBeenCalledTimes(1)
  })

  it("自動捲動只在高亮的隊伍改變時發生，欄頭跟著位移", async () => {
    const user = userEvent.setup()
    const { container } = render(<BracketExplorer bracket={inProgress()} />)
    const { setter } = instrumentTree(container)
    await user.type(searchbox(), "大")

    // 每打一個字都重算，但高亮的仍是同一隊時只捲一次
    expect(setter).toHaveBeenCalledTimes(1)
    const heads = container.querySelector<HTMLElement>(
      "[data-slot=bracket-round-heads]",
    )!
    // 輔大 Blaze 只在第一輪：最遠一輪是第一輪
    expect(setter).toHaveBeenLastCalledWith(bracketScrollLeftForRound(1, 317))

    await user.click(screen.getByRole("button", { name: "上一隊" }))
    // 師大 Aurora 最遠到第二輪
    expect(setter).toHaveBeenCalledTimes(2)
    const left = bracketScrollLeftForRound(2, 317)
    expect(setter).toHaveBeenLastCalledWith(left)
    expect(heads.style.transform).toBe(`translateX(${-left}px)`)

    // 清除後重新搜尋同一隊也會再捲一次
    await user.click(screen.getByRole("button", { name: "清除搜尋" }))
    // 一次貼上，避免逐字輸入時中途命中別隊
    await user.paste("aurora")
    expect(setter).toHaveBeenCalledTimes(3)
    expect(setter).toHaveBeenLastCalledWith(left)
  })

  it("輪詢後原本高亮的隊伍不再命中：改高亮第一隊", async () => {
    const user = userEvent.setup()
    const bracket = inProgress()
    const { container, rerender } = render(
      <BracketExplorer bracket={bracket} />,
    )
    await user.type(searchbox(), "大")
    await user.click(screen.getByRole("button", { name: "下一隊" }))
    expect(hitRows(container)).toEqual(["M2a"])

    const renamed = {
      ...bracket,
      matches: bracket.matches.map((m) =>
        m.team_a?.name === "清大 Hydra"
          ? { ...m, team_a: { ...m.team_a, name: "清華 Hydra" } }
          : m,
      ),
    }
    rerender(<BracketExplorer bracket={renamed} />)

    expect(screen.getByRole("status")).toHaveTextContent("找到 6 隊")
    expect(hitRows(container)).toEqual(["M1b"])
  })

  it("搜尋列在橫向捲動容器之外、固定在頂端；輪次欄頭也在容器外、固定在搜尋列下方", () => {
    const { container } = render(<BracketExplorer bracket={inProgress()} />)

    const tree = container.querySelector("[data-slot=bracket-tree]")!
    const toolbar = container.querySelector("[data-slot=bracket-toolbar]")!
    expect(toolbar).toContainElement(searchbox())
    expect(tree.contains(searchbox())).toBe(false)
    expect(toolbar).toHaveClass("sticky", "top-0")
    const headsViewport = container.querySelector(
      "[data-slot=bracket-round-heads-viewport]",
    )!
    expect(headsViewport).toHaveClass("sticky", "top-13", "overflow-hidden")
    expect(tree.querySelector("[data-slot=bracket-round-heads]")).toBeNull()
  })
})

describe("沒有傳搜尋相關 prop 的 BracketTree（與 4.6 相同）", () => {
  it("沒有搜尋列、欄頭不固定、沒有任何高亮", () => {
    const { container } = render(<BracketTree bracket={inProgress()} />)

    expect(container.querySelector("[data-slot=bracket-toolbar]")).toBeNull()
    expect(screen.queryByRole("searchbox")).toBeNull()
    expect(
      container.querySelector("[data-slot=bracket-round-heads-viewport]"),
    ).not.toHaveClass("sticky")
    expect(hitRows(container)).toEqual([])
    expect(pendingRows(container)).toEqual([])
    expect(
      container.querySelector("[data-slot=bracket-search-connectors]"),
    ).toBeNull()
  })
})

describe("bracketScrollLeftForRound", () => {
  it("讓該欄完整露出並帶出下一段連接線；容器夠寬時不捲", () => {
    // 第三輪欄左緣 456＋內距 4，右邊到下一段連接線結束 460＋228＝688
    expect(bracketScrollLeftForRound(3, 317)).toBe(688 - 317)
    expect(bracketScrollLeftForRound(1, 1280)).toBe(0)
    // 容器比一欄加連接線還窄：以欄的左緣為準
    expect(bracketScrollLeftForRound(3, 100)).toBe(460)
  })
})
