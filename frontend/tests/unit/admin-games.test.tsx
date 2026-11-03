import { screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { toast } from "sonner"
import { describe, expect, it, vi } from "vitest"

import { type GameRead, TournamentsService } from "@/client"
import {
  BACK_TO_GAMES_TEXT,
  GAME_NOT_FOUND_TEXT,
  GAMES_EMPTY_TEXT,
} from "@/features/tournaments/AdminGamesPage"
import {
  GAME_CREATED_TOAST_TEXT,
  GAME_SAVED_TOAST_TEXT,
} from "@/features/tournaments/admin-games"
import { FORBIDDEN_FALLBACK_MESSAGE } from "@/lib/api-error"
import { ACCOUNT, renderApp, signInAs } from "./auth-fixtures"
import { httpError } from "./helpers"

vi.mock("@tanstack/react-router-devtools", () => ({
  TanStackRouterDevtools: () => null,
}))
vi.mock("@tanstack/react-query-devtools", () => ({
  ReactQueryDevtools: () => null,
}))

type ListResult = Awaited<ReturnType<typeof TournamentsService.listGames>>
type ReadResult = Awaited<ReturnType<typeof TournamentsService.readGame>>
type CreateResult = Awaited<ReturnType<typeof TournamentsService.createGame>>
type UpdateResult = Awaited<ReturnType<typeof TournamentsService.updateGame>>

const ADMIN = { ...ACCOUNT, is_platform_admin: true }

const VALORANT: GameRead = {
  id: "game-1",
  name: "特戰英豪",
  starters: 5,
  substitutes: 2,
  default_bo: 3,
  game_minutes: 40,
  score_type: "rounds",
  rank_tiers: [
    { name: "神話", score: 100 },
    { name: "鑽石", score: 60 },
  ],
}

const CHESS: GameRead = {
  id: "game-2",
  name: "戰棋對決",
  starters: 1,
  substitutes: 0,
  default_bo: 1,
  game_minutes: 20,
  score_type: "win_loss",
  rank_tiers: [{ name: "大師", score: 10 }],
}

function listResult(games: GameRead[]): ListResult {
  return { data: games } as ListResult
}

function mockList(games: GameRead[] = [VALORANT, CHESS]) {
  return vi
    .spyOn(TournamentsService, "listGames")
    .mockResolvedValue(listResult(games))
}

function mockRead(game: GameRead = VALORANT) {
  return vi
    .spyOn(TournamentsService, "readGame")
    .mockResolvedValue({ data: game } as ReadResult)
}

function tableArea(): HTMLElement {
  return document.querySelector("[data-slot=data-table]") as HTMLElement
}

function cardArea(): HTMLElement {
  return document.querySelector("[data-slot=data-table-cards]") as HTMLElement
}

async function chooseOption(
  user: ReturnType<typeof userEvent.setup>,
  label: string,
  option: string,
) {
  await user.click(screen.getByRole("combobox", { name: label }))
  await user.click(await screen.findByRole("option", { name: option }))
}

/** 填好一份合法的新增表單（BO 與段位由呼叫端決定）。 */
async function fillBasics(user: ReturnType<typeof userEvent.setup>) {
  await user.type(await screen.findByLabelText("遊戲名稱"), "  虛構競技 ")
  await user.type(screen.getByLabelText("先發人數"), "3")
  await user.type(screen.getByLabelText("替補人數"), "0")
  await user.type(screen.getByLabelText("每局預估時間（分鐘）"), "15")
  await chooseOption(user, "比分型態", "記回合比分")
}

describe("S36 遊戲設定：列表", () => {
  it("不是平台管理員：顯示 S38 的 403，不呼叫遊戲 API", async () => {
    const list = mockList()
    signInAs()
    renderApp("/admin/games")

    expect(
      await screen.findByRole("heading", { name: FORBIDDEN_FALLBACK_MESSAGE }),
    ).toBeInTheDocument()
    expect(list).not.toHaveBeenCalled()
  })

  it("側欄有「遊戲設定」與「學校清單」，與「主辦方申請」同一層", async () => {
    mockList()
    signInAs({ account: ADMIN })
    renderApp("/admin/games")

    await screen.findByRole("table", { name: "遊戲" })
    const nav = document.querySelector(
      "[data-slot=backoffice-sidebar] nav",
    ) as HTMLElement
    const links = within(nav).getAllByRole("link")
    expect(links.map((link) => link.textContent)).toEqual([
      "主辦方申請",
      "遊戲設定",
      "學校清單",
    ])
    expect(within(nav).getByRole("link", { name: "遊戲設定" })).toHaveAttribute(
      "data-status",
      "active",
    )
  })

  it("Data table 列出名稱、先發／替補、預設 BO、每局時間、比分型態；名稱與「編輯」連到編輯頁", async () => {
    mockList()
    signInAs({ account: ADMIN })
    renderApp("/admin/games")

    await screen.findByRole("table", { name: "遊戲" })
    const table = within(tableArea()).getByRole("table")
    expect(
      within(table)
        .getAllByRole("columnheader")
        .map((header) => header.textContent),
    ).toEqual(["名稱", "先發／替補", "預設 BO", "每局時間", "比分型態", "操作"])
    const [, first, second] = within(table).getAllByRole("row")
    expect(
      within(first)
        .getAllByRole("cell")
        .map((cell) => cell.textContent),
    ).toEqual(["特戰英豪", "5／2", "BO3", "40 分鐘", "記回合比分", "編輯"])
    expect(within(second).getByText("只記勝負")).toBeInTheDocument()
    expect(
      within(first).getByRole("link", { name: "特戰英豪" }),
    ).toHaveAttribute("href", "/admin/games/game-1")
    expect(within(first).getByRole("link", { name: "編輯" })).toHaveAttribute(
      "href",
      "/admin/games/game-1",
    )
    expect(screen.getByRole("link", { name: "新增遊戲" })).toHaveAttribute(
      "href",
      "/admin/games/new",
    )
  })

  it("< md（375 px）改成卡片：每款遊戲一張，也有「編輯」", async () => {
    mockList()
    signInAs({ account: ADMIN })
    renderApp("/admin/games")

    await screen.findByRole("table", { name: "遊戲" })
    // jsdom 不排版：確認卡片清單存在且只在 < md 顯示，表格只在 ≥ md 顯示
    expect(cardArea()).toHaveClass("md:hidden")
    expect(tableArea()).toHaveClass("hidden", "md:block")
    const cards = within(cardArea()).getAllByRole("listitem")
    expect(cards).toHaveLength(2)
    expect(
      within(cards[0])
        .getAllByRole("term")
        .map((term) => term.textContent),
    ).toEqual(["名稱", "先發／替補", "預設 BO", "每局時間", "比分型態", "操作"])
    expect(
      within(cards[0]).getByRole("link", { name: "編輯" }),
    ).toBeInTheDocument()
  })

  it("超過 20 款：前端每頁 20 筆並可換頁", async () => {
    const user = userEvent.setup()
    const games = Array.from({ length: 21 }, (_, index) => ({
      ...CHESS,
      id: `game-${index}`,
      name: `遊戲 ${String(index).padStart(2, "0")}`,
    }))
    mockList(games)
    signInAs({ account: ADMIN })
    renderApp("/admin/games")

    const table = await screen.findByRole("table", { name: "遊戲" })
    expect(within(table).getAllByRole("row")).toHaveLength(21)
    await user.click(screen.getByRole("button", { name: "下一頁" }))

    await waitFor(() =>
      expect(within(table).getAllByRole("row")).toHaveLength(2),
    )
    expect(within(table).getByText("遊戲 20")).toBeInTheDocument()
  })

  it("沒有遊戲：Empty state 與「新增遊戲」", async () => {
    mockList([])
    signInAs({ account: ADMIN })
    renderApp("/admin/games")

    const empty = (await screen.findByText(GAMES_EMPTY_TEXT)).closest(
      "[data-slot=empty-state]",
    ) as HTMLElement
    expect(
      within(empty).getByRole("link", { name: "新增遊戲" }),
    ).toHaveAttribute("href", "/admin/games/new")
    expect(screen.queryByRole("table")).toBeNull()
  })

  it("讀取失敗：顯示錯誤與「重新載入」", async () => {
    const user = userEvent.setup()
    const list = vi
      .spyOn(TournamentsService, "listGames")
      .mockRejectedValueOnce(httpError(500, {}))
      .mockResolvedValue(listResult([VALORANT]))
    signInAs({ account: ADMIN })
    renderApp("/admin/games")

    expect(await screen.findByText("伺服器發生錯誤（500）")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "重新載入" }))

    expect(
      await screen.findByRole("table", { name: "遊戲" }),
    ).toBeInTheDocument()
    expect(list).toHaveBeenCalledTimes(2)
  })
})

describe("S36 遊戲設定：新增", () => {
  it("合法資料、2 筆段位：呼叫 createGame，Toast 後回列表並看到新遊戲", async () => {
    const user = userEvent.setup()
    const success = vi.spyOn(toast, "success")
    const created: GameRead = {
      id: "game-3",
      name: "虛構競技",
      starters: 3,
      substitutes: 0,
      default_bo: 5,
      game_minutes: 15,
      score_type: "rounds",
      rank_tiers: [
        { name: "黃金", score: 30 },
        { name: "白銀", score: 0 },
      ],
    }
    const list = vi
      .spyOn(TournamentsService, "listGames")
      .mockResolvedValue(listResult([VALORANT, created]))
    const create = vi
      .spyOn(TournamentsService, "createGame")
      .mockResolvedValue({ data: created } as CreateResult)
    signInAs({ account: ADMIN })
    const router = renderApp("/admin/games/new")

    expect(
      await screen.findByRole("heading", { name: "新增遊戲" }),
    ).toBeInTheDocument()
    await fillBasics(user)
    await chooseOption(user, "預設 BO 數", "BO5")
    await user.type(screen.getByLabelText("第 1 筆段位名稱"), "黃金")
    await user.type(screen.getByLabelText("第 1 筆積分"), "30")
    await user.click(screen.getByRole("button", { name: "新增段位" }))
    await user.type(screen.getByLabelText("第 2 筆段位名稱"), "白銀")
    await user.type(screen.getByLabelText("第 2 筆積分"), "0")
    await user.click(screen.getByRole("button", { name: "新增遊戲" }))

    await waitFor(() =>
      expect(create).toHaveBeenCalledWith({
        body: {
          name: "虛構競技",
          starters: 3,
          substitutes: 0,
          default_bo: 5,
          game_minutes: 15,
          score_type: "rounds",
          rank_tiers: [
            { name: "黃金", score: 30 },
            { name: "白銀", score: 0 },
          ],
        },
      }),
    )
    await waitFor(() =>
      expect(success).toHaveBeenCalledWith(GAME_CREATED_TOAST_TEXT, {
        duration: 3000,
      }),
    )
    await waitFor(() =>
      expect(router.state.location.pathname).toBe("/admin/games"),
    )
    const table = await screen.findByRole("table", { name: "遊戲" })
    expect(within(table).getByText("虛構競技")).toBeInTheDocument()
    expect(list).toHaveBeenCalled()
  })

  it("前端驗證：BO 留空、段位名稱不分大小寫重複、積分不是非負整數時不送出，錯誤標在欄位與該列", async () => {
    const user = userEvent.setup()
    const create = vi.spyOn(TournamentsService, "createGame")
    signInAs({ account: ADMIN })
    renderApp("/admin/games/new")

    await fillBasics(user)
    await user.type(screen.getByLabelText("第 1 筆段位名稱"), "Gold")
    await user.type(screen.getByLabelText("第 1 筆積分"), "10")
    await user.click(screen.getByRole("button", { name: "新增段位" }))
    await user.type(screen.getByLabelText("第 2 筆段位名稱"), " gold ")
    await user.type(screen.getByLabelText("第 2 筆積分"), "-1")
    await user.click(screen.getByRole("button", { name: "新增遊戲" }))

    expect(await screen.findByText("請選擇預設 BO 數")).toBeInTheDocument()
    const rows = within(
      screen.getByRole("list", { name: "段位" }),
    ).getAllByRole("listitem")
    expect(within(rows[0]).queryByText(/重複/)).toBeNull()
    expect(
      within(rows[1]).getByText("段位名稱「gold」重複"),
    ).toBeInTheDocument()
    expect(within(rows[1]).getByText("積分不能小於 0")).toBeInTheDocument()
    expect(create).not.toHaveBeenCalled()
  })

  it("前端驗證：名稱必填且 ≤100 字、先發 ≥1、每局時間 ≥1、段位至少一筆", async () => {
    const user = userEvent.setup()
    const create = vi.spyOn(TournamentsService, "createGame")
    signInAs({ account: ADMIN })
    renderApp("/admin/games/new")

    await user.type(await screen.findByLabelText("先發人數"), "0")
    await user.type(screen.getByLabelText("替補人數"), "1.5")
    await user.type(screen.getByLabelText("每局預估時間（分鐘）"), "0")
    await user.click(screen.getByRole("button", { name: "刪除第 1 筆段位" }))
    await user.click(screen.getByRole("button", { name: "新增遊戲" }))

    expect(await screen.findByText("請輸入遊戲名稱")).toBeInTheDocument()
    expect(screen.getByText("先發人數不能小於 1")).toBeInTheDocument()
    expect(screen.getByText("替補人數請輸入整數")).toBeInTheDocument()
    expect(screen.getByText("每局預估時間不能小於 1")).toBeInTheDocument()
    expect(screen.getByText("請選擇比分型態")).toBeInTheDocument()
    expect(screen.getByText("至少需要一筆段位")).toBeInTheDocument()

    await user.type(screen.getByLabelText("遊戲名稱"), "名".repeat(101))
    await user.click(screen.getByRole("button", { name: "新增遊戲" }))
    expect(await screen.findByText("遊戲名稱最多 100 個字")).toBeInTheDocument()
    expect(create).not.toHaveBeenCalled()
  })

  it("名稱重複（409）：後端訊息顯示在名稱欄位下方，表單保留輸入", async () => {
    const user = userEvent.setup()
    vi.spyOn(TournamentsService, "createGame").mockRejectedValue(
      httpError(409, {
        detail: { code: "GAME_NAME_TAKEN", message: "遊戲名稱已存在。" },
      }),
    )
    signInAs({ account: ADMIN })
    const router = renderApp("/admin/games/new")

    await fillBasics(user)
    await chooseOption(user, "預設 BO 數", "BO1")
    await user.type(screen.getByLabelText("第 1 筆段位名稱"), "黃金")
    await user.type(screen.getByLabelText("第 1 筆積分"), "30")
    await user.click(screen.getByRole("button", { name: "新增遊戲" }))

    const name = screen.getByLabelText("遊戲名稱")
    expect(await screen.findByText("遊戲名稱已存在。")).toHaveAttribute(
      "id",
      name.getAttribute("aria-describedby")?.split(" ")[1],
    )
    expect(name).toHaveValue("  虛構競技 ")
    expect(screen.getByLabelText("第 1 筆段位名稱")).toHaveValue("黃金")
    expect(router.state.location.pathname).toBe("/admin/games/new")
    expect(screen.queryByRole("alert")).toBeNull()
  })
})

describe("S36 遊戲設定：編輯", () => {
  it("預填現值；改 BO、刪一列段位後呼叫 updateGame，Toast「已儲存變更」", async () => {
    const user = userEvent.setup()
    const success = vi.spyOn(toast, "success")
    const read = mockRead()
    const update = vi
      .spyOn(TournamentsService, "updateGame")
      .mockResolvedValue({
        data: {
          ...VALORANT,
          default_bo: 7,
          rank_tiers: [VALORANT.rank_tiers[0]],
        },
      } as UpdateResult)
    signInAs({ account: ADMIN })
    renderApp("/admin/games/game-1")

    expect(await screen.findByLabelText("遊戲名稱")).toHaveValue("特戰英豪")
    expect(read).toHaveBeenCalledWith({ path: { game_id: "game-1" } })
    expect(screen.getByLabelText("先發人數")).toHaveValue("5")
    expect(screen.getByLabelText("替補人數")).toHaveValue("2")
    expect(screen.getByLabelText("每局預估時間（分鐘）")).toHaveValue("40")
    expect(
      screen.getByRole("combobox", { name: "預設 BO 數" }),
    ).toHaveTextContent("BO3")
    expect(
      screen.getByRole("combobox", { name: "比分型態" }),
    ).toHaveTextContent("記回合比分")
    expect(screen.getByLabelText("第 2 筆段位名稱")).toHaveValue("鑽石")
    expect(screen.getByLabelText("第 2 筆積分")).toHaveValue("60")

    await chooseOption(user, "預設 BO 數", "BO7")
    await user.click(screen.getByRole("button", { name: "刪除第 2 筆段位" }))
    await user.click(screen.getByRole("button", { name: "儲存變更" }))

    await waitFor(() =>
      expect(update).toHaveBeenCalledWith({
        path: { game_id: "game-1" },
        body: {
          name: "特戰英豪",
          starters: 5,
          substitutes: 2,
          default_bo: 7,
          game_minutes: 40,
          score_type: "rounds",
          rank_tiers: [{ name: "神話", score: 100 }],
        },
      }),
    )
    await waitFor(() =>
      expect(success).toHaveBeenCalledWith(GAME_SAVED_TOAST_TEXT, {
        duration: 3000,
      }),
    )
  })

  it("遊戲不存在（404）：顯示「找不到這款遊戲」與回列表的連結", async () => {
    vi.spyOn(TournamentsService, "readGame").mockRejectedValue(
      httpError(404, {
        detail: { code: "GAME_NOT_FOUND", message: "找不到這款遊戲。" },
      }),
    )
    signInAs({ account: ADMIN })
    renderApp("/admin/games/missing")

    expect(
      await screen.findByRole("heading", { name: GAME_NOT_FOUND_TEXT }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole("link", { name: BACK_TO_GAMES_TEXT }),
    ).toHaveAttribute("href", "/admin/games")
    expect(screen.queryByLabelText("遊戲名稱")).toBeNull()
  })
})

describe("S36 遊戲設定：錯誤處理與輸入", () => {
  it("列表讀取失敗時，頁首仍有「新增遊戲」", async () => {
    vi.spyOn(TournamentsService, "listGames").mockRejectedValue(
      httpError(500, {}),
    )
    signInAs({ account: ADMIN })
    renderApp("/admin/games")

    expect(await screen.findByText("伺服器發生錯誤（500）")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "新增遊戲" })).toHaveAttribute(
      "href",
      "/admin/games/new",
    )
  })

  it("網址的 gameId 不是 UUID（後端 422 game_id）：與 404 相同，顯示「找不到這款遊戲」", async () => {
    vi.spyOn(TournamentsService, "readGame").mockRejectedValue(
      httpError(422, {
        detail: [
          {
            loc: ["path", "game_id"],
            msg: "Input should be a valid UUID",
            type: "uuid_parsing",
          },
        ],
      }),
    )
    signInAs({ account: ADMIN })
    renderApp("/admin/games/not-a-uuid")

    expect(
      await screen.findByRole("heading", { name: GAME_NOT_FOUND_TEXT }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole("link", { name: BACK_TO_GAMES_TEXT }),
    ).toHaveAttribute("href", "/admin/games")
    expect(screen.queryByText(/valid UUID/)).toBeNull()
  })

  it("編輯頁讀取失敗（500）：顯示錯誤與「重新載入」，重試後預填表單", async () => {
    const user = userEvent.setup()
    vi.spyOn(TournamentsService, "readGame")
      .mockRejectedValueOnce(httpError(500, {}))
      .mockResolvedValue({ data: VALORANT } as ReadResult)
    signInAs({ account: ADMIN })
    renderApp("/admin/games/game-1")

    expect(await screen.findByText("伺服器發生錯誤（500）")).toBeInTheDocument()
    expect(screen.queryByText(GAME_NOT_FOUND_TEXT)).toBeNull()
    await user.click(screen.getByRole("button", { name: "重新載入" }))

    expect(await screen.findByLabelText("遊戲名稱")).toHaveValue("特戰英豪")
    expect(screen.getByLabelText("第 1 筆段位名稱")).toHaveValue("神話")
  })

  it("改名並儲存：標題換成新名稱", async () => {
    const user = userEvent.setup()
    mockRead()
    vi.spyOn(TournamentsService, "updateGame").mockResolvedValue({
      data: { ...VALORANT, name: "特戰英豪二代" },
    } as UpdateResult)
    signInAs({ account: ADMIN })
    renderApp("/admin/games/game-1")

    expect(
      await screen.findByRole("heading", { name: "編輯「特戰英豪」" }),
    ).toBeInTheDocument()
    await user.type(screen.getByLabelText("遊戲名稱"), "二代")
    await user.click(screen.getByRole("button", { name: "儲存變更" }))

    expect(
      await screen.findByRole("heading", { name: "編輯「特戰英豪二代」" }),
    ).toBeInTheDocument()
  })

  it("全形數字（中文輸入法）轉成半形送出", async () => {
    const user = userEvent.setup()
    mockList()
    const create = vi
      .spyOn(TournamentsService, "createGame")
      .mockResolvedValue({ data: CHESS } as CreateResult)
    signInAs({ account: ADMIN })
    renderApp("/admin/games/new")

    await user.type(await screen.findByLabelText("遊戲名稱"), "虛構競技")
    await user.type(screen.getByLabelText("先發人數"), "５")
    await user.type(screen.getByLabelText("替補人數"), "－０")
    await user.type(screen.getByLabelText("每局預估時間（分鐘）"), "１５")
    await chooseOption(user, "比分型態", "只記勝負")
    await chooseOption(user, "預設 BO 數", "BO3")
    await user.type(screen.getByLabelText("第 1 筆段位名稱"), "黃金")
    await user.type(screen.getByLabelText("第 1 筆積分"), "３０")
    await user.click(screen.getByRole("button", { name: "新增遊戲" }))

    await waitFor(() =>
      expect(create).toHaveBeenCalledWith({
        body: {
          name: "虛構競技",
          starters: 5,
          substitutes: 0,
          default_bo: 3,
          game_minutes: 15,
          score_type: "win_loss",
          rank_tiers: [{ name: "黃金", score: 30 }],
        },
      }),
    )
  })

  it("段位名稱比照後端 casefold：「Straße」與「STRASSE」視為重複", async () => {
    const user = userEvent.setup()
    const create = vi.spyOn(TournamentsService, "createGame")
    signInAs({ account: ADMIN })
    renderApp("/admin/games/new")

    await user.type(await screen.findByLabelText("第 1 筆段位名稱"), "Straße")
    await user.type(screen.getByLabelText("第 1 筆積分"), "1")
    await user.click(screen.getByRole("button", { name: "新增段位" }))
    await user.type(screen.getByLabelText("第 2 筆段位名稱"), "STRASSE")
    await user.type(screen.getByLabelText("第 2 筆積分"), "2")
    await user.click(screen.getByRole("button", { name: "新增遊戲" }))

    expect(
      await screen.findByText("段位名稱「STRASSE」重複"),
    ).toBeInTheDocument()
    expect(create).not.toHaveBeenCalled()
  })

  it("其他送出錯誤（500）：表單頂部顯示錯誤，保留輸入並留在新增頁", async () => {
    const user = userEvent.setup()
    vi.spyOn(TournamentsService, "createGame").mockRejectedValue(
      httpError(500, {}),
    )
    signInAs({ account: ADMIN })
    const router = renderApp("/admin/games/new")

    await fillBasics(user)
    await chooseOption(user, "預設 BO 數", "BO1")
    await user.type(screen.getByLabelText("第 1 筆段位名稱"), "黃金")
    await user.type(screen.getByLabelText("第 1 筆積分"), "30")
    await user.click(screen.getByRole("button", { name: "新增遊戲" }))

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "伺服器發生錯誤（500）",
    )
    expect(screen.getByLabelText("遊戲名稱")).toHaveValue("  虛構競技 ")
    expect(router.state.location.pathname).toBe("/admin/games/new")
  })
})
