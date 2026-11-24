import { createMemoryHistory, createRouter } from "@tanstack/react-router"
import { screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { toast } from "sonner"
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest"

import {
  CompetitionService,
  type GameRead,
  type PublicTournament,
  RegistrationService,
  type TournamentMode,
  type TournamentRead,
  TournamentsService,
} from "@/client"
import {
  INVITE_EXPIRED_TEXT,
  INVITE_MISSING_TEXT,
  INVITE_ONLY_TEXT,
  INVITE_SIGN_IN_TEXT,
  REGISTRATION_LINK_DESCRIPTION,
  REGISTRATION_LINK_LABEL,
  REGISTRATION_LINK_RESET_TEXT,
  RESET_REGISTRATION_LINK_CONFIRM_TEXT,
  RESET_REGISTRATION_LINK_TEXT,
  registrationLinkUrl,
} from "@/features/tournaments/registration-link"
import { SAVE_SETTINGS_TEXT } from "@/features/tournaments/TournamentSettingsPage"
import { routeTree } from "@/routeTree.gen"
import { ACCOUNT, renderApp, signInAs } from "./auth-fixtures"
import { httpError } from "./helpers"

// Story 3.10 第 2 部分：賽事模式選項與賽事報名連結（S1、S2、S27、S28）

vi.mock("@tanstack/react-router-devtools", () => ({
  TanStackRouterDevtools: () => null,
}))
vi.mock("@tanstack/react-query-devtools", () => ({
  ReactQueryDevtools: () => null,
}))

type Result<F extends (...args: never[]) => unknown> = Awaited<ReturnType<F>>

const ORGANIZER = { ...ACCOUNT, is_organizer: true }
const TOURNAMENT_ID = "t-1"
const TOKEN = "tok-1"

function publicTournament(
  overrides: Partial<PublicTournament> = {},
): PublicTournament {
  return {
    id: TOURNAMENT_ID,
    name: "校內盃",
    status: "open",
    mode: "custom",
    game_name: "英雄聯盟",
    capacity: 8,
    registration_start: "2026-01-01T11:00:00Z",
    priority_end: "2026-01-01T11:00:00Z",
    // 報名截止在遠方未來，倒數不會歸零
    registration_end: "2099-01-01T11:00:00Z",
    start_at: "2099-01-02T11:00:00Z",
    round_interval_minutes: 180,
    livestream_url: null,
    ...overrides,
  }
}

const GAME: GameRead = {
  id: "game-lol",
  name: "英雄聯盟",
  starters: 5,
  substitutes: 1,
  default_bo: 3,
  game_minutes: 40,
  score_type: "win_loss",
  rank_tiers: [],
}

function organizerTournament(
  overrides: Partial<TournamentRead> = {},
): TournamentRead {
  return {
    id: TOURNAMENT_ID,
    organizer_id: ORGANIZER.id,
    name: "校內盃",
    status: "upcoming",
    mode: "custom",
    capacity: 8,
    // 台北時間 2026/11/03 12:00 ～ 2026/11/09 23:00；自訂賽事優先期結束＝報名開始
    registration_start: "2026-11-03T04:00:00Z",
    priority_end: "2026-11-03T04:00:00Z",
    registration_end: "2026-11-09T15:00:00Z",
    start_at: "2026-11-10T11:00:00Z",
    round_interval_minutes: 180,
    forfeit_minutes: 15,
    appeal_minutes: 30,
    livestream_url: null,
    game_id: GAME.id,
    game_name: GAME.name,
    starters: 5,
    substitutes: 1,
    bo: 3,
    game_minutes: 40,
    score_type: "win_loss",
    rank_tiers: [],
    round_bo: [],
    ...overrides,
  }
}

beforeAll(async () => {
  // 先載入延遲載入的頁面，避免冷啟動轉譯超過 findBy 的等待時間
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: ["/"] }),
  })
  await Promise.all([
    import("@/features/tournaments/TournamentPage"),
    router.loadRouteChunk(router.routesByPath["/teams/$teamId"]),
  ])
}, 30_000)

beforeEach(() => {
  vi.spyOn(CompetitionService, "readDrawStatus").mockResolvedValue({
    data: { can_draw: false, reason: "not_drawable", expected_teams: null },
  } as Result<typeof CompetitionService.readDrawStatus>)
})

// ---------------------------------------------------------------- S1

describe("S1 邀請制報名標籤", () => {
  it("自訂賽事的卡片標「邀請制報名」，校園賽不標", async () => {
    vi.spyOn(TournamentsService, "listPublicTournaments").mockResolvedValue({
      data: [
        publicTournament({ id: "t-custom", name: "自訂盃" }),
        publicTournament({ id: "t-campus", name: "校園盃", mode: "campus" }),
      ],
    } as unknown as Result<typeof TournamentsService.listPublicTournaments>)
    renderApp("/")

    const custom = (await screen.findByText("自訂盃")).closest("a")
    const campus = screen.getByText("校園盃").closest("a")
    expect(
      within(custom as HTMLElement).getByText(INVITE_ONLY_TEXT),
    ).toBeVisible()
    expect(
      within(campus as HTMLElement).queryByText(INVITE_ONLY_TEXT),
    ).toBeNull()
  })
})

// ---------------------------------------------------------------- S2

function mockPublic(mode: TournamentMode = "custom") {
  vi.spyOn(TournamentsService, "readPublicTournament").mockResolvedValue({
    data: publicTournament({ mode }),
  } as unknown as Result<typeof TournamentsService.readPublicTournament>)
}

function mockMyTeams() {
  vi.spyOn(RegistrationService, "listMyTeams").mockResolvedValue({
    data: [],
  } as unknown as Result<typeof RegistrationService.listMyTeams>)
}

function mockLinkStatus(valid: boolean) {
  return vi
    .spyOn(TournamentsService, "readRegistrationLinkStatus")
    .mockResolvedValue({ data: { valid } } as Result<
      typeof TournamentsService.readRegistrationLinkStatus
    >)
}

async function waitForOverview() {
  expect(await screen.findByText("報名截止")).toBeInTheDocument()
}

async function settle() {
  await new Promise((resolve) => setTimeout(resolve, 50))
}

describe("S2 自訂賽事的建隊入口", () => {
  it("已登入、沒有帶連結：顯示索取連結的提示，沒有「建立隊伍」", async () => {
    signInAs()
    mockPublic()
    mockMyTeams()
    const status = mockLinkStatus(true)
    renderApp(`/tournaments/${TOURNAMENT_ID}`)

    expect(await screen.findByText(INVITE_MISSING_TEXT)).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "建立隊伍" })).toBeNull()
    expect(status).not.toHaveBeenCalled()
  })

  it("連結失效：顯示已失效的提示", async () => {
    signInAs()
    mockPublic()
    mockMyTeams()
    const status = mockLinkStatus(false)
    renderApp(`/tournaments/${TOURNAMENT_ID}?invite=wrong`)

    expect(await screen.findByText(INVITE_EXPIRED_TEXT)).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "建立隊伍" })).toBeNull()
    expect(status).toHaveBeenCalledWith({
      path: { tournament_id: TOURNAMENT_ID },
      query: { invite: "wrong" },
    })
  })

  it("帶有效連結：顯示「建立隊伍」，建隊時把 token 帶給後端", async () => {
    const user = userEvent.setup()
    signInAs()
    mockPublic()
    mockMyTeams()
    mockLinkStatus(true)
    // 不回應：只檢查送出的 body，不導向 S17
    const create = vi
      .spyOn(RegistrationService, "createTeam")
      .mockReturnValue(
        new Promise(() => {}) as ReturnType<
          typeof RegistrationService.createTeam
        >,
      )
    renderApp(`/tournaments/${TOURNAMENT_ID}?invite=${TOKEN}`)

    const button = await screen.findByRole("button", { name: "建立隊伍" })
    await waitFor(() => expect(button).toBeEnabled())
    await user.click(button)
    const dialog = await screen.findByRole("dialog", { name: "建立隊伍" })
    await user.type(within(dialog).getByLabelText("隊名"), "夜貓隊")
    await user.click(within(dialog).getByRole("button", { name: "建立隊伍" }))

    await waitFor(() => expect(create).toHaveBeenCalledTimes(1))
    expect(create).toHaveBeenCalledWith({
      path: { tournament_id: TOURNAMENT_ID },
      body: { name: "夜貓隊", invite_token: TOKEN },
    })
  })

  it("對話框開著時連結被重設：對話框顯示已失效的訊息", async () => {
    const user = userEvent.setup()
    signInAs()
    mockPublic()
    mockMyTeams()
    mockLinkStatus(true)
    vi.spyOn(RegistrationService, "createTeam").mockRejectedValue(
      httpError(403, {
        detail: {
          code: "TOURNAMENT_INVITE_REQUIRED",
          message: INVITE_EXPIRED_TEXT,
        },
      }),
    )
    renderApp(`/tournaments/${TOURNAMENT_ID}?invite=${TOKEN}`)

    const button = await screen.findByRole("button", { name: "建立隊伍" })
    await waitFor(() => expect(button).toBeEnabled())
    await user.click(button)
    const dialog = await screen.findByRole("dialog", { name: "建立隊伍" })
    await user.type(within(dialog).getByLabelText("隊名"), "夜貓隊")
    await user.click(within(dialog).getByRole("button", { name: "建立隊伍" }))

    expect(
      await within(dialog).findByText(INVITE_EXPIRED_TEXT),
    ).toBeInTheDocument()
  })

  it("Email 未驗證、帶有效連結：「建立隊伍」停用並說明（同校園賽）", async () => {
    signInAs({ account: { ...ACCOUNT, email_verified: false } })
    mockPublic()
    mockMyTeams()
    mockLinkStatus(true)
    renderApp(`/tournaments/${TOURNAMENT_ID}?invite=${TOKEN}`)

    expect(
      await screen.findByText("完成 Email 驗證後才能建立隊伍。"),
    ).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "建立隊伍" })).toBeDisabled()
  })

  it("未登入開連結：顯示「登入後即可建立隊伍。」，「登入」帶回含 invite 的網址", async () => {
    mockPublic()
    const status = mockLinkStatus(true)
    renderApp(`/tournaments/${TOURNAMENT_ID}?invite=${TOKEN}`)

    expect(await screen.findByText(INVITE_SIGN_IN_TEXT)).toBeInTheDocument()
    const login = screen
      .getAllByRole("link", { name: "登入" })
      .find((link) => link.getAttribute("href")?.includes("redirect"))
    expect(login).toBeDefined()
    const href = new URL(login?.getAttribute("href") ?? "", "http://localhost")
    expect(href.pathname).toBe("/login")
    expect(href.searchParams.get("redirect")).toBe(
      `/tournaments/${TOURNAMENT_ID}?invite=${TOKEN}`,
    )
    expect(status).not.toHaveBeenCalled()
  })

  it("未登入、沒有帶連結：顯示索取連結的提示，沒有「登入」提示", async () => {
    mockPublic()
    renderApp(`/tournaments/${TOURNAMENT_ID}`)

    await waitForOverview()
    expect(await screen.findByText(INVITE_MISSING_TEXT)).toBeInTheDocument()
    expect(screen.queryByText(INVITE_SIGN_IN_TEXT)).toBeNull()
    expect(screen.queryByRole("button", { name: "建立隊伍" })).toBeNull()
  })

  it("校園賽帶 invite：忽略參數，照常顯示「建立隊伍」且不帶 token", async () => {
    const user = userEvent.setup()
    signInAs()
    mockPublic("campus")
    mockMyTeams()
    const status = mockLinkStatus(false)
    const create = vi
      .spyOn(RegistrationService, "createTeam")
      .mockReturnValue(
        new Promise(() => {}) as ReturnType<
          typeof RegistrationService.createTeam
        >,
      )
    renderApp(`/tournaments/${TOURNAMENT_ID}?invite=anything`)

    const button = await screen.findByRole("button", { name: "建立隊伍" })
    await waitFor(() => expect(button).toBeEnabled())
    await user.click(button)
    const dialog = await screen.findByRole("dialog", { name: "建立隊伍" })
    await user.type(within(dialog).getByLabelText("隊名"), "夜貓隊")
    await user.click(within(dialog).getByRole("button", { name: "建立隊伍" }))

    await waitFor(() => expect(create).toHaveBeenCalledTimes(1))
    expect(create.mock.calls[0][0].body).toEqual({ name: "夜貓隊" })
    expect(status).not.toHaveBeenCalled()
  })

  it("本賽事的主辦方帶有效連結：不顯示「建立隊伍」也不顯示連結提示", async () => {
    signInAs({ account: ORGANIZER })
    mockPublic()
    mockMyTeams()
    mockLinkStatus(true)
    const myTournaments = vi
      .spyOn(TournamentsService, "listMyTournaments")
      .mockResolvedValue({
        data: [{ id: TOURNAMENT_ID } as TournamentRead],
      } as Result<typeof TournamentsService.listMyTournaments>)
    renderApp(`/tournaments/${TOURNAMENT_ID}?invite=${TOKEN}`)

    await waitForOverview()
    await waitFor(() => expect(myTournaments).toHaveBeenCalled())
    await settle()
    expect(screen.queryByRole("button", { name: "建立隊伍" })).toBeNull()
    expect(screen.queryByText(INVITE_EXPIRED_TEXT)).toBeNull()
    expect(screen.queryByText(INVITE_MISSING_TEXT)).toBeNull()
  })

  it("已在本賽事有隊伍、帶有效連結：顯示該隊的狀態卡，不顯示「建立隊伍」", async () => {
    signInAs()
    mockPublic()
    vi.spyOn(RegistrationService, "listMyTeams").mockResolvedValue({
      data: [
        {
          team_id: "team-1",
          team_name: "夜貓隊",
          tournament_id: TOURNAMENT_ID,
          tournament_name: "校內盃",
          game_name: "英雄聯盟",
          registration_status: "forming",
          waitlist_position: null,
          waitlist_reason: null,
          representative_backfill: null,
          waitlist_phase: null,
        },
      ],
    } as unknown as Result<typeof RegistrationService.listMyTeams>)
    mockLinkStatus(true)
    renderApp(`/tournaments/${TOURNAMENT_ID}?invite=${TOKEN}`)

    const card = await screen.findByRole("link", { name: /夜貓隊/ })
    expect(card).toHaveAttribute("href", "/teams/team-1")
    expect(screen.queryByRole("button", { name: "建立隊伍" })).toBeNull()
  })

  it("報名截止的自訂賽事帶連結：不顯示連結提示與「建立隊伍」（同校園賽）", async () => {
    signInAs()
    vi.spyOn(TournamentsService, "readPublicTournament").mockResolvedValue({
      data: publicTournament({ status: "closed" }),
    } as unknown as Result<typeof TournamentsService.readPublicTournament>)
    const myTeams = vi.spyOn(RegistrationService, "listMyTeams")
    myTeams.mockResolvedValue({ data: [] } as unknown as Result<
      typeof RegistrationService.listMyTeams
    >)
    mockLinkStatus(false)
    renderApp(`/tournaments/${TOURNAMENT_ID}?invite=${TOKEN}`)

    expect(await screen.findByText("抽籤準備中")).toBeInTheDocument()
    await waitFor(() => expect(myTeams).toHaveBeenCalled())
    await settle()
    expect(screen.queryByText(INVITE_EXPIRED_TEXT)).toBeNull()
    expect(screen.queryByText(INVITE_MISSING_TEXT)).toBeNull()
    expect(screen.queryByRole("button", { name: "建立隊伍" })).toBeNull()
  })

  it("尚未開放的自訂賽事：不顯示連結提示（同校園賽）", async () => {
    signInAs()
    vi.spyOn(TournamentsService, "readPublicTournament").mockResolvedValue({
      data: publicTournament({
        status: "upcoming",
        registration_start: "2099-01-01T00:00:00Z",
      }),
    } as unknown as Result<typeof TournamentsService.readPublicTournament>)
    mockMyTeams()
    renderApp(`/tournaments/${TOURNAMENT_ID}`)

    expect(await screen.findByText("報名開始")).toBeInTheDocument()
    await settle()
    expect(screen.queryByText(INVITE_MISSING_TEXT)).toBeNull()
  })
})

// ---------------------------------------------------------------- S27

function mockMine(tournament: TournamentRead) {
  vi.spyOn(TournamentsService, "readMyTournament").mockResolvedValue({
    data: tournament,
  } as Result<typeof TournamentsService.readMyTournament>)
}

describe("S27 賽事報名連結", () => {
  it("自訂賽事：顯示可複製的連結與說明；重設後換成新連結並顯示 Toast", async () => {
    const user = userEvent.setup()
    const success = vi.spyOn(toast, "success")
    mockMine(organizerTournament())
    vi.spyOn(TournamentsService, "readRegistrationLink").mockResolvedValue({
      data: { tournament_id: TOURNAMENT_ID, invite_token: TOKEN },
    } as Result<typeof TournamentsService.readRegistrationLink>)
    const reset = vi
      .spyOn(TournamentsService, "resetRegistrationLink")
      .mockResolvedValue({
        data: { tournament_id: TOURNAMENT_ID, invite_token: "tok-2" },
      } as Result<typeof TournamentsService.resetRegistrationLink>)
    signInAs({ account: ORGANIZER })
    renderApp(`/organizer/tournaments/${TOURNAMENT_ID}`)

    const field = await screen.findByRole("textbox", {
      name: REGISTRATION_LINK_LABEL,
    })
    expect(field).toHaveValue(registrationLinkUrl(TOURNAMENT_ID, TOKEN))
    expect(screen.getByText(REGISTRATION_LINK_DESCRIPTION)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "複製連結" })).toBeEnabled()

    await user.click(
      screen.getByRole("button", { name: RESET_REGISTRATION_LINK_TEXT }),
    )
    const dialog = await screen.findByRole("alertdialog", {
      name: RESET_REGISTRATION_LINK_TEXT,
    })
    expect(
      within(dialog).getByText(RESET_REGISTRATION_LINK_CONFIRM_TEXT),
    ).toBeInTheDocument()
    await user.click(
      within(dialog).getByRole("button", {
        name: RESET_REGISTRATION_LINK_TEXT,
      }),
    )

    await waitFor(() => expect(reset).toHaveBeenCalledTimes(1))
    await waitFor(() =>
      expect(
        screen.getByRole("textbox", { name: REGISTRATION_LINK_LABEL }),
      ).toHaveValue(registrationLinkUrl(TOURNAMENT_ID, "tok-2")),
    )
    expect(success).toHaveBeenCalledWith(
      REGISTRATION_LINK_RESET_TEXT,
      expect.anything(),
    )
  })

  it.each(["cancelled", "finished"] as const)(
    "%s 的自訂賽事：不顯示賽事報名連結，也不查詢",
    async (status) => {
      mockMine(organizerTournament({ status }))
      const read = vi.spyOn(TournamentsService, "readRegistrationLink")
      signInAs({ account: ORGANIZER })
      renderApp(`/organizer/tournaments/${TOURNAMENT_ID}`)

      await screen.findByRole("heading", { name: "校內盃" })
      await settle()
      expect(
        screen.queryByRole("textbox", { name: REGISTRATION_LINK_LABEL }),
      ).toBeNull()
      expect(read).not.toHaveBeenCalled()
    },
  )

  it("自訂賽事的摘要不顯示「優先期結束」", async () => {
    vi.spyOn(TournamentsService, "readRegistrationLink").mockResolvedValue({
      data: { tournament_id: TOURNAMENT_ID, invite_token: TOKEN },
    } as Result<typeof TournamentsService.readRegistrationLink>)
    mockMine(organizerTournament({ status: "open" }))
    signInAs({ account: ORGANIZER })
    renderApp(`/organizer/tournaments/${TOURNAMENT_ID}`)

    await screen.findByRole("heading", { name: "校內盃" })
    expect(screen.getByText("報名期間")).toBeInTheDocument()
    expect(screen.queryByText("優先期結束")).toBeNull()
  })

  it("校園賽的摘要照常顯示「優先期結束」", async () => {
    signInAs({ account: ORGANIZER })
    mockMine(
      organizerTournament({
        status: "open",
        mode: "campus",
        priority_end: "2099-01-01T00:00:00Z",
      }),
    )
    renderApp(`/organizer/tournaments/${TOURNAMENT_ID}`)
    await screen.findByRole("heading", { name: "校內盃" })
    expect(screen.getAllByText("優先期結束").length).toBeGreaterThan(0)
  })

  it("校園賽：不顯示賽事報名連結，也不查詢", async () => {
    mockMine(organizerTournament({ mode: "campus" }))
    const read = vi.spyOn(TournamentsService, "readRegistrationLink")
    signInAs({ account: ORGANIZER })
    renderApp(`/organizer/tournaments/${TOURNAMENT_ID}`)

    await screen.findByRole("heading", { name: "校內盃" })
    await settle()
    expect(
      screen.queryByRole("textbox", { name: REGISTRATION_LINK_LABEL }),
    ).toBeNull()
    expect(read).not.toHaveBeenCalled()
  })
})

// ---------------------------------------------------------------- S28

async function openSettings(tournament: TournamentRead) {
  mockMine(tournament)
  vi.spyOn(TournamentsService, "listGamesForOrganizer").mockResolvedValue({
    data: [GAME],
  } as Result<typeof TournamentsService.listGamesForOrganizer>)
  const update = vi
    .spyOn(TournamentsService, "updateMyTournament")
    .mockImplementation(
      async (options) =>
        ({ data: { ...tournament, ...(options.body as object) } }) as never,
    )
  signInAs({ account: ORGANIZER })
  renderApp(`/organizer/tournaments/${TOURNAMENT_ID}/settings`)
  await screen.findByRole("heading", { name: "賽事設定" })
  return update
}

async function chooseMode(
  user: ReturnType<typeof userEvent.setup>,
  name: string,
) {
  await user.click(screen.getByRole("combobox", { name: "賽事模式" }))
  await user.click(await screen.findByRole("option", { name }))
}

describe("S28 切換賽事模式", () => {
  it("尚未開放，校園賽→自訂：優先期欄位隱藏，送出 mode 與優先期 0", async () => {
    const user = userEvent.setup()
    const update = await openSettings(
      organizerTournament({
        mode: "campus",
        priority_end: "2026-11-04T04:00:00Z",
      }),
    )
    expect(screen.getByLabelText("優先期（小時）")).toHaveValue(24)

    await chooseMode(user, "自訂")
    expect(screen.queryByLabelText("優先期（小時）")).toBeNull()
    await user.click(screen.getByRole("button", { name: SAVE_SETTINGS_TEXT }))

    await waitFor(() => expect(update).toHaveBeenCalledTimes(1))
    expect(update.mock.calls[0][0].body).toEqual({
      mode: "custom",
      priority_hours: 0,
    })
  })

  it("尚未開放，自訂→校園賽：優先期欄位出現並預填 24，可修改", async () => {
    const user = userEvent.setup()
    const update = await openSettings(organizerTournament())
    expect(screen.queryByLabelText("優先期（小時）")).toBeNull()

    await chooseMode(user, "校園賽")
    const priority = screen.getByLabelText("優先期（小時）")
    expect(priority).toHaveValue(24)
    await user.clear(priority)
    await user.type(priority, "12")
    await user.click(screen.getByRole("button", { name: SAVE_SETTINGS_TEXT }))

    await waitFor(() => expect(update).toHaveBeenCalledTimes(1))
    expect(update.mock.calls[0][0].body).toEqual({
      mode: "campus",
      priority_hours: 12,
    })
  })

  it("校園賽（優先期 48）切自訂再切回：還原原本的優先期，不送出模式與優先期", async () => {
    const user = userEvent.setup()
    const update = await openSettings(
      organizerTournament({
        mode: "campus",
        priority_end: "2026-11-05T04:00:00Z",
      }),
    )
    expect(screen.getByLabelText("優先期（小時）")).toHaveValue(48)

    await chooseMode(user, "自訂")
    await chooseMode(user, "校園賽")
    expect(screen.getByLabelText("優先期（小時）")).toHaveValue(48)
    const name = screen.getByLabelText("賽事名稱")
    await user.clear(name)
    await user.type(name, "改名盃")
    await user.click(screen.getByRole("button", { name: SAVE_SETTINGS_TEXT }))

    await waitFor(() => expect(update).toHaveBeenCalledTimes(1))
    expect(update.mock.calls[0][0].body).toEqual({ name: "改名盃" })
  })

  it("開放報名後：賽事模式唯讀", async () => {
    await openSettings(organizerTournament({ status: "open" }))

    expect(screen.getByRole("combobox", { name: "賽事模式" })).toBeDisabled()
    expect(
      screen.getByRole("combobox", { name: "賽事模式" }),
    ).toHaveTextContent("自訂")
  })
})
