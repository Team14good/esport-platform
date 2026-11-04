import { act, fireEvent, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { toast } from "sonner"
import { describe, expect, it, vi } from "vitest"

import {
  type GameRead,
  type Identity,
  type TournamentRead,
  TournamentsService,
} from "@/client"
import { formatMatchDateTime } from "@/features/competition/match-time"
import {
  CAPACITY_WARNING_TEXT,
  TOURNAMENT_CREATED_TEXT,
} from "@/features/tournaments/CreateTournamentForm"
import { NO_TOURNAMENTS_TEXT } from "@/features/tournaments/OrganizerTournamentsPage"
import { FORBIDDEN_FALLBACK_MESSAGE } from "@/lib/api-error"
import { taipeiLocalToIso } from "@/lib/datetime"
import { ACCOUNT, BROWSE, renderApp, signInAs } from "./auth-fixtures"
import { httpError } from "./helpers"

vi.mock("@tanstack/react-router-devtools", () => ({
  TanStackRouterDevtools: () => null,
}))
vi.mock("@tanstack/react-query-devtools", () => ({
  ReactQueryDevtools: () => null,
}))

type ListMineResult = Awaited<
  ReturnType<typeof TournamentsService.listMyTournaments>
>
type ReadMineResult = Awaited<
  ReturnType<typeof TournamentsService.readMyTournament>
>
type ListGamesResult = Awaited<
  ReturnType<typeof TournamentsService.listGamesForOrganizer>
>

const ORGANIZER = { ...ACCOUNT, is_organizer: true }
const ORGANIZER_IDENTITY: Identity = {
  key: "organizer",
  label: "主辦方後台",
  home_path: "/organizer",
}

const VALORANT: GameRead = {
  id: "game-val",
  name: "特戰英豪",
  starters: 5,
  substitutes: 1,
  default_bo: 3,
  game_minutes: 40,
  score_type: "rounds",
  rank_tiers: [],
}
const CHESS: GameRead = {
  id: "game-chess",
  name: "虛構棋",
  starters: 3,
  substitutes: 0,
  default_bo: 7,
  game_minutes: 10,
  score_type: "win_loss",
  rank_tiers: [],
}

const TOURNAMENT: TournamentRead = {
  id: "t-1",
  organizer_id: ORGANIZER.id,
  name: "臺大秋季盃",
  status: "open",
  mode: "campus",
  capacity: 32,
  // 台北時間 2026/11/03 12:00 ～ 2026/11/09 23:00，優先期結束 11/04 12:00
  registration_start: "2026-11-03T04:00:00Z",
  priority_end: "2026-11-04T04:00:00Z",
  registration_end: "2026-11-09T15:00:00Z",
  // 台北時間 2026/11/10 19:00
  start_at: "2026-11-10T11:00:00Z",
  round_interval_minutes: 150,
  forfeit_minutes: 15,
  appeal_minutes: 30,
  livestream_url: "https://twitch.tv/ntu",
  game_id: VALORANT.id,
  game_name: VALORANT.name,
  starters: 5,
  substitutes: 1,
  bo: 3,
  game_minutes: 40,
  score_type: "rounds",
  rank_tiers: [],
}
const ONGOING: TournamentRead = {
  ...TOURNAMENT,
  id: "t-2",
  name: "清大冬季盃",
  status: "ongoing",
}

function mockMine(tournaments: TournamentRead[]) {
  return vi
    .spyOn(TournamentsService, "listMyTournaments")
    .mockResolvedValue({ data: tournaments } as ListMineResult)
}

function mockGames(games: GameRead[] = [VALORANT, CHESS]) {
  return vi
    .spyOn(TournamentsService, "listGamesForOrganizer")
    .mockResolvedValue({ data: games } as ListGamesResult)
}

function mockRead(tournament: TournamentRead = TOURNAMENT) {
  return vi
    .spyOn(TournamentsService, "readMyTournament")
    .mockResolvedValue({ data: tournament } as ReadMineResult)
}

function mockCreate() {
  return vi.spyOn(TournamentsService, "createTournament").mockImplementation(
    async (options) =>
      ({
        data: { ...TOURNAMENT, id: "t-new", ...options.body },
      }) as never,
  )
}

function sidebar(): HTMLElement {
  return document.querySelector("[data-slot=backoffice-sidebar]") as HTMLElement
}

function tableArea(): HTMLElement {
  return document.querySelector("[data-slot=data-table]") as HTMLElement
}

function forbiddenHeading() {
  return screen.findByRole("heading", { name: FORBIDDEN_FALLBACK_MESSAGE })
}

/** 欄位下方的錯誤訊息（FormMessage）。 */
function fieldMessage(label: string): string | null {
  const input = screen.getByLabelText(label)
  const item = input.closest("[data-slot=form-item]") as HTMLElement
  return item.querySelector("[data-slot=form-message]")?.textContent ?? null
}

type User = ReturnType<typeof userEvent.setup>

async function chooseGame(user: User, name: string) {
  await user.click(screen.getByRole("combobox", { name: "遊戲" }))
  await user.click(await screen.findByRole("option", { name }))
}

async function setNumber(user: User, label: string, value: string) {
  const input = screen.getByLabelText(label)
  await user.clear(input)
  if (value) await user.type(input, value)
}

// datetime-local 在 jsdom 逐字輸入時中間值不合法會被清空，直接設定整個值
function setDateTime(label: string, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } })
}

/** 填一份合法的表單（特戰英豪：棄權 15＋BO3 × 40＋申訴 30 = 165）。 */
async function fillValidForm(
  user: User,
  overrides: { capacity?: string } = {},
) {
  await user.type(screen.getByLabelText("賽事名稱"), "臺大秋季盃")
  await chooseGame(user, "特戰英豪")
  await setNumber(user, "名額", overrides.capacity ?? "32")
  setDateTime("報名開始", "2026-11-03T12:00")
  setDateTime("報名截止", "2026-11-09T23:00")
  setDateTime("開賽時間", "2026-11-10T19:00")
  await setNumber(user, "每輪間隔（分鐘）", "180")
}

async function openCreatePage() {
  mockGames()
  signInAs({ account: ORGANIZER })
  const router = renderApp("/organizer/tournaments/new")
  await screen.findByRole("heading", { name: "建立賽事" })
  // 遊戲清單載入後選單才啟用
  await waitFor(() =>
    expect(screen.getByRole("combobox", { name: "遊戲" })).toBeEnabled(),
  )
  return router
}

describe("taipeiLocalToIso", () => {
  it("台北時間轉成 UTC 的 ISO；不合法的值回傳 null", () => {
    expect(taipeiLocalToIso("2026-11-10T19:00")).toBe(
      "2026-11-10T11:00:00.000Z",
    )
    expect(taipeiLocalToIso("2026-01-01T03:30")).toBe(
      "2025-12-31T19:30:00.000Z",
    )
    expect(taipeiLocalToIso("2026-11-10T19:00:30")).toBe(
      "2026-11-10T11:00:30.000Z",
    )
    expect(taipeiLocalToIso("")).toBeNull()
    expect(taipeiLocalToIso("2026-02-30T10:00")).toBeNull()
    expect(taipeiLocalToIso("2026-11-10 19:00")).toBeNull()
  })
})

describe("S25 我的賽事", () => {
  it("有賽事：欄位、名稱連到 S27、狀態徽章；標題列有「建立賽事」", async () => {
    mockMine([TOURNAMENT, ONGOING])
    signInAs({ account: ORGANIZER })
    renderApp("/organizer")

    await screen.findByRole("table", { name: "我的賽事" })
    const table = within(tableArea()).getByRole("table", { name: "我的賽事" })
    expect(
      within(table)
        .getAllByRole("columnheader")
        .map((header) => header.textContent),
    ).toEqual(["賽事名稱", "遊戲", "狀態", "報名截止", "開賽時間"])
    const [, openRow, ongoingRow] = within(table).getAllByRole("row")
    expect(
      within(openRow).getByRole("link", { name: "臺大秋季盃" }),
    ).toHaveAttribute("href", "/organizer/tournaments/t-1")
    expect(within(openRow).getByText("特戰英豪")).toBeInTheDocument()
    expect(within(openRow).getByText("開放報名")).toHaveAttribute(
      "data-tone",
      "live",
    )
    expect(within(openRow).getByText("2026/11/09 23:00")).toBeInTheDocument()
    expect(within(openRow).getByText("2026/11/10 19:00")).toBeInTheDocument()
    const ongoingBadge = within(ongoingRow).getByText("進行中")
    expect(ongoingBadge).toHaveAttribute("data-tone", "live")
    expect(
      ongoingBadge.querySelector("[data-slot=status-badge-pulse]"),
    ).not.toBeNull()
    expect(screen.getByRole("link", { name: "建立賽事" })).toHaveAttribute(
      "href",
      "/organizer/tournaments/new",
    )
    expect(screen.queryByText(NO_TOURNAMENTS_TEXT)).toBeNull()
  })

  it("超過 20 筆時前端分頁，頁碼寫在網址", async () => {
    const user = userEvent.setup()
    const many = Array.from({ length: 21 }, (_, index) => ({
      ...TOURNAMENT,
      id: `t-${index + 1}`,
      name: `賽事 ${index + 1}`,
    }))
    mockMine(many)
    signInAs({ account: ORGANIZER })
    const router = renderApp("/organizer")

    await screen.findAllByRole("link", { name: "賽事 20" })
    expect(screen.queryByRole("link", { name: "賽事 21" })).toBeNull()
    await user.click(screen.getByRole("button", { name: "下一頁" }))

    await screen.findAllByRole("link", { name: "賽事 21" })
    expect(screen.queryByRole("link", { name: "賽事 1" })).toBeNull()
    expect(router.state.location.search).toEqual({ page: 2 })
  })

  it("網址頁碼超出：換到最後一頁", async () => {
    const many = Array.from({ length: 21 }, (_, index) => ({
      ...TOURNAMENT,
      id: `t-${index + 1}`,
      name: `賽事 ${index + 1}`,
    }))
    mockMine(many)
    signInAs({ account: ORGANIZER })
    const router = renderApp("/organizer?page=3")

    await screen.findAllByRole("link", { name: "賽事 21" })
    await waitFor(() =>
      expect(router.state.location.search).toEqual({ page: 2 }),
    )
    expect(screen.queryByText(NO_TOURNAMENTS_TEXT)).toBeNull()
  })

  it("清單載入失敗：顯示錯誤，按「重新載入」重抓", async () => {
    const user = userEvent.setup()
    const mine = vi
      .spyOn(TournamentsService, "listMyTournaments")
      .mockRejectedValueOnce(httpError(500, "Internal Server Error"))
      .mockResolvedValue({ data: [] } as unknown as ListMineResult)
    signInAs({ account: ORGANIZER })
    renderApp("/organizer")

    await user.click(await screen.findByRole("button", { name: "重新載入" }))

    expect(await screen.findByText(NO_TOURNAMENTS_TEXT)).toBeInTheDocument()
    expect(mine).toHaveBeenCalledTimes(2)
  })

  it("狀態徽章的色調依 DESIGN.md", async () => {
    const statuses = [
      ["upcoming", "尚未開放", "muted"],
      ["closed", "報名截止", "muted"],
      ["published", "賽程已公布", "brand"],
      ["finished", "已結束", "muted"],
      ["cancelled", "已取消", "destructive"],
    ] as const
    mockMine(
      statuses.map(([status], index) => ({
        ...TOURNAMENT,
        id: `t-${index}`,
        status,
      })),
    )
    signInAs({ account: ORGANIZER })
    renderApp("/organizer")

    await screen.findByRole("table", { name: "我的賽事" })
    const table = within(tableArea())
    for (const [, label, tone] of statuses) {
      const badge = table
        .getAllByText(label)
        .find((element) => element.dataset.slot === "status-badge")
      expect(badge).toHaveAttribute("data-tone", tone)
    }
  })
})

describe("S26 建立賽事", () => {
  it("沒有賽事模式欄位；優先期、棄權、申訴有預設值", async () => {
    await openCreatePage()

    expect(screen.queryByText(/賽事模式|校園賽/)).toBeNull()
    expect(screen.getByLabelText("優先期（小時）")).toHaveValue(24)
    expect(screen.getByLabelText("棄權時限（分鐘）")).toHaveValue(15)
    expect(screen.getByLabelText("申訴期（分鐘）")).toHaveValue(30)
  })

  it("選遊戲帶入先發、替補、BO；改選另一款時重新帶入，帶入後可修改", async () => {
    const user = userEvent.setup()
    await openCreatePage()

    await chooseGame(user, "特戰英豪")
    expect(screen.getByLabelText("先發人數")).toHaveValue(5)
    expect(screen.getByLabelText("替補人數")).toHaveValue(1)
    expect(screen.getByRole("combobox", { name: "BO" })).toHaveTextContent(
      "BO3",
    )

    await setNumber(user, "先發人數", "4")
    expect(screen.getByLabelText("先發人數")).toHaveValue(4)

    await chooseGame(user, "虛構棋")
    expect(screen.getByLabelText("先發人數")).toHaveValue(3)
    expect(screen.getByLabelText("替補人數")).toHaveValue(0)
    expect(screen.getByRole("combobox", { name: "BO" })).toHaveTextContent(
      "BO7",
    )
  })

  it("每輪間隔不足：不送出，欄位下方「每輪間隔至少 85 分鐘」；選好遊戲後一直顯示最小間隔", async () => {
    const user = userEvent.setup()
    const create = mockCreate()
    await openCreatePage()
    await fillValidForm(user)

    // 每局 40、BO1、棄權 15、申訴 30 → 85
    await user.click(screen.getByRole("combobox", { name: "BO" }))
    await user.click(await screen.findByRole("option", { name: "BO1" }))
    expect(screen.getByText(/目前的最小間隔：85 分鐘/)).toBeInTheDocument()
    await setNumber(user, "每輪間隔（分鐘）", "80")
    await user.click(screen.getByRole("button", { name: "建立賽事" }))

    await waitFor(() =>
      expect(fieldMessage("每輪間隔（分鐘）")).toBe("每輪間隔至少 85 分鐘"),
    )
    expect(create).not.toHaveBeenCalled()

    // 棄權時限改成 20 時，最小間隔跟著更新
    await setNumber(user, "棄權時限（分鐘）", "20")
    expect(screen.getByText(/目前的最小間隔：90 分鐘/)).toBeInTheDocument()
    // 送出過一次後，跨欄位的錯誤跟著依賴的欄位更新
    await waitFor(() =>
      expect(fieldMessage("每輪間隔（分鐘）")).toBe("每輪間隔至少 90 分鐘"),
    )
  })

  it("送出後改 BO：每輪間隔的錯誤跟著重新檢查而消失；送出前不顯示錯誤", async () => {
    const user = userEvent.setup()
    mockCreate()
    await openCreatePage()
    await fillValidForm(user)
    // BO3：15＋3 × 40＋30 = 165
    await setNumber(user, "每輪間隔（分鐘）", "100")
    await user.click(screen.getByRole("combobox", { name: "BO" }))
    await user.click(await screen.findByRole("option", { name: "BO5" }))
    // 還沒送出過：改 BO 不會顯示每輪間隔的錯誤
    expect(fieldMessage("每輪間隔（分鐘）")).toBeNull()

    await user.click(screen.getByRole("button", { name: "建立賽事" }))
    await waitFor(() =>
      expect(fieldMessage("每輪間隔（分鐘）")).toBe("每輪間隔至少 245 分鐘"),
    )

    await user.click(screen.getByRole("combobox", { name: "BO" }))
    await user.click(await screen.findByRole("option", { name: "BO1" }))
    await waitFor(() => expect(fieldMessage("每輪間隔（分鐘）")).toBeNull())
  })

  it("連按「建立賽事」只呼叫一次 API", async () => {
    const user = userEvent.setup()
    const create = mockCreate()
    mockRead({ ...TOURNAMENT, id: "t-new" })
    await openCreatePage()
    await fillValidForm(user)

    await user.dblClick(screen.getByRole("button", { name: "建立賽事" }))

    await waitFor(() => expect(create).toHaveBeenCalledTimes(1))
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(create).toHaveBeenCalledTimes(1)
  })

  it("名額超過 128 時連按確認鈕只呼叫一次 API", async () => {
    const user = userEvent.setup()
    const create = mockCreate()
    mockRead({ ...TOURNAMENT, id: "t-new" })
    await openCreatePage()
    await fillValidForm(user, { capacity: "200" })

    await user.click(screen.getByRole("button", { name: "建立賽事" }))
    const dialog = await screen.findByRole("alertdialog")
    await user.dblClick(
      within(dialog).getByRole("button", { name: "建立賽事" }),
    )

    await waitFor(() => expect(create).toHaveBeenCalledTimes(1))
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(create).toHaveBeenCalledTimes(1)
  })

  it("報名截止晚於開賽：不送出，報名截止欄位顯示原因", async () => {
    const user = userEvent.setup()
    const create = mockCreate()
    await openCreatePage()
    await fillValidForm(user)
    setDateTime("報名截止", "2026-11-10T20:00")

    await user.click(screen.getByRole("button", { name: "建立賽事" }))

    await waitFor(() =>
      expect(fieldMessage("報名截止")).toBe("報名截止不能晚於開賽時間"),
    )
    expect(create).not.toHaveBeenCalled()
  })

  it("報名開始晚於截止、優先期超過截止：各自的欄位顯示原因", async () => {
    const user = userEvent.setup()
    const create = mockCreate()
    await openCreatePage()
    await fillValidForm(user)

    setDateTime("報名開始", "2026-11-09T23:00")
    await user.click(screen.getByRole("button", { name: "建立賽事" }))
    await waitFor(() =>
      expect(fieldMessage("報名開始")).toBe("報名開始必須早於報名截止"),
    )

    // 報名期間 10 小時、優先期 24 小時
    setDateTime("報名開始", "2026-11-09T13:00")
    await user.click(screen.getByRole("button", { name: "建立賽事" }))
    await waitFor(() =>
      expect(fieldMessage("優先期（小時）")).toBe(
        "優先期結束（報名開始＋優先期）不能晚於報名截止",
      ),
    )
    expect(fieldMessage("報名開始")).toBeNull()
    expect(create).not.toHaveBeenCalled()
  })

  it("送出後改日期：依賴的欄位跟著重新檢查，不必再送出", async () => {
    const user = userEvent.setup()
    const create = mockCreate()
    await openCreatePage()
    await fillValidForm(user)
    setDateTime("報名截止", "2026-11-10T20:00")
    await user.click(screen.getByRole("button", { name: "建立賽事" }))
    await waitFor(() =>
      expect(fieldMessage("報名截止")).toBe("報名截止不能晚於開賽時間"),
    )

    // 開賽時間 → 報名截止
    setDateTime("開賽時間", "2026-11-11T19:00")
    await waitFor(() => expect(fieldMessage("報名截止")).toBeNull())

    // 報名截止 → 報名開始
    setDateTime("報名截止", "2026-11-03T11:00")
    await waitFor(() =>
      expect(fieldMessage("報名開始")).toBe("報名開始必須早於報名截止"),
    )

    // 報名截止 → 報名開始、優先期（報名期間 1 小時、優先期 24 小時）
    setDateTime("報名截止", "2026-11-03T13:00")
    await waitFor(() => expect(fieldMessage("報名開始")).toBeNull())
    await waitFor(() =>
      expect(fieldMessage("優先期（小時）")).toBe(
        "優先期結束（報名開始＋優先期）不能晚於報名截止",
      ),
    )

    // 報名開始 → 優先期（報名期間改為 25 小時）
    setDateTime("報名開始", "2026-11-02T12:00")
    await waitFor(() => expect(fieldMessage("優先期（小時）")).toBeNull())
    expect(create).not.toHaveBeenCalled()
  })

  it("必填、整數與下限", async () => {
    const user = userEvent.setup()
    const create = mockCreate()
    await openCreatePage()

    await setNumber(user, "名額", "1")
    await setNumber(user, "棄權時限（分鐘）", "10")
    await setNumber(user, "申訴期（分鐘）", "")
    await user.click(screen.getByRole("button", { name: "建立賽事" }))

    await waitFor(() => expect(fieldMessage("賽事名稱")).toBe("請輸入賽事名稱"))
    expect(fieldMessage("名額")).toBe("名額不能小於 2")
    expect(fieldMessage("棄權時限（分鐘）")).toBe("棄權時限不能小於 15")
    expect(fieldMessage("申訴期（分鐘）")).toBe("請輸入申訴期")
    expect(fieldMessage("報名開始")).toBe("請輸入報名開始")
    expect(
      within(
        screen
          .getByRole("combobox", { name: "遊戲" })
          .closest("[data-slot=form-item]") as HTMLElement,
      ).getByText("請選擇遊戲"),
    ).toBeInTheDocument()
    expect(create).not.toHaveBeenCalled()
  })

  it("直播連結不是 http／https：不送出，欄位顯示原因", async () => {
    const user = userEvent.setup()
    const create = mockCreate()
    await openCreatePage()
    await fillValidForm(user)
    await user.type(screen.getByLabelText("直播連結（選填）"), "ftp://x")

    await user.click(screen.getByRole("button", { name: "建立賽事" }))

    await waitFor(() =>
      expect(fieldMessage("直播連結（選填）")).toBe(
        "直播連結必須是 http:// 或 https:// 開頭的網址",
      ),
    )
    expect(create).not.toHaveBeenCalled()
  })

  it("名額 200：先彈出提醒，按取消不送出，按確認才呼叫 API", async () => {
    const user = userEvent.setup()
    const create = mockCreate()
    await openCreatePage()
    await fillValidForm(user, { capacity: "200" })

    await user.click(screen.getByRole("button", { name: "建立賽事" }))
    let dialog = await screen.findByRole("alertdialog")
    expect(dialog).toHaveTextContent(CAPACITY_WARNING_TEXT)
    await user.click(within(dialog).getByRole("button", { name: "取消" }))
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull())
    expect(create).not.toHaveBeenCalled()

    await user.click(screen.getByRole("button", { name: "建立賽事" }))
    dialog = await screen.findByRole("alertdialog")
    await user.click(within(dialog).getByRole("button", { name: "建立賽事" }))

    await waitFor(() => expect(create).toHaveBeenCalledTimes(1))
    expect(create.mock.calls[0][0].body.capacity).toBe(200)
  })

  it("名額 128：不彈提醒，直接送出", async () => {
    const user = userEvent.setup()
    const create = mockCreate()
    await openCreatePage()
    await fillValidForm(user, { capacity: "128" })

    await user.click(screen.getByRole("button", { name: "建立賽事" }))

    await waitFor(() => expect(create).toHaveBeenCalledTimes(1))
    expect(screen.queryByRole("alertdialog")).toBeNull()
  })

  it("合法送出：時間轉成 UTC；成功 Toast 並導向 S27", async () => {
    const user = userEvent.setup()
    const success = vi.spyOn(toast, "success")
    const create = mockCreate()
    mockRead({ ...TOURNAMENT, id: "t-new" })
    const router = await openCreatePage()
    await fillValidForm(user)

    await user.click(screen.getByRole("button", { name: "建立賽事" }))

    await waitFor(() => expect(create).toHaveBeenCalledTimes(1))
    expect(create.mock.calls[0][0].body).toEqual({
      name: "臺大秋季盃",
      game_id: VALORANT.id,
      capacity: 32,
      starters: 5,
      substitutes: 1,
      bo: 3,
      registration_start: "2026-11-03T04:00:00.000Z",
      registration_end: "2026-11-09T15:00:00.000Z",
      priority_hours: 24,
      start_at: "2026-11-10T11:00:00.000Z",
      round_interval_minutes: 180,
      forfeit_minutes: 15,
      appeal_minutes: 30,
      livestream_url: null,
    })
    await waitFor(() =>
      expect(router.state.location.pathname).toBe(
        "/organizer/tournaments/t-new",
      ),
    )
    expect(success).toHaveBeenCalledWith(
      TOURNAMENT_CREATED_TEXT,
      expect.anything(),
    )
  })

  it("伺服器 422：寫回對應欄位", async () => {
    const user = userEvent.setup()
    vi.spyOn(TournamentsService, "createTournament").mockRejectedValue(
      httpError(422, {
        detail: [
          {
            loc: ["body", "registration_end"],
            msg: "報名截止必須晚於現在",
            type: "value_error",
          },
        ],
      }),
    )
    await openCreatePage()
    await fillValidForm(user)

    await user.click(screen.getByRole("button", { name: "建立賽事" }))

    await waitFor(() =>
      expect(fieldMessage("報名截止")).toBe("報名截止必須晚於現在"),
    )
    expect(screen.queryByRole("alert")).toBeNull()
  })

  it("伺服器 422 後修正欄位再送出：呼叫第二次並導向 S27", async () => {
    const user = userEvent.setup()
    const create = vi
      .spyOn(TournamentsService, "createTournament")
      .mockRejectedValueOnce(
        httpError(422, {
          detail: [
            {
              loc: ["body", "registration_end"],
              msg: "報名截止必須晚於現在",
              type: "value_error",
            },
          ],
        }),
      )
      .mockResolvedValue({ data: { ...TOURNAMENT, id: "t-new" } } as never)
    mockRead({ ...TOURNAMENT, id: "t-new" })
    const router = await openCreatePage()
    await fillValidForm(user)

    await user.click(screen.getByRole("button", { name: "建立賽事" }))
    await waitFor(() =>
      expect(fieldMessage("報名截止")).toBe("報名截止必須晚於現在"),
    )

    setDateTime("報名截止", "2026-11-09T22:00")
    await user.click(screen.getByRole("button", { name: "建立賽事" }))

    await waitFor(() => expect(create).toHaveBeenCalledTimes(2))
    await waitFor(() =>
      expect(router.state.location.pathname).toBe(
        "/organizer/tournaments/t-new",
      ),
    )
  })

  it("遊戲清單載入失敗：顯示錯誤，按「重新載入」重抓後可以選", async () => {
    const user = userEvent.setup()
    const games = vi
      .spyOn(TournamentsService, "listGamesForOrganizer")
      .mockRejectedValueOnce(httpError(500, "Internal Server Error"))
      .mockResolvedValue({ data: [VALORANT] } as ListGamesResult)
    signInAs({ account: ORGANIZER })
    renderApp("/organizer/tournaments/new")

    await user.click(await screen.findByRole("button", { name: "重新載入" }))

    await waitFor(() =>
      expect(screen.getByRole("combobox", { name: "遊戲" })).toBeEnabled(),
    )
    expect(screen.queryByRole("button", { name: "重新載入" })).toBeNull()
    expect(games).toHaveBeenCalledTimes(2)
    await chooseGame(user, "特戰英豪")
  })

  it("沒有可選的遊戲：顯示「目前沒有可選的遊戲」", async () => {
    mockGames([])
    signInAs({ account: ORGANIZER })
    renderApp("/organizer/tournaments/new")

    expect(
      await screen.findByText("目前沒有可選的遊戲，請聯絡平台管理員新增。"),
    ).toBeInTheDocument()
  })

  it("伺服器業務錯誤：表單頂部 Alert 顯示訊息", async () => {
    const user = userEvent.setup()
    vi.spyOn(TournamentsService, "createTournament").mockRejectedValue(
      httpError(404, {
        detail: { code: "GAME_NOT_FOUND", message: "找不到這款遊戲" },
      }),
    )
    await openCreatePage()
    await fillValidForm(user)

    await user.click(screen.getByRole("button", { name: "建立賽事" }))

    expect(await screen.findByRole("alert")).toHaveTextContent("找不到這款遊戲")
    // 遊戲可能剛被移除：重抓遊戲清單
    await waitFor(() =>
      expect(
        vi.mocked(TournamentsService.listGamesForOrganizer),
      ).toHaveBeenCalledTimes(2),
    )
  })
})

describe("S27 賽事總覽", () => {
  it("側欄「查看賽事頁」→ S2、「總覽」；徽章、模式與各項設定", async () => {
    mockRead()
    signInAs({ account: ORGANIZER })
    renderApp("/organizer/tournaments/t-1")

    expect(
      await screen.findByRole("heading", { name: "臺大秋季盃" }),
    ).toBeInTheDocument()
    const nav = within(sidebar()).getByRole("navigation", {
      name: "臺大秋季盃",
    })
    const links = within(nav).getAllByRole("link")
    expect(links.map((link) => link.textContent)).toEqual([
      "查看賽事頁",
      "總覽",
      "場次管理",
    ])
    expect(links[0]).toHaveAttribute("href", "/tournaments/t-1")
    expect(links[1]).toHaveAttribute("href", "/organizer/tournaments/t-1")
    expect(links[1]).toHaveAttribute("data-status", "active")
    expect(links[2]).toHaveAttribute(
      "href",
      "/organizer/tournaments/t-1/matches",
    )

    expect(screen.getByText("開放報名")).toHaveAttribute("data-tone", "live")
    const details = within(
      screen.getByText("模式").closest("dl") as HTMLElement,
    )
    const value = (term: string) =>
      details.getByText(term).nextElementSibling?.textContent
    expect(value("模式")).toBe("校園賽")
    expect(value("遊戲")).toBe("特戰英豪")
    expect(value("名額")).toBe("32 隊")
    // 年份與今天相同時不顯示年份，所以用同一個格式函式算期望值
    expect(value("報名期間")).toBe(
      `${formatMatchDateTime(TOURNAMENT.registration_start)} ～ ${formatMatchDateTime(TOURNAMENT.registration_end)}`,
    )
    expect(value("報名期間")).toContain("11/3（二）12:00")
    expect(value("優先期結束")).toBe(
      formatMatchDateTime(TOURNAMENT.priority_end),
    )
    expect(value("優先期結束")).toContain("11/4（三）12:00")
    expect(value("開賽時間")).toContain("11/10（二）19:00")
    expect(value("每輪間隔")).toBe("2 小時 30 分")
    expect(value("BO")).toBe("BO3")
    expect(value("先發／替補")).toBe("先發 5 人／替補 1 人")
    expect(value("棄權時限")).toBe("15 分鐘")
    expect(value("申訴期")).toBe("30 分鐘")
    expect(details.getByRole("link", { name: /twitch\.tv/ })).toHaveAttribute(
      "href",
      "https://twitch.tv/ntu",
    )
  })

  it("沒有直播連結時不顯示該列", async () => {
    mockRead({ ...TOURNAMENT, livestream_url: null })
    signInAs({ account: ORGANIZER })
    renderApp("/organizer/tournaments/t-1")

    await screen.findByRole("heading", { name: "臺大秋季盃" })
    expect(screen.queryByText("直播連結")).toBeNull()
  })

  it("別人的賽事（403）：S38 的 403", async () => {
    const read = vi
      .spyOn(TournamentsService, "readMyTournament")
      .mockRejectedValue(
        httpError(403, {
          detail: {
            code: "TOURNAMENT_OWNER_REQUIRED",
            message: "只有賽事主辦方可以執行這個操作",
          },
        }),
      )
    signInAs({ account: ORGANIZER })
    renderApp("/organizer/tournaments/t-9")

    expect(await forbiddenHeading()).toBeInTheDocument()
    // 403 不重試
    expect(read).toHaveBeenCalledTimes(1)
  })

  it("不存在（404）：404 頁", async () => {
    vi.spyOn(TournamentsService, "readMyTournament").mockRejectedValue(
      httpError(404, {
        detail: { code: "TOURNAMENT_NOT_FOUND", message: "找不到這場賽事" },
      }),
    )
    signInAs({ account: ORGANIZER })
    renderApp("/organizer/tournaments/t-9")

    expect(
      await screen.findByRole("heading", { name: "找不到這個頁面。" }),
    ).toBeInTheDocument()
  })
})

describe("S27 載入失敗", () => {
  it("非 403／404：重試後顯示錯誤，按「重新載入」重抓", async () => {
    // 登入與路由載入要靠真實時間推進，只把重試的等待時間快轉
    vi.useFakeTimers({
      toFake: ["setTimeout", "clearTimeout"],
      shouldAdvanceTime: true,
    })
    const read = vi
      .spyOn(TournamentsService, "readMyTournament")
      .mockRejectedValueOnce(httpError(500, "Internal Server Error"))
      .mockRejectedValueOnce(httpError(500, "Internal Server Error"))
      .mockRejectedValueOnce(httpError(500, "Internal Server Error"))
      .mockRejectedValueOnce(httpError(500, "Internal Server Error"))
      .mockResolvedValue({ data: TOURNAMENT } as ReadMineResult)
    signInAs({ account: ORGANIZER })
    try {
      renderApp("/organizer/tournaments/t-1")
      await waitFor(() => expect(read).toHaveBeenCalledTimes(1))

      // 沿用全站規則重試 3 次（間隔 1、2、4 秒）
      await act(async () => {
        await vi.advanceTimersByTimeAsync(10_000)
      })
    } finally {
      vi.useRealTimers()
    }
    expect(read).toHaveBeenCalledTimes(4)

    const user = userEvent.setup()
    await user.click(await screen.findByRole("button", { name: "重新載入" }))

    expect(
      await screen.findByRole("heading", { name: "臺大秋季盃" }),
    ).toBeInTheDocument()
    // 按下後重新取得（總覽掛上時會再取一次，所以不比對確切次數）
    expect(read.mock.calls.length).toBeGreaterThan(4)
  })
})

describe("權限與入口", () => {
  it.each([
    "/organizer",
    "/organizer/tournaments/new",
    "/organizer/tournaments/t-1",
  ])("一般帳號開 %s：S38 的 403，不呼叫主辦方 API", async (url) => {
    const mine = mockMine([])
    const games = mockGames()
    const read = mockRead()
    signInAs()
    renderApp(url)

    expect(await forbiddenHeading()).toBeInTheDocument()
    expect(mine).not.toHaveBeenCalled()
    expect(games).not.toHaveBeenCalled()
    expect(read).not.toHaveBeenCalled()
  })

  it.each(["/organizer/tournaments/new", "/organizer/tournaments/t-1"])(
    "未登入開 %s：導向 S6 並帶 redirect",
    async (url) => {
      const router = renderApp(url)

      await screen.findByRole("heading", { name: "登入" })
      expect(router.state.location.search).toEqual({ redirect: url })
    },
  )

  it("從身分切換器進入主辦方後台：到 S25", async () => {
    const user = userEvent.setup()
    mockMine([])
    signInAs({ account: ORGANIZER, identities: [BROWSE, ORGANIZER_IDENTITY] })
    const router = renderApp("/")

    const banner = await screen.findByRole("banner")
    await user.click(
      await within(banner).findByRole("button", { name: /切換身分（目前：/ }),
    )
    const menu = await screen.findByRole("menu")
    await user.click(within(menu).getByRole("menuitem", { name: "主辦方後台" }))

    await waitFor(() =>
      expect(router.state.location.pathname).toBe("/organizer"),
    )
    expect(
      await screen.findByRole("heading", { name: "我的賽事" }),
    ).toBeInTheDocument()
  })
})
