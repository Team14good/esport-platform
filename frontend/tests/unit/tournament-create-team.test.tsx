import { createMemoryHistory, createRouter } from "@tanstack/react-router"
import { screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeAll, describe, expect, it, vi } from "vitest"

import {
  type IdentityService,
  type MyTeamCard,
  type PublicTournament,
  RegistrationService,
  type TeamDetail,
  type TournamentRead,
  type TournamentStatus,
  TournamentsService,
} from "@/client"
import { routeTree } from "@/routeTree.gen"
import { ACCOUNT, renderApp, signInAs } from "./auth-fixtures"
import { httpError } from "./helpers"

vi.mock("@tanstack/react-router-devtools", () => ({
  TanStackRouterDevtools: () => null,
}))
vi.mock("@tanstack/react-query-devtools", () => ({
  ReactQueryDevtools: () => null,
}))

type ReadResult = Awaited<
  ReturnType<typeof TournamentsService.readPublicTournament>
>
type MyTournamentsResult = Awaited<
  ReturnType<typeof TournamentsService.listMyTournaments>
>
type MyTeamsResult = Awaited<ReturnType<typeof RegistrationService.listMyTeams>>
type CreateTeamResult = Awaited<
  ReturnType<typeof RegistrationService.createTeam>
>
type ReadTeamResult = Awaited<ReturnType<typeof RegistrationService.readTeam>>

const TOURNAMENT_ID = "t-1"

function tournament(status: TournamentStatus = "open"): PublicTournament {
  return {
    id: TOURNAMENT_ID,
    name: "期中盃",
    status,
    game_name: "特戰英豪",
    capacity: 16,
    // 報名截止在遠方未來，倒數不會歸零
    registration_start: "2026-01-01T11:00:00Z",
    priority_end: "2026-01-02T11:00:00Z",
    registration_end: "2099-01-01T11:00:00Z",
    start_at: "2099-01-02T11:00:00Z",
    round_interval_minutes: 180,
    livestream_url: null,
  }
}

const MY_TEAM: MyTeamCard = {
  team_id: "team-1",
  team_name: "夜貓隊",
  tournament_id: TOURNAMENT_ID,
  tournament_name: "期中盃",
  game_name: "特戰英豪",
  registration_status: "forming",
}

const TEAM: TeamDetail = {
  id: "team-new",
  name: "夜貓隊",
  tournament_id: TOURNAMENT_ID,
  tournament_name: "期中盃",
  game_name: "特戰英豪",
  starters: 5,
  substitutes: 1,
  max_members: 6,
  members: [
    {
      account_id: "acc-1",
      display_name: "小安",
      role: "captain",
      joined_at: "2026-11-02T10:00:00Z",
      game_account_id: null,
      rank_tier: null,
      rank_score: null,
      has_rank_screenshot: false,
      rank_screenshot_name: null,
      missing_fields: ["game_account_id", "rank_tier", "rank_screenshot"],
    },
  ],
  registration_status: "forming",
  invite_token: "tok-1",
  invite_status: "active",
  my_role: "captain",
  rank_tiers: [
    { name: "鑽石", score: 30 },
    { name: "黃金", score: 10 },
  ],
  avg_rank_score: null,
  rank_filled_count: 0,
  profile_editable: true,
}

function mockTournament(status: TournamentStatus = "open") {
  return vi
    .spyOn(TournamentsService, "readPublicTournament")
    .mockResolvedValue({ data: tournament(status) } as unknown as ReadResult)
}

function mockMyTeams(cards: MyTeamCard[] = []) {
  return vi
    .spyOn(RegistrationService, "listMyTeams")
    .mockResolvedValue({ data: cards } as MyTeamsResult)
}

function mockMyTournaments(ids: string[]) {
  return vi.spyOn(TournamentsService, "listMyTournaments").mockResolvedValue({
    data: ids.map((id) => ({ id }) as TournamentRead),
  } as MyTournamentsResult)
}

/** 等 S2 的報名截止倒數出現（總覽已渲染）。 */
async function waitForOverview() {
  expect(await screen.findByText("報名截止")).toBeInTheDocument()
}

// 先載入用到的路由（延遲載入），避免冷啟動轉譯超過 findBy 的等待時間
beforeAll(async () => {
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: ["/"] }),
  })
  await Promise.all([
    import("@/features/tournaments/TournamentPage"),
    router.loadRouteChunk(router.routesByPath["/teams/$teamId"]),
  ])
}, 30_000)

describe("S2 開放報名的「建立隊伍」入口", () => {
  it("已驗證、可建隊：開 S16，送出成功導向新隊伍的 S17", async () => {
    const user = userEvent.setup()
    signInAs()
    mockTournament()
    mockMyTeams()
    const myTournaments = vi.spyOn(TournamentsService, "listMyTournaments")
    const create = vi
      .spyOn(RegistrationService, "createTeam")
      .mockResolvedValue({ data: TEAM } as CreateTeamResult)
    vi.spyOn(RegistrationService, "readTeam").mockResolvedValue({
      data: TEAM,
    } as ReadTeamResult)
    const router = renderApp(`/tournaments/${TOURNAMENT_ID}`)

    const button = await screen.findByRole("button", { name: "建立隊伍" })
    await waitFor(() => expect(button).toBeEnabled())
    // 一般帳號不查主辦方賽事
    expect(myTournaments).not.toHaveBeenCalled()
    await user.click(button)
    const dialog = await screen.findByRole("dialog", { name: "建立隊伍" })
    await user.type(within(dialog).getByLabelText("隊名"), "夜貓隊")
    await user.click(within(dialog).getByRole("button", { name: "建立隊伍" }))

    await waitFor(() =>
      expect(router.state.location.pathname).toBe("/teams/team-new"),
    )
    expect(create).toHaveBeenCalledWith({
      path: { tournament_id: TOURNAMENT_ID },
      body: { name: "夜貓隊" },
    })
  })

  it("伺服器拒絕時在 Dialog 顯示原因", async () => {
    const user = userEvent.setup()
    signInAs()
    mockTournament()
    mockMyTeams()
    vi.spyOn(RegistrationService, "createTeam").mockRejectedValue(
      httpError(409, {
        detail: {
          code: "REGISTRATION_CLOSED",
          message: "這個賽事目前不開放報名。",
        },
      }),
    )
    renderApp(`/tournaments/${TOURNAMENT_ID}`)

    const button = await screen.findByRole("button", { name: "建立隊伍" })
    await waitFor(() => expect(button).toBeEnabled())
    await user.click(button)
    const dialog = await screen.findByRole("dialog", { name: "建立隊伍" })
    await user.type(within(dialog).getByLabelText("隊名"), "夜貓隊")
    await user.click(within(dialog).getByRole("button", { name: "建立隊伍" }))

    expect(
      await within(dialog).findByText("這個賽事目前不開放報名。"),
    ).toBeInTheDocument()
  })

  it("未登入：不顯示「建立隊伍」，也不查我的隊伍", async () => {
    mockTournament()
    const myTeams = mockMyTeams()
    renderApp(`/tournaments/${TOURNAMENT_ID}`)

    await waitForOverview()
    expect(screen.queryByRole("button", { name: "建立隊伍" })).toBeNull()
    expect(myTeams).not.toHaveBeenCalled()
  })

  it("Email 未驗證：按鈕停用並說明原因", async () => {
    signInAs({ account: { ...ACCOUNT, email_verified: false } })
    mockTournament()
    mockMyTeams()
    renderApp(`/tournaments/${TOURNAMENT_ID}`)

    expect(
      await screen.findByText("完成 Email 驗證後才能建立隊伍。"),
    ).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "建立隊伍" })).toBeDisabled()
  })

  it("本賽事的主辦方：不顯示「建立隊伍」", async () => {
    signInAs({ account: { ...ACCOUNT, is_organizer: true } })
    mockTournament()
    mockMyTeams()
    const myTournaments = mockMyTournaments(["t-other", TOURNAMENT_ID])
    renderApp(`/tournaments/${TOURNAMENT_ID}`)

    await waitForOverview()
    await waitFor(() => expect(myTournaments).toHaveBeenCalled())
    // 查詢完成後再確認一次，避免只是還在載入
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(screen.queryByRole("button", { name: "建立隊伍" })).toBeNull()
  })

  it("其他賽事的主辦方：照一般帳號顯示「建立隊伍」", async () => {
    signInAs({ account: { ...ACCOUNT, is_organizer: true } })
    mockTournament()
    mockMyTeams()
    mockMyTournaments(["t-other"])
    renderApp(`/tournaments/${TOURNAMENT_ID}`)

    const button = await screen.findByRole("button", { name: "建立隊伍" })
    await waitFor(() => expect(button).toBeEnabled())
  })

  it("已在本賽事有隊伍：顯示該隊的 Registration status card，點擊到 S17", async () => {
    signInAs()
    mockTournament()
    mockMyTeams([
      { ...MY_TEAM, team_id: "team-other", tournament_id: "t-other" },
      MY_TEAM,
    ])
    renderApp(`/tournaments/${TOURNAMENT_ID}`)

    const card = await screen.findByRole("link", { name: /夜貓隊/ })
    expect(card).toHaveAttribute("href", "/teams/team-1")
    expect(card).toHaveTextContent("組隊中")
    expect(screen.queryByRole("button", { name: "建立隊伍" })).toBeNull()
  })

  it("我的隊伍查詢失敗：不顯示「建立隊伍」，也不另外報錯", async () => {
    signInAs()
    mockTournament()
    const myTeams = vi
      .spyOn(RegistrationService, "listMyTeams")
      .mockRejectedValue(httpError(500, {}))
    renderApp(`/tournaments/${TOURNAMENT_ID}`)

    await waitForOverview()
    await waitFor(() => expect(myTeams).toHaveBeenCalled())
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(screen.queryByRole("button", { name: "建立隊伍" })).toBeNull()
    expect(screen.queryByRole("alert")).toBeNull()
  })

  it("主辦方賽事查詢失敗：不顯示「建立隊伍」", async () => {
    signInAs({ account: { ...ACCOUNT, is_organizer: true } })
    mockTournament()
    mockMyTeams()
    const myTournaments = vi
      .spyOn(TournamentsService, "listMyTournaments")
      .mockRejectedValue(httpError(500, {}))
    renderApp(`/tournaments/${TOURNAMENT_ID}`)

    await waitForOverview()
    await waitFor(() => expect(myTournaments).toHaveBeenCalled())
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(screen.queryByRole("button", { name: "建立隊伍" })).toBeNull()
  })

  it("資料載入中：不顯示「建立隊伍」", async () => {
    signInAs()
    mockTournament()
    // 永遠不回應
    vi.spyOn(RegistrationService, "listMyTeams").mockReturnValue(
      new Promise(() => {}) as ReturnType<
        typeof RegistrationService.listMyTeams
      >,
    )
    renderApp(`/tournaments/${TOURNAMENT_ID}`)

    await waitForOverview()
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(screen.queryByRole("button", { name: "建立隊伍" })).toBeNull()
  })

  it("主辦方賽事載入中：不顯示「建立隊伍」", async () => {
    signInAs({ account: { ...ACCOUNT, is_organizer: true } })
    mockTournament()
    mockMyTeams()
    // 永遠不回應
    const myTournaments = vi
      .spyOn(TournamentsService, "listMyTournaments")
      .mockReturnValue(
        new Promise(() => {}) as ReturnType<
          typeof TournamentsService.listMyTournaments
        >,
      )
    renderApp(`/tournaments/${TOURNAMENT_ID}`)

    await waitForOverview()
    await waitFor(() => expect(myTournaments).toHaveBeenCalled())
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(screen.queryByRole("button", { name: "建立隊伍" })).toBeNull()
  })

  it("目前帳號載入中：不顯示「建立隊伍」", async () => {
    const { readAccount } = signInAs()
    // 永遠不回應
    readAccount.mockReturnValue(
      new Promise(() => {}) as ReturnType<
        typeof IdentityService.readCurrentAccount
      >,
    )
    mockTournament()
    const myTeams = mockMyTeams()
    renderApp(`/tournaments/${TOURNAMENT_ID}`)

    await waitForOverview()
    await waitFor(() => expect(myTeams).toHaveBeenCalled())
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(screen.queryByRole("button", { name: "建立隊伍" })).toBeNull()
  })

  it("目前帳號查詢失敗：不顯示「建立隊伍」", async () => {
    const { readAccount } = signInAs()
    readAccount.mockRejectedValue(httpError(500, {}))
    mockTournament()
    const myTeams = mockMyTeams()
    renderApp(`/tournaments/${TOURNAMENT_ID}`)

    await waitForOverview()
    await waitFor(() => expect(readAccount).toHaveBeenCalled())
    await waitFor(() => expect(myTeams).toHaveBeenCalled())
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(screen.queryByRole("button", { name: "建立隊伍" })).toBeNull()
  })

  it("本賽事主辦方且已有本賽事隊伍：卡片優先，不顯示「建立隊伍」", async () => {
    signInAs({ account: { ...ACCOUNT, is_organizer: true } })
    mockTournament()
    mockMyTeams([MY_TEAM])
    mockMyTournaments([TOURNAMENT_ID])
    renderApp(`/tournaments/${TOURNAMENT_ID}`)

    const card = await screen.findByRole("link", { name: /夜貓隊/ })
    expect(card).toHaveAttribute("href", "/teams/team-1")
    expect(screen.queryByRole("button", { name: "建立隊伍" })).toBeNull()
  })

  it("報名截止（非開放報名）：維持 2.4 既有行為，不顯示入口", async () => {
    signInAs()
    mockTournament("closed")
    const myTeams = mockMyTeams()
    renderApp(`/tournaments/${TOURNAMENT_ID}`)

    expect(await screen.findByText("抽籤準備中")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "建立隊伍" })).toBeNull()
    expect(myTeams).not.toHaveBeenCalled()
  })
})
