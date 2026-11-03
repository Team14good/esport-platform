import { createMemoryHistory, createRouter } from "@tanstack/react-router"
import { screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { toast } from "sonner"
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest"

import {
  type Identity,
  type MyTeamCard,
  RegistrationService,
  type TeamDetail,
  type TeamInvitePreview,
  type TeamMemberRead,
} from "@/client"
import { routeTree } from "@/routeTree.gen"
import { ACCOUNT, BROWSE, renderApp, signInAs } from "./auth-fixtures"
import { httpError } from "./helpers"

vi.mock("@tanstack/react-router-devtools", () => ({
  TanStackRouterDevtools: () => null,
}))
vi.mock("@tanstack/react-query-devtools", () => ({
  ReactQueryDevtools: () => null,
}))

type ReadTeamResult = Awaited<ReturnType<typeof RegistrationService.readTeam>>
type PreviewResult = Awaited<
  ReturnType<typeof RegistrationService.previewTeamInvite>
>
type JoinResult = Awaited<ReturnType<typeof RegistrationService.joinTeam>>
type MyTeamsResult = Awaited<ReturnType<typeof RegistrationService.listMyTeams>>
type UpdateProfileResult = Awaited<
  ReturnType<typeof RegistrationService.updateMyPlayerProfile>
>

const MY_TEAMS: Identity = {
  key: "my_teams",
  label: "我的隊伍",
  home_path: "/me/teams",
}

const member = (
  id: string,
  name: string,
  role: "captain" | "player" = "player",
  profile: Partial<TeamMemberRead> = {},
): TeamMemberRead => ({
  account_id: id,
  display_name: name,
  role,
  joined_at: "2026-10-30T10:00:00Z",
  game_account_id: null,
  rank_tier: null,
  rank_score: null,
  has_rank_screenshot: false,
  rank_screenshot_name: null,
  missing_fields: ["game_account_id", "rank_tier", "rank_screenshot"],
  ...profile,
})

/** 已填完參賽資料的隊員（`screenshotName` 只有本人看得到）。 */
const filled = (
  id: string,
  name: string,
  rankTier: string,
  rankScore: number,
  role: "captain" | "player" = "player",
  screenshotName: string | null = null,
) =>
  member(id, name, role, {
    game_account_id: `${name}#TW`,
    rank_tier: rankTier,
    rank_score: rankScore,
    has_rank_screenshot: true,
    rank_screenshot_name: screenshotName,
    missing_fields: [],
  })

const TEAM: TeamDetail = {
  id: "team-1",
  name: "夜貓隊",
  tournament_id: "tour-1",
  tournament_name: "政大校園盃",
  game_name: "特戰英豪",
  starters: 5,
  substitutes: 1,
  max_members: 6,
  members: [
    member("acc-1", "阿哲", "captain"),
    member("acc-2", "小芸"),
    member("acc-3", "阿凱"),
    member("acc-4", "小晴"),
  ],
  registration_status: "forming",
  invite_token: "tok-1",
  invite_status: "active",
  my_role: "player",
  rank_tiers: [
    { name: "鑽石", score: 30 },
    { name: "黃金", score: 10 },
  ],
  avg_rank_score: null,
  rank_filled_count: 0,
  profile_editable: true,
}

const INVITE: TeamInvitePreview = {
  team_id: "team-1",
  team_name: "夜貓隊",
  tournament_id: "tour-1",
  tournament_name: "政大校園盃",
  game_name: "特戰英豪",
  member_count: 4,
  max_members: 6,
  invite_status: "active",
}

function mockReadTeam(team: TeamDetail = TEAM) {
  return vi
    .spyOn(RegistrationService, "readTeam")
    .mockResolvedValue({ data: team } as ReadTeamResult)
}

function mockPreview(invite: TeamInvitePreview = INVITE) {
  return vi
    .spyOn(RegistrationService, "previewTeamInvite")
    .mockResolvedValue({ data: invite } as PreviewResult)
}

// 路由以 autoCodeSplitting 延遲載入：第一次進入某個路由時，Vite 才轉譯它的元件，
// 冷啟動時常要將近 1 秒，偶爾超過 findBy 預設的 1000 ms，使該路由的第一個測試失敗。
// 先載入本檔用到的路由，讓每個測試只等待畫面本身。
beforeAll(async () => {
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: ["/"] }),
  })
  await Promise.all(
    (["/teams/$teamId", "/join/$inviteToken", "/me/teams"] as const).map(
      (path) => router.loadRouteChunk(router.routesByPath[path]),
    ),
  )
}, 30_000)

beforeEach(() => {
  // S17 會渲染 S18；jsdom 沒有 matchMedia，useIsMobile 只用它監聽變化，寬度看 innerWidth
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }))
  URL.createObjectURL = vi.fn(() => "blob:preview")
  URL.revokeObjectURL = vi.fn()
})

describe("隊伍頁（S17）", () => {
  it("隊員檢視：名單、隊長徽章、人數與邀請連結", async () => {
    signInAs()
    const read = mockReadTeam()
    renderApp("/teams/team-1")

    expect(
      await screen.findByRole("heading", { name: "夜貓隊" }),
    ).toBeInTheDocument()
    expect(read).toHaveBeenCalledWith({ path: { team_id: "team-1" } })
    expect(screen.getByText("政大校園盃 · 特戰英豪")).toBeInTheDocument()
    expect(screen.getByText("組隊中")).toBeInTheDocument()

    const rows = within(
      screen.getByRole("list", { name: "隊伍名單" }),
    ).getAllByRole("listitem")
    expect(rows).toHaveLength(4)
    expect(within(rows[0]).getByText("隊長")).toBeInTheDocument()
    expect(screen.getByText("4／6 人（先發 5）")).toBeInTheDocument()

    expect(screen.getByLabelText("隊伍邀請連結")).toHaveValue(
      `${window.location.origin}/join/tok-1`,
    )
    expect(screen.getByRole("button", { name: "複製連結" })).toBeEnabled()
  })

  it("額滿時邀請連結顯示「連結已失效」與原因「隊伍已滿」", async () => {
    signInAs()
    mockReadTeam({
      ...TEAM,
      max_members: 4,
      substitutes: 0,
      starters: 4,
      invite_status: "full",
    })
    renderApp("/teams/team-1")

    expect(await screen.findByText("連結已失效")).toBeInTheDocument()
    expect(screen.getByText(/隊伍已滿/)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "複製連結" })).toBeDisabled()
  })

  it("非隊員：顯示沒有權限", async () => {
    signInAs()
    vi.spyOn(RegistrationService, "readTeam").mockRejectedValue(
      httpError(403, {
        detail: {
          code: "TEAM_MEMBER_REQUIRED",
          message: "只有隊員可以查看這支隊伍。",
        },
      }),
    )
    renderApp("/teams/team-1")

    expect(
      await screen.findByText("你沒有權限查看這個頁面。"),
    ).toBeInTheDocument()
  })

  it("未登入：導向登入並帶 redirect 回隊伍頁", async () => {
    const router = renderApp("/teams/team-1")

    await waitFor(() => expect(router.state.location.pathname).toBe("/login"))
    expect(router.state.location.search).toEqual({ redirect: "/teams/team-1" })
  })
})

describe("隊伍頁的參賽資料（S17、S18）", () => {
  // 目前帳號是 acc-1（auth-fixtures 的 ACCOUNT）
  const PARTIAL: TeamDetail = {
    ...TEAM,
    members: [
      member("acc-1", "阿哲", "captain"),
      filled("acc-2", "小芸", "鑽石", 30),
      member("acc-3", "阿凱", "player", {
        game_account_id: "Kai#TW",
        rank_tier: "黃金",
        rank_score: 10,
        missing_fields: ["rank_screenshot"],
      }),
      member("acc-4", "小晴", "player", {
        has_rank_screenshot: true,
        missing_fields: ["game_account_id", "rank_tier"],
      }),
    ],
    avg_rank_score: 20,
    rank_filled_count: 2,
  }

  function rows() {
    return within(screen.getByRole("list", { name: "隊伍名單" })).getAllByRole(
      "listitem",
    )
  }

  it("每列顯示已填資料與完成度，只有自己那列有「填寫我的資料」", async () => {
    signInAs()
    mockReadTeam(PARTIAL)
    renderApp("/teams/team-1")

    expect(await screen.findByText("小芸")).toBeInTheDocument()
    const [mine, complete, noScreenshot, onlyScreenshot] = rows()
    expect(within(mine).getByText("缺：遊戲 ID、段位、段位截圖")).toHaveClass(
      "text-muted-foreground",
    )
    expect(
      within(complete).getByText("小芸#TW · 鑽石 · 段位截圖：已上傳"),
    ).toBeInTheDocument()
    expect(within(complete).getByText("資料完成")).toHaveClass(
      "text-status-confirmed",
    )
    expect(within(noScreenshot).getByText("Kai#TW · 黃金")).toBeInTheDocument()
    expect(within(noScreenshot).getByText("缺：段位截圖")).toBeInTheDocument()
    expect(
      within(onlyScreenshot).getByText("段位截圖：已上傳"),
    ).toBeInTheDocument()
    expect(
      within(onlyScreenshot).getByText("缺：遊戲 ID、段位"),
    ).toBeInTheDocument()

    expect(
      await within(mine).findByRole("button", { name: "填寫我的資料" }),
    ).toBeInTheDocument()
    expect(
      screen.getAllByRole("button", { name: "填寫我的資料" }),
    ).toHaveLength(1)
    expect(
      screen.getByText("平均段位積分 20.00（2／4 人已填）"),
    ).toBeInTheDocument()
  })

  it("全員填完時平均段位積分不註明人數", async () => {
    signInAs()
    mockReadTeam({
      ...TEAM,
      members: [
        filled("acc-1", "阿哲", "鑽石", 30, "captain"),
        filled("acc-2", "小芸", "鑽石", 30),
        filled("acc-3", "阿凱", "黃金", 10),
      ],
      avg_rank_score: 23.33,
      rank_filled_count: 3,
    })
    renderApp("/teams/team-1")

    expect(await screen.findByText("平均段位積分 23.33")).toBeInTheDocument()
  })

  it("開 S18：段位來自對照表；儲存後關閉、名單更新並 Toast「已儲存參賽資料」", async () => {
    const user = userEvent.setup()
    const success = vi.spyOn(toast, "success")
    signInAs()
    mockReadTeam(PARTIAL)
    const saved: TeamDetail = {
      ...PARTIAL,
      members: [
        filled("acc-1", "阿哲", "鑽石", 30, "captain", "rank.png"),
        ...PARTIAL.members.slice(1),
      ],
      avg_rank_score: 23.33,
      rank_filled_count: 3,
    }
    const progress: number[] = []
    const update = vi
      .spyOn(RegistrationService, "updateMyPlayerProfile")
      .mockImplementation(async (options) => {
        options.onUploadProgress?.({
          loaded: 1,
          total: 2,
          bytes: 1,
          lengthComputable: true,
        })
        // 進度回報後，畫面上的百分比
        await waitFor(() =>
          expect(screen.getByText("上傳中 50%")).toBeInTheDocument(),
        )
        progress.push(50)
        // mockImplementation 的型別涵蓋 throwOnError 為 false 的回傳，直接轉型
        return { data: saved } as never
      })
    renderApp("/teams/team-1")

    await user.click(
      await screen.findByRole("button", { name: "填寫我的資料" }),
    )
    const dialog = await screen.findByTestId("player-profile-dialog")
    await user.type(within(dialog).getByLabelText("遊戲 ID"), "阿哲#TW")
    await user.click(within(dialog).getByRole("combobox", { name: "段位" }))
    const options = await screen.findAllByRole("option")
    expect(options.map((option) => option.textContent)).toEqual([
      "鑽石",
      "黃金",
    ])
    await user.click(screen.getByRole("option", { name: "鑽石" }))
    const screenshot = new File(["png"], "rank.png", { type: "image/png" })
    await user.upload(within(dialog).getByLabelText("段位截圖"), screenshot)
    await user.click(within(dialog).getByRole("button", { name: "儲存資料" }))

    await waitFor(() =>
      expect(screen.queryByTestId("player-profile-dialog")).toBeNull(),
    )
    expect(progress).toEqual([50])
    expect(update).toHaveBeenCalledWith(
      expect.objectContaining({
        path: { team_id: "team-1" },
        body: {
          game_account_id: "阿哲#TW",
          rank_tier: "鑽石",
          rank_screenshot: screenshot,
        },
        onUploadProgress: expect.any(Function),
      }),
    )
    expect(success).toHaveBeenCalledWith("已儲存參賽資料", expect.anything())
    expect(within(rows()[0]).getByText("資料完成")).toBeInTheDocument()
    expect(
      screen.getByText("平均段位積分 23.33（3／4 人已填）"),
    ).toBeInTheDocument()
  })

  it("已上傳截圖時重開 S18 只顯示檔名，不換圖也能儲存", async () => {
    const user = userEvent.setup()
    signInAs()
    const mine = filled("acc-1", "阿哲", "黃金", 10, "captain", "old.png")
    mockReadTeam({ ...TEAM, members: [mine] })
    const update = vi
      .spyOn(RegistrationService, "updateMyPlayerProfile")
      .mockResolvedValue({
        data: { ...TEAM, members: [mine] },
      } as UpdateProfileResult)
    renderApp("/teams/team-1")

    await user.click(
      await screen.findByRole("button", { name: "填寫我的資料" }),
    )
    const dialog = await screen.findByTestId("player-profile-dialog")
    expect(within(dialog).getByLabelText("遊戲 ID")).toHaveValue("阿哲#TW")
    expect(within(dialog).getByTestId("screenshot-uploaded")).toHaveTextContent(
      "old.png",
    )
    expect(within(dialog).queryByRole("img")).toBeNull()
    await user.click(within(dialog).getByRole("button", { name: "儲存資料" }))

    await waitFor(() => expect(update).toHaveBeenCalled())
    expect(update.mock.calls[0][0].body).toEqual({
      game_account_id: "阿哲#TW",
      rank_tier: "黃金",
      rank_screenshot: undefined,
    })
    expect(update.mock.calls[0][0].onUploadProgress).toBeUndefined()
  })

  it("伺服器拒絕時 S18 保持開啟並顯示原因，並重新取得隊伍", async () => {
    const user = userEvent.setup()
    signInAs()
    const mine = filled("acc-1", "阿哲", "黃金", 10, "captain", "old.png")
    const read = mockReadTeam({ ...TEAM, members: [mine] })
    vi.spyOn(RegistrationService, "updateMyPlayerProfile").mockRejectedValue(
      httpError(409, {
        detail: {
          code: "ROSTER_LOCKED",
          message: "名單已鎖定，資料無法修改。",
        },
      }),
    )
    renderApp("/teams/team-1")

    await user.click(
      await screen.findByRole("button", { name: "填寫我的資料" }),
    )
    const dialog = await screen.findByTestId("player-profile-dialog")
    await user.click(within(dialog).getByRole("button", { name: "儲存資料" }))

    expect(
      await within(dialog).findByText("名單已鎖定，資料無法修改。"),
    ).toBeInTheDocument()
    expect(screen.getByTestId("player-profile-dialog")).toBeInTheDocument()
    await waitFor(() => expect(read).toHaveBeenCalledTimes(2))
  })

  it("不能編輯時（profile_editable 為 false）S18 唯讀，按鈕仍是「填寫我的資料」", async () => {
    const user = userEvent.setup()
    signInAs()
    mockReadTeam({
      ...TEAM,
      registration_status: "pending",
      profile_editable: false,
      members: [filled("acc-1", "阿哲", "黃金", 10, "captain", "old.png")],
    })
    renderApp("/teams/team-1")

    await user.click(
      await screen.findByRole("button", { name: "填寫我的資料" }),
    )
    const dialog = await screen.findByTestId("player-profile-dialog")
    expect(within(dialog).getByLabelText("遊戲 ID")).toBeDisabled()
    expect(
      within(dialog).getByRole("combobox", { name: "段位" }),
    ).toBeDisabled()
    expect(
      within(dialog).queryByRole("button", { name: "儲存資料" }),
    ).toBeNull()
  })
})

describe("加入隊伍（S19）", () => {
  it("未登入：先顯示賽事、遊戲與隊名，提供註冊與登入（帶 redirect 回 S19）", async () => {
    mockPreview()
    renderApp("/join/tok-1")

    expect(await screen.findByText("政大校園盃 · 特戰英豪")).toBeInTheDocument()
    expect(screen.getByText("夜貓隊")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "註冊帳號" })).toHaveAttribute(
      "href",
      "/signup?redirect=%2Fjoin%2Ftok-1",
    )
    expect(screen.getByRole("link", { name: "登入帳號" })).toHaveAttribute(
      "href",
      "/login?redirect=%2Fjoin%2Ftok-1",
    )
    expect(screen.queryByRole("button", { name: "加入隊伍" })).toBeNull()
  })

  it("未驗證 Email：說明需先驗證，「加入隊伍」停用", async () => {
    signInAs({ account: { ...ACCOUNT, email_verified: false } })
    mockPreview()
    renderApp("/join/tok-1")

    expect(
      await screen.findByText("完成 Email 驗證後才能加入隊伍。"),
    ).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "加入隊伍" })).toBeDisabled()
  })

  it("加入成功後到隊伍頁", async () => {
    const user = userEvent.setup()
    signInAs()
    mockPreview()
    const join = vi
      .spyOn(RegistrationService, "joinTeam")
      .mockResolvedValue({ data: TEAM } as JoinResult)
    mockReadTeam()
    const router = renderApp("/join/tok-1")

    const button = await screen.findByRole("button", { name: "加入隊伍" })
    await waitFor(() => expect(button).toBeEnabled())
    await user.click(button)

    await waitFor(() =>
      expect(router.state.location.pathname).toBe("/teams/team-1"),
    )
    expect(join).toHaveBeenCalledWith({ path: { token: "tok-1" } })
  })

  it("被拒絕時說明原因並提供回賽事頁的連結", async () => {
    const user = userEvent.setup()
    signInAs()
    mockPreview()
    vi.spyOn(RegistrationService, "joinTeam").mockRejectedValue(
      httpError(409, {
        detail: {
          code: "ALREADY_IN_TOURNAMENT",
          message: "你已經在這個賽事的隊伍中，同一個賽事只能加入一支隊伍。",
        },
      }),
    )
    renderApp("/join/tok-1")

    const button = await screen.findByRole("button", { name: "加入隊伍" })
    await waitFor(() => expect(button).toBeEnabled())
    await user.click(button)

    expect(
      await screen.findByText(
        "你已經在這個賽事的隊伍中，同一個賽事只能加入一支隊伍。",
      ),
    ).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "回到賽事頁" })).toHaveAttribute(
      "href",
      "/tournaments/tour-1",
    )
    // 已在同賽事的隊伍：另提供「查看我的隊伍」
    expect(screen.getByRole("link", { name: "查看我的隊伍" })).toHaveAttribute(
      "href",
      "/me/teams",
    )
  })

  it("加入成功或失敗後重新取得邀請預覽；其他原因被拒時不顯示「查看我的隊伍」", async () => {
    const user = userEvent.setup()
    signInAs()
    const preview = mockPreview()
    vi.spyOn(RegistrationService, "joinTeam").mockRejectedValue(
      httpError(409, {
        detail: { code: "TEAM_FULL", message: "隊伍已滿，無法再加入。" },
      }),
    )
    renderApp("/join/tok-1")

    const button = await screen.findByRole("button", { name: "加入隊伍" })
    await waitFor(() => expect(button).toBeEnabled())
    expect(preview).toHaveBeenCalledTimes(1)
    await user.click(button)

    expect(
      await screen.findByText("隊伍已滿，無法再加入。"),
    ).toBeInTheDocument()
    await waitFor(() => expect(preview).toHaveBeenCalledTimes(2))
    expect(screen.queryByRole("link", { name: "查看我的隊伍" })).toBeNull()
  })

  it("隊伍已滿：說明連結已失效，不提供加入", async () => {
    signInAs()
    mockPreview({ ...INVITE, member_count: 6, invite_status: "full" })
    renderApp("/join/tok-1")

    expect(
      await screen.findByText("連結已失效：隊伍已滿。"),
    ).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "加入隊伍" })).toBeNull()
    expect(screen.getByRole("link", { name: "回到賽事頁" })).toHaveAttribute(
      "href",
      "/tournaments/tour-1",
    )
  })

  it("連結不存在：說明連結無效", async () => {
    vi.spyOn(RegistrationService, "previewTeamInvite").mockRejectedValue(
      httpError(404, {
        detail: {
          code: "TEAM_INVITE_NOT_FOUND",
          message: "這個邀請連結無效。",
        },
      }),
    )
    renderApp("/join/nope")

    expect(await screen.findByText(/這個邀請連結無效。/)).toBeInTheDocument()
  })
})

describe("我的隊伍（S12）", () => {
  it("每隊一張 Registration status card，點擊到 S17", async () => {
    const user = userEvent.setup()
    signInAs()
    const cards: MyTeamCard[] = [
      {
        team_id: "team-1",
        team_name: "夜貓隊",
        tournament_id: "tour-1",
        tournament_name: "政大校園盃",
        game_name: "特戰英豪",
        registration_status: "forming",
      },
    ]
    vi.spyOn(RegistrationService, "listMyTeams").mockResolvedValue({
      data: cards,
    } as MyTeamsResult)
    mockReadTeam()
    const router = renderApp("/me/teams")

    const card = await screen.findByRole("link", { name: /夜貓隊/ })
    expect(card).toHaveAttribute("href", "/teams/team-1")
    expect(within(card).getByText("政大校園盃 · 特戰英豪")).toBeInTheDocument()
    expect(within(card).getByText("組隊中")).toBeInTheDocument()

    await user.click(card)

    await waitFor(() =>
      expect(router.state.location.pathname).toBe("/teams/team-1"),
    )
  })

  it("沒有隊伍：「你還沒有加入任何隊伍。」＋「瀏覽賽事」", async () => {
    signInAs()
    vi.spyOn(RegistrationService, "listMyTeams").mockResolvedValue({
      data: [],
    } as unknown as MyTeamsResult)
    renderApp("/me/teams")

    expect(
      await screen.findByText("你還沒有加入任何隊伍。"),
    ).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "瀏覽賽事" })).toHaveAttribute(
      "href",
      "/",
    )
  })

  it("身分切換器出現「我的隊伍」，點選到 /me/teams", async () => {
    const user = userEvent.setup()
    signInAs({ identities: [BROWSE, MY_TEAMS] })
    vi.spyOn(RegistrationService, "listMyTeams").mockResolvedValue({
      data: [],
    } as unknown as MyTeamsResult)
    const router = renderApp("/")

    const banner = await screen.findByRole("banner")
    await user.click(
      await within(banner).findByRole("button", { name: /切換身分（目前：/ }),
    )
    const menu = await screen.findByRole("menu")
    await user.click(within(menu).getByRole("menuitem", { name: /我的隊伍/ }))

    await waitFor(() =>
      expect(router.state.location.pathname).toBe("/me/teams"),
    )
  })
})
