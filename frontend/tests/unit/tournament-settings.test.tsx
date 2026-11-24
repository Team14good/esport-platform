import { fireEvent, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { toast } from "sonner"
import { describe, expect, it, vi } from "vitest"

import {
  type GameRead,
  RegistrationService,
  type TournamentRead,
  type TournamentStatus,
  TournamentsService,
} from "@/client"
import {
  CAPACITY_RAISED_TEXT,
  NEW_CAPACITY_LABEL,
  NOT_EDITABLE_BANNER_TEXT,
  RAISE_CAPACITY_CONFIRM_TEXT,
  RAISE_CAPACITY_TEXT,
  SAVE_SETTINGS_TEXT,
  SETTINGS_LOCKED_BANNER_TEXT,
  SETTINGS_SAVED_TEXT,
  SETTINGS_TITLE,
  settingsMode,
  toSettingsValues,
  toTournamentUpdate,
} from "@/features/tournaments/TournamentSettingsPage"
import { ACCOUNT, renderApp, signInAs } from "./auth-fixtures"
import { httpError } from "./helpers"

vi.mock("@tanstack/react-router-devtools", () => ({
  TanStackRouterDevtools: () => null,
}))
vi.mock("@tanstack/react-query-devtools", () => ({
  ReactQueryDevtools: () => null,
}))

const ORGANIZER = { ...ACCOUNT, is_organizer: true }
const URL = "/organizer/tournaments/t-1/settings"

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
  // 台北時間 2026/11/03 12:00 ～ 2026/11/09 23:00，優先期 24 小時
  registration_start: "2026-11-03T04:00:00Z",
  priority_end: "2026-11-04T04:00:00Z",
  registration_end: "2026-11-09T15:00:00Z",
  // 台北時間 2026/11/10 19:00
  start_at: "2026-11-10T11:00:00Z",
  // 下限 15＋3×40＋30＝165
  round_interval_minutes: 180,
  forfeit_minutes: 15,
  appeal_minutes: 30,
  livestream_url: null,
  game_id: VALORANT.id,
  // 快照名稱（遊戲後來改名也照快照顯示）
  game_name: "特戰英豪（快照）",
  starters: 5,
  substitutes: 1,
  bo: 3,
  game_minutes: 40,
  score_type: "rounds",
  rank_tiers: [],
  round_bo: [],
}

type ReadResult = Awaited<
  ReturnType<typeof TournamentsService.readMyTournament>
>
type GamesResult = Awaited<
  ReturnType<typeof TournamentsService.listGamesForOrganizer>
>
type User = ReturnType<typeof userEvent.setup>

function tournamentIn(
  status: TournamentStatus,
  overrides: Partial<TournamentRead> = {},
): TournamentRead {
  return { ...TOURNAMENT, status, ...overrides }
}

async function open(tournament: TournamentRead) {
  const read = vi
    .spyOn(TournamentsService, "readMyTournament")
    .mockResolvedValue({ data: tournament } as ReadResult)
  vi.spyOn(TournamentsService, "listGamesForOrganizer").mockResolvedValue({
    data: [VALORANT, CHESS],
  } as GamesResult)
  signInAs({ account: ORGANIZER })
  renderApp(URL)
  await screen.findByRole("heading", { name: SETTINGS_TITLE })
  return read
}

function mockUpdate(result: (body: object) => TournamentRead) {
  return vi
    .spyOn(TournamentsService, "updateMyTournament")
    .mockImplementation(
      async (options) => ({ data: result(options.body as object) }) as never,
    )
}

/** 欄位下方的錯誤訊息（FormMessage）。 */
function fieldMessage(label: string): string | null {
  const input = screen.getByLabelText(label)
  const item = input.closest("[data-slot=form-item]") as HTMLElement
  return item.querySelector("[data-slot=form-message]")?.textContent ?? null
}

async function setNumber(user: User, label: string, value: string) {
  const input = screen.getByLabelText(label)
  await user.clear(input)
  if (value) await user.type(input, value)
}

function setDateTime(label: string, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } })
}

const ALL_FIELDS = [
  "賽事名稱",
  "名額",
  "先發人數",
  "替補人數",
  "報名開始",
  "報名截止",
  "優先期（小時）",
  "開賽時間",
  "每輪間隔（分鐘）",
  "棄權時限（分鐘）",
  "申訴期（分鐘）",
  "直播連結（選填）",
]

function enabledFields(): string[] {
  return ALL_FIELDS.filter((label) =>
    (screen.getByLabelText(label) as HTMLInputElement).matches(":enabled"),
  )
}

describe("S28 狀態與可修改的範圍", () => {
  it("依狀態決定可修改的範圍", () => {
    expect(settingsMode("upcoming")).toBe("full")
    expect(settingsMode("open")).toBe("relax")
    expect(settingsMode("closed")).toBe("relax")
    expect(settingsMode("published")).toBe("livestream")
    expect(settingsMode("ongoing")).toBe("livestream")
    expect(settingsMode("finished")).toBe("readonly")
    expect(settingsMode("cancelled")).toBe("readonly")
  })

  it("只送有變動且可修改的欄位；換遊戲時一併送出人數與 BO", () => {
    const initial = toSettingsValues(tournamentIn("upcoming"))
    expect(initial.registration_end).toBe("2026-11-09T23:00")
    expect(initial.priority_hours).toBe("24")

    expect(
      toTournamentUpdate(
        { ...initial, name: "新名稱", game_id: CHESS.id },
        initial,
        tournamentIn("upcoming"),
        "full",
      ),
    ).toEqual({
      name: "新名稱",
      game_id: CHESS.id,
      starters: 5,
      substitutes: 1,
      bo: 3,
    })
    // 開放報名後，鎖定的欄位就算被改了也不送
    expect(
      toTournamentUpdate(
        { ...initial, name: "新名稱", livestream_url: "" },
        initial,
        tournamentIn("open"),
        "relax",
      ),
    ).toEqual({})
    expect(
      toTournamentUpdate(
        { ...initial, round_bo: ["5"] },
        initial,
        tournamentIn("open"),
        "relax",
      ),
    ).toEqual({ round_bo: [{ rounds_from_final: 0, bo: 5 }] })
  })
})

describe("S28 賽事設定頁", () => {
  it("側欄有「設定」", async () => {
    await open(tournamentIn("open"))

    const sidebar = document.querySelector(
      "[data-slot=backoffice-sidebar]",
    ) as HTMLElement
    expect(within(sidebar).getByRole("link", { name: "設定" })).toHaveAttribute(
      "href",
      URL,
    )
  })

  it("尚未開放：全部欄位可改，名額可降低；儲存只送變動的欄位並顯示成功 Toast", async () => {
    const user = userEvent.setup()
    const success = vi.spyOn(toast, "success")
    const update = mockUpdate((body) => ({
      ...tournamentIn("upcoming"),
      ...body,
    }))
    await open(tournamentIn("upcoming"))

    expect(enabledFields()).toEqual(ALL_FIELDS)
    // 遊戲清單載入後選單才啟用
    await waitFor(() =>
      expect(screen.getByRole("combobox", { name: "遊戲" })).toBeEnabled(),
    )
    expect(
      screen.queryByRole("button", { name: RAISE_CAPACITY_TEXT }),
    ).not.toBeInTheDocument()
    await setNumber(user, "名額", "16")
    await user.click(screen.getByRole("button", { name: SAVE_SETTINGS_TEXT }))

    await waitFor(() => expect(update).toHaveBeenCalledTimes(1))
    expect(update.mock.calls[0][0]).toMatchObject({
      path: { tournament_id: "t-1" },
      body: { capacity: 16 },
    })
    await waitFor(() =>
      expect(success).toHaveBeenCalledWith(
        SETTINGS_SAVED_TEXT,
        expect.anything(),
      ),
    )
  })

  it("開放報名：只有放寬類欄位可改，遊戲唯讀，數字欄位下限為目前值", async () => {
    const user = userEvent.setup()
    const update = mockUpdate((body) => ({ ...tournamentIn("open"), ...body }))
    await open(tournamentIn("open", { forfeit_minutes: 20 }))

    expect(enabledFields()).toEqual([
      "報名截止",
      "每輪間隔（分鐘）",
      "棄權時限（分鐘）",
      "申訴期（分鐘）",
      "直播連結（選填）",
    ])
    expect(screen.getByRole("combobox", { name: "遊戲" })).toBeDisabled()
    expect(screen.getByRole("combobox", { name: "遊戲" })).toHaveTextContent(
      "特戰英豪（快照）",
    )
    expect(screen.getByLabelText("棄權時限（分鐘）")).toHaveAttribute(
      "min",
      "20",
    )
    expect(screen.getByLabelText("申訴期（分鐘）")).toHaveAttribute("min", "30")
    expect(screen.getByLabelText("報名截止")).toHaveAttribute(
      "min",
      "2026-11-09T23:00",
    )
    expect(screen.getByLabelText("報名截止")).toHaveAttribute(
      "max",
      // 必須早於開賽時間（台北 11/10 19:00）
      "2026-11-10T18:59",
    )

    setDateTime("報名截止", "2026-11-10T12:00")
    await user.click(screen.getByRole("button", { name: SAVE_SETTINGS_TEXT }))

    await waitFor(() => expect(update).toHaveBeenCalledTimes(1))
    expect(update.mock.calls[0][0]?.body).toEqual({
      registration_end: "2026-11-10T04:00:00.000Z",
    })
  })

  it("開放報名：縮短或間隔不足時在欄位顯示錯誤，不送出", async () => {
    const user = userEvent.setup()
    const update = mockUpdate(() => tournamentIn("open"))
    await open(
      tournamentIn("open", { appeal_minutes: 40, round_interval_minutes: 200 }),
    )

    await setNumber(user, "申訴期（分鐘）", "30")
    setDateTime("報名截止", "2026-11-09T22:00")
    await user.click(screen.getByRole("button", { name: SAVE_SETTINGS_TEXT }))

    await waitFor(() =>
      expect(fieldMessage("申訴期（分鐘）")).toBe("開放報名後申訴期只能延長"),
    )
    expect(fieldMessage("報名截止")).toBe("開放報名後報名截止只能延後")

    await setNumber(user, "申訴期（分鐘）", "70")
    setDateTime("報名截止", "2026-11-09T23:00")
    await user.click(screen.getByRole("button", { name: SAVE_SETTINGS_TEXT }))
    // 15＋120＋70＝205 > 200
    await waitFor(() =>
      expect(fieldMessage("每輪間隔（分鐘）")).toBe("每輪間隔至少 205 分鐘"),
    )
    expect(update).not.toHaveBeenCalled()
  })

  it("伺服器的 422 寫回對應欄位", async () => {
    const user = userEvent.setup()
    vi.spyOn(TournamentsService, "updateMyTournament").mockRejectedValue(
      httpError(422, {
        detail: [
          {
            type: "ROUND_INTERVAL_TOO_SHORT",
            loc: ["body", "round_interval_minutes"],
            msg: "每輪間隔至少 190 分鐘",
          },
        ],
      }),
    )
    await open(tournamentIn("open"))

    await setNumber(user, "棄權時限（分鐘）", "16")
    await user.click(screen.getByRole("button", { name: SAVE_SETTINGS_TEXT }))

    await waitFor(() =>
      expect(fieldMessage("每輪間隔（分鐘）")).toBe("每輪間隔至少 190 分鐘"),
    )
  })

  it("409 時在表單上方顯示伺服器訊息並重抓賽事", async () => {
    const user = userEvent.setup()
    vi.spyOn(TournamentsService, "updateMyTournament").mockRejectedValue(
      httpError(409, {
        detail: {
          code: "TOURNAMENT_SETTINGS_LOCKED",
          message: "抽籤後只能修改場次時間。",
        },
      }),
    )
    const read = await open(tournamentIn("open"))
    const readsBefore = read.mock.calls.length

    await setNumber(user, "棄權時限（分鐘）", "16")
    await user.click(screen.getByRole("button", { name: SAVE_SETTINGS_TEXT }))

    expect(
      await screen.findByText("抽籤後只能修改場次時間。"),
    ).toBeInTheDocument()
    await waitFor(() =>
      expect(read.mock.calls.length).toBeGreaterThan(readsBefore),
    )
  })

  it.each(["published", "ongoing"] as const)(
    "%s：頂部 banner，整頁唯讀只剩直播連結",
    async (status) => {
      const user = userEvent.setup()
      const update = mockUpdate((body) => ({
        ...tournamentIn(status),
        ...body,
      }))
      await open(tournamentIn(status))

      expect(screen.getByText(SETTINGS_LOCKED_BANNER_TEXT)).toBeInTheDocument()
      expect(enabledFields()).toEqual(["直播連結（選填）"])
      expect(
        screen.queryByRole("button", { name: RAISE_CAPACITY_TEXT }),
      ).not.toBeInTheDocument()

      await user.type(
        screen.getByLabelText("直播連結（選填）"),
        "https://twitch.tv/ntu",
      )
      await user.click(screen.getByRole("button", { name: SAVE_SETTINGS_TEXT }))

      await waitFor(() => expect(update).toHaveBeenCalledTimes(1))
      expect(update.mock.calls[0][0]?.body).toEqual({
        livestream_url: "https://twitch.tv/ntu",
      })
    },
  )

  it("抽籤後：直播連結不是 http／https 時在欄位顯示錯誤", async () => {
    const user = userEvent.setup()
    const update = mockUpdate(() => tournamentIn("published"))
    await open(tournamentIn("published"))

    await user.type(screen.getByLabelText("直播連結（選填）"), "ftp://a.tv")
    await user.click(screen.getByRole("button", { name: SAVE_SETTINGS_TEXT }))

    await waitFor(() =>
      expect(fieldMessage("直播連結（選填）")).toBe(
        "直播連結必須是 http:// 或 https:// 開頭的網址",
      ),
    )
    expect(update).not.toHaveBeenCalled()
  })

  it.each(["finished", "cancelled"] as const)(
    "%s：整頁唯讀，沒有儲存按鈕",
    async (status) => {
      await open(tournamentIn(status))

      expect(screen.getByText(NOT_EDITABLE_BANNER_TEXT)).toBeInTheDocument()
      expect(enabledFields()).toEqual([])
      expect(
        screen.queryByRole("button", { name: SAVE_SETTINGS_TEXT }),
      ).not.toBeInTheDocument()
    },
  )

  it("提高名額：確認對話框說明候補立即遞補，確認後經提高名額 API 送出", async () => {
    const user = userEvent.setup()
    const success = vi.spyOn(toast, "success")
    const raise = vi
      .spyOn(RegistrationService, "raiseCapacity")
      .mockResolvedValue({
        data: tournamentIn("open", { capacity: 40 }),
      } as never)
    const update = vi.spyOn(TournamentsService, "updateMyTournament")
    await open(tournamentIn("open"))

    await setNumber(user, NEW_CAPACITY_LABEL, "32")
    await user.click(screen.getByRole("button", { name: RAISE_CAPACITY_TEXT }))
    expect(
      await screen.findByText("新名額必須大於目前的名額（32 隊）。"),
    ).toBeInTheDocument()

    await setNumber(user, NEW_CAPACITY_LABEL, "40")
    await user.click(screen.getByRole("button", { name: RAISE_CAPACITY_TEXT }))
    const dialog = await screen.findByRole("alertdialog")
    expect(dialog).toHaveTextContent(RAISE_CAPACITY_CONFIRM_TEXT)
    await user.click(
      within(dialog).getByRole("button", { name: RAISE_CAPACITY_TEXT }),
    )

    await waitFor(() => expect(raise).toHaveBeenCalledTimes(1))
    expect(raise.mock.calls[0][0]).toMatchObject({
      path: { tournament_id: "t-1" },
      body: { capacity: 40 },
    })
    expect(update).not.toHaveBeenCalled()
    await waitFor(() =>
      expect(success).toHaveBeenCalledWith(
        CAPACITY_RAISED_TEXT,
        expect.anything(),
      ),
    )
    // 以回傳值更新畫面
    await waitFor(() => expect(screen.getByLabelText("名額")).toHaveValue(40))
  })
})

describe("S28 切換遊戲、重抓與提高名額失敗", () => {
  it("尚未開放：換遊戲後帶入新遊戲的人數與 BO，儲存時一併送出", async () => {
    const user = userEvent.setup()
    const update = mockUpdate((body) => ({
      ...tournamentIn("upcoming"),
      ...body,
    }))
    await open(tournamentIn("upcoming"))
    await waitFor(() =>
      expect(screen.getByRole("combobox", { name: "遊戲" })).toBeEnabled(),
    )

    await user.click(screen.getByRole("combobox", { name: "遊戲" }))
    await user.click(await screen.findByRole("option", { name: CHESS.name }))
    expect(screen.getByLabelText("先發人數")).toHaveValue(3)
    expect(screen.getByLabelText("替補人數")).toHaveValue(0)
    await user.click(screen.getByRole("button", { name: SAVE_SETTINGS_TEXT }))

    await waitFor(() => expect(update).toHaveBeenCalledTimes(1))
    expect(update.mock.calls[0][0]?.body).toEqual({
      game_id: CHESS.id,
      starters: 3,
      substitutes: 0,
      bo: 7,
    })
  })

  it("提高名額失敗時重抓賽事；內容相同的重抓不會清掉沒儲存的修改", async () => {
    const user = userEvent.setup()
    vi.spyOn(RegistrationService, "raiseCapacity").mockRejectedValue(
      httpError(409, {
        detail: {
          code: "CAPACITY_NOT_EDITABLE",
          message: "賽事抽籤後不能修改名額。",
        },
      }),
    )
    const read = await open(tournamentIn("open"))
    await setNumber(user, "棄權時限（分鐘）", "20")
    const readsBefore = read.mock.calls.length

    await setNumber(user, NEW_CAPACITY_LABEL, "40")
    await user.click(screen.getByRole("button", { name: RAISE_CAPACITY_TEXT }))
    const dialog = await screen.findByRole("alertdialog")
    await user.click(
      within(dialog).getByRole("button", { name: RAISE_CAPACITY_TEXT }),
    )

    expect(
      await within(dialog).findByText("賽事抽籤後不能修改名額。"),
    ).toBeInTheDocument()
    await waitFor(() =>
      expect(read.mock.calls.length).toBeGreaterThan(readsBefore),
    )
    // 重抓回來的資料相同：表單不重建，剛才的修改還在
    expect(screen.getByLabelText("棄權時限（分鐘）")).toHaveValue(20)
  })

  it("儲存失敗後提高名額成功，清除表單上方的錯誤", async () => {
    const user = userEvent.setup()
    vi.spyOn(TournamentsService, "updateMyTournament").mockRejectedValue(
      httpError(409, {
        detail: {
          code: "TOURNAMENT_SETTINGS_LOCKED",
          message: "抽籤後只能修改場次時間。",
        },
      }),
    )
    vi.spyOn(RegistrationService, "raiseCapacity").mockResolvedValue({
      data: tournamentIn("open", { capacity: 40 }),
    } as never)
    await open(tournamentIn("open"))

    await setNumber(user, "棄權時限（分鐘）", "16")
    await user.click(screen.getByRole("button", { name: SAVE_SETTINGS_TEXT }))
    expect(
      await screen.findByText("抽籤後只能修改場次時間。"),
    ).toBeInTheDocument()

    await setNumber(user, NEW_CAPACITY_LABEL, "40")
    await user.click(screen.getByRole("button", { name: RAISE_CAPACITY_TEXT }))
    const dialog = await screen.findByRole("alertdialog")
    await user.click(
      within(dialog).getByRole("button", { name: RAISE_CAPACITY_TEXT }),
    )

    await waitFor(() =>
      expect(
        screen.queryByText("抽籤後只能修改場次時間。"),
      ).not.toBeInTheDocument(),
    )
  })
})
