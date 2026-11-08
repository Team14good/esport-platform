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
  submit_blockers: [],
  priority_end: "2099-01-01T00:00:00Z",
  registration_end: "2099-01-08T00:00:00Z",
  submitted_at: null,
  waitlist_position: null,
  waitlist_reason: null,
  representative_backfill: null,
  waitlist_phase: null,
}

/** 不是候補時，候補資訊全為 null。 */
const NO_WAITLIST = {
  waitlist_position: null,
  waitlist_reason: null,
  representative_backfill: null,
  waitlist_phase: null,
} satisfies Partial<MyTeamCard>

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

/** 某行候補說明所在區塊的每一行文字；找不到區塊時直接讓斷言失敗。 */
function waitlistLines(line: HTMLElement): (string | null)[] {
  const details = line.closest("[data-slot=waitlist-details]")
  expect(details).not.toBeNull()
  return Array.from(details?.children ?? [], (child) => child.textContent)
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
        ...NO_WAITLIST,
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

describe("送出報名（S17、S19）", () => {
  type SubmitResult = Awaited<
    ReturnType<typeof RegistrationService.submitRegistration>
  >
  // 目前帳號是 acc-1（auth-fixtures 的 ACCOUNT），在這裡是隊長
  const READY: TeamDetail = {
    ...TEAM,
    my_role: "captain",
    members: [
      filled("acc-1", "阿哲", "鑽石", 30, "captain", "rank.png"),
      filled("acc-2", "小芸", "鑽石", 30),
      filled("acc-3", "阿凱", "黃金", 10),
      filled("acc-4", "小晴", "黃金", 10),
      filled("acc-5", "阿宏", "黃金", 10),
    ],
    avg_rank_score: 18,
    rank_filled_count: 5,
  }
  const SUBMITTED: TeamDetail = {
    ...READY,
    registration_status: "pending",
    invite_status: "locked",
    profile_editable: false,
    submitted_at: "2026-11-03T10:00:00Z",
  }
  const BLOCKERS = [
    { code: "STARTERS_NOT_MET", message: "還差 1 人才達先發人數（5 人）" },
    { code: "PROFILE_INCOMPLETE", message: "尚未填完參賽資料：小芸、阿凱" },
  ] satisfies TeamDetail["submit_blockers"]

  const inMs = (ms: number) => new Date(Date.now() + ms).toISOString()

  function reasons() {
    return within(
      screen.getByRole("list", { name: "尚未符合送出條件" }),
    ).getAllByRole("listitem")
  }

  function countdownOf(label: string) {
    const countdown = screen
      .getByText(label)
      .closest<HTMLElement>("[data-slot=countdown]")
    expect(countdown).not.toBeNull()
    return countdown as HTMLElement
  }

  it("條件不符：「送出報名」停用，下方逐項列出原因", async () => {
    signInAs()
    mockReadTeam({ ...READY, submit_blockers: BLOCKERS })
    renderApp("/teams/team-1")

    const button = await screen.findByRole("button", { name: "送出報名" })
    expect(button).toBeDisabled()
    expect(reasons().map((item) => item.textContent)).toEqual([
      "還差 1 人才達先發人數（5 人）",
      "尚未填完參賽資料：小芸、阿凱",
    ])
    expect(screen.queryByText("由隊長送出報名")).toBeNull()
  })

  it("確認後送出：徽章、Toast、邀請連結失效、優先期倒數與 S18 唯讀", async () => {
    const user = userEvent.setup()
    const success = vi.spyOn(toast, "success")
    signInAs()
    mockReadTeam(READY)
    const submitted = { ...SUBMITTED, priority_end: inMs(3 * 60 * 60 * 1000) }
    const submit = vi
      .spyOn(RegistrationService, "submitRegistration")
      .mockResolvedValue({ data: submitted } as SubmitResult)
    renderApp("/teams/team-1")

    const button = await screen.findByRole("button", { name: "送出報名" })
    expect(button).toBeEnabled()
    expect(screen.queryByRole("list", { name: "尚未符合送出條件" })).toBeNull()
    await user.click(button)
    const dialog = await screen.findByRole("alertdialog")
    expect(dialog).toHaveAccessibleName("送出報名")
    expect(dialog).toHaveAccessibleDescription(
      "送出後名單會鎖定，只有被主辦方退回才能修改。",
    )
    await user.click(within(dialog).getByRole("button", { name: "送出報名" }))

    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull())
    expect(submit).toHaveBeenCalledWith({ path: { team_id: "team-1" } })
    expect(success).toHaveBeenCalledWith("已送出報名", expect.anything())
    expect(screen.getByText("已送出・待分配")).toBeInTheDocument()
    expect(screen.getByText("連結已失效")).toBeInTheDocument()
    expect(screen.getByText(/名單已鎖定/)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "複製連結" })).toBeDisabled()
    expect(screen.queryByRole("button", { name: "送出報名" })).toBeNull()
    expect(countdownOf("優先期結束後分配名額")).toHaveAttribute(
      "data-variant",
      "muted",
    )

    await user.click(screen.getByRole("button", { name: "填寫我的資料" }))
    const profile = await screen.findByTestId("player-profile-dialog")
    expect(within(profile).getByLabelText("遊戲 ID")).toBeDisabled()
  })

  // Story 3.5：先搶期送出的回應已帶分配結果，S17 直接照回應顯示（不做 optimistic update）
  const FIRST_COME_RULE =
    "先搶期由優先期沒有報名、目前也沒有正取的學校，依送出先後遞補。"
  const FIRST_COME: TeamDetail = {
    ...SUBMITTED,
    priority_end: inMs(-60 * 60 * 1000),
    registration_end: inMs(3 * 24 * 60 * 60 * 1000),
  }

  async function submitWith(response: TeamDetail) {
    const user = userEvent.setup()
    const success = vi.spyOn(toast, "success")
    signInAs()
    mockReadTeam(READY)
    vi.spyOn(RegistrationService, "submitRegistration").mockResolvedValue({
      data: response,
    } as SubmitResult)
    renderApp("/teams/team-1")

    await user.click(await screen.findByRole("button", { name: "送出報名" }))
    const dialog = await screen.findByRole("alertdialog")
    await user.click(within(dialog).getByRole("button", { name: "送出報名" }))
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull())
    expect(success).toHaveBeenCalledWith("已送出報名", expect.anything())
    expect(screen.queryByText("已送出・待分配")).toBeNull()
    expect(screen.queryByText("優先期結束後分配名額")).toBeNull()
  }

  it("先搶期送出、回應為正取：直接顯示「正取」與報名截止倒數", async () => {
    await submitWith({ ...FIRST_COME, registration_status: "accepted" })

    expect(screen.getByText("正取")).toBeInTheDocument()
    expect(
      screen.getByText("報名截止").closest("[data-slot=countdown]"),
    ).not.toBeNull()
    expect(document.querySelector("[data-slot=waitlist-details]")).toBeNull()
  })

  it("先搶期送出、回應為候補有順位：直接顯示「候補第 N 位」與先搶期遞補規則", async () => {
    await submitWith({
      ...FIRST_COME,
      registration_status: "waitlisted",
      waitlist_position: 2,
      waitlist_reason: null,
      representative_backfill: false,
      waitlist_phase: "first_come",
    })

    expect(screen.getByText("候補第 2 位")).toBeInTheDocument()
    expect(waitlistLines(screen.getByText(FIRST_COME_RULE))).toEqual([
      FIRST_COME_RULE,
    ])
  })

  it("先搶期送出、回應為候補沒有順位：直接顯示原因與先搶期遞補規則", async () => {
    const reason = "先搶期每校只遞補最早送出的一隊，本校已有更早送出的候補。"
    await submitWith({
      ...FIRST_COME,
      registration_status: "waitlisted",
      waitlist_position: null,
      waitlist_reason: "LATER_THAN_SCHOOLMATE",
      representative_backfill: false,
      waitlist_phase: "first_come",
    })

    expect(screen.getByText("候補・目前不在遞補順序中")).toBeInTheDocument()
    expect(waitlistLines(screen.getByText(reason))).toEqual([
      reason,
      FIRST_COME_RULE,
    ])
  })

  it("伺服器拒絕時在對話框內顯示原因，並重新取得隊伍", async () => {
    const user = userEvent.setup()
    signInAs()
    const read = mockReadTeam(READY)
    vi.spyOn(RegistrationService, "submitRegistration").mockRejectedValue(
      httpError(409, {
        detail: {
          code: "REGISTRATION_REQUIREMENTS_UNMET",
          message: "尚未設定學校：阿凱",
        },
      }),
    )
    renderApp("/teams/team-1")

    await user.click(await screen.findByRole("button", { name: "送出報名" }))
    const dialog = await screen.findByRole("alertdialog")
    await user.click(within(dialog).getByRole("button", { name: "送出報名" }))

    expect(
      await within(dialog).findByText("尚未設定學校：阿凱"),
    ).toBeInTheDocument()
    await waitFor(() => expect(read).toHaveBeenCalledTimes(2))
  })

  it("非隊長：不顯示「送出報名」，改寫「由隊長送出報名」並列出缺漏", async () => {
    signInAs()
    mockReadTeam({ ...READY, my_role: "player", submit_blockers: BLOCKERS })
    renderApp("/teams/team-1")

    expect(await screen.findByText("由隊長送出報名")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "送出報名" })).toBeNull()
    expect(reasons()).toHaveLength(2)
  })

  it("報名截止剩餘超過 24 小時：倒數為 muted", async () => {
    signInAs()
    mockReadTeam({ ...READY, registration_end: inMs(3 * 24 * 60 * 60 * 1000) })
    renderApp("/teams/team-1")

    expect(await screen.findByText("報名截止")).toBeInTheDocument()
    expect(countdownOf("報名截止")).toHaveAttribute("data-variant", "muted")
  })

  it("報名截止最後 24 小時：倒數為 appeal", async () => {
    signInAs()
    mockReadTeam({ ...READY, registration_end: inMs(2 * 60 * 60 * 1000) })
    renderApp("/teams/team-1")

    expect(await screen.findByText("報名截止")).toBeInTheDocument()
    expect(countdownOf("報名截止")).toHaveAttribute("data-variant", "appeal")
  })

  it("報名截止倒數歸零：寫「已截止」、停用「送出報名」並只重新取得隊伍一次", async () => {
    signInAs()
    const open = { ...READY, registration_end: inMs(1_200) }
    const closed: TeamDetail = {
      ...open,
      profile_editable: false,
      submit_blockers: [{ code: "REGISTRATION_CLOSED", message: "已截止" }],
    }
    const read = vi
      .spyOn(RegistrationService, "readTeam")
      .mockResolvedValueOnce({ data: open } as ReadTeamResult)
      .mockResolvedValue({ data: closed } as ReadTeamResult)
    renderApp("/teams/team-1")

    expect(
      await screen.findByRole("button", { name: "送出報名" }),
    ).toBeEnabled()
    await waitFor(
      () =>
        expect(screen.getByRole("button", { name: "送出報名" })).toBeDisabled(),
      { timeout: 3_000 },
    )
    expect(reasons().map((item) => item.textContent)).toEqual(["已截止"])
    expect(
      within(countdownOf("報名截止")).getByText("已截止"),
    ).toBeInTheDocument()
    await waitFor(() => expect(read).toHaveBeenCalledTimes(2))
    // 歸零後不輪詢
    await new Promise((resolve) => setTimeout(resolve, 300))
    expect(read).toHaveBeenCalledTimes(2)
  })

  it("優先期已過才檢視已送出的隊伍：不顯示倒數", async () => {
    signInAs()
    mockReadTeam({ ...SUBMITTED, priority_end: inMs(-60_000) })
    renderApp("/teams/team-1")

    expect(await screen.findByText("已送出・待分配")).toBeInTheDocument()
    expect(screen.queryByText("優先期結束後分配名額")).toBeNull()
    expect(screen.queryByText("報名截止")).toBeNull()
  })

  it("優先期倒數歸零：改顯示「已送出・待分配」，不輪詢", async () => {
    signInAs()
    const read = mockReadTeam({ ...SUBMITTED, priority_end: inMs(1_200) })
    renderApp("/teams/team-1")

    expect(await screen.findByText("優先期結束後分配名額")).toBeInTheDocument()
    await waitFor(
      () => expect(screen.queryByText("優先期結束後分配名額")).toBeNull(),
      { timeout: 3_000 },
    )
    // 徽章與分配區塊各一
    expect(screen.getAllByText("已送出・待分配")).toHaveLength(2)
    expect(read).toHaveBeenCalledTimes(1)
  })

  it("裝置休眠、計時器延後：Countdown 先歸零時也立即寫「已截止」並重新取得隊伍", async () => {
    // 只假造 Date：hook 排的 10 分鐘 setTimeout 不會觸發，Countdown 每秒的真實 interval 照常執行
    vi.useFakeTimers({ toFake: ["Date"] })
    try {
      signInAs()
      const open = { ...READY, registration_end: inMs(10 * 60 * 1000) }
      const read = vi
        .spyOn(RegistrationService, "readTeam")
        .mockResolvedValueOnce({ data: open } as ReadTeamResult)
        .mockResolvedValue({
          data: {
            ...open,
            submit_blockers: [
              { code: "REGISTRATION_CLOSED", message: "已截止" },
            ],
          },
        } as ReadTeamResult)
      renderApp("/teams/team-1")

      expect(
        await screen.findByRole("button", { name: "送出報名" }),
      ).toBeEnabled()
      vi.setSystemTime(Date.now() + 11 * 60 * 1000)

      await waitFor(
        () =>
          expect(
            screen.getByRole("button", { name: "送出報名" }),
          ).toBeDisabled(),
        { timeout: 3_000 },
      )
      expect(
        within(countdownOf("報名截止")).getByText("已截止"),
      ).toBeInTheDocument()
      await waitFor(() => expect(read).toHaveBeenCalledTimes(2))
    } finally {
      vi.useRealTimers()
    }
  })

  it("裝置休眠、計時器延後：優先期 Countdown 先歸零時也立即改顯示「已送出・待分配」", async () => {
    vi.useFakeTimers({ toFake: ["Date"] })
    try {
      signInAs()
      mockReadTeam({ ...SUBMITTED, priority_end: inMs(10 * 60 * 1000) })
      renderApp("/teams/team-1")

      expect(
        await screen.findByText("優先期結束後分配名額"),
      ).toBeInTheDocument()
      vi.setSystemTime(Date.now() + 11 * 60 * 1000)

      await waitFor(
        () => expect(screen.queryByText("優先期結束後分配名額")).toBeNull(),
        { timeout: 3_000 },
      )
      expect(screen.getAllByText("已送出・待分配")).toHaveLength(2)
    } finally {
      vi.useRealTimers()
    }
  })

  it("報名已截止仍在組隊中：S17 邀請連結顯示「報名已截止」", async () => {
    signInAs()
    mockReadTeam({ ...READY, invite_status: "closed" })
    renderApp("/teams/team-1")

    expect(await screen.findByText("連結已失效")).toBeInTheDocument()
    expect(screen.getByText(/報名已截止/)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "複製連結" })).toBeDisabled()
  })

  it("S19：報名已截止時顯示「連結已失效：報名已截止。」", async () => {
    signInAs()
    mockPreview({ ...INVITE, invite_status: "closed" })
    renderApp("/join/tok-1")

    expect(
      await screen.findByText("連結已失效：報名已截止。"),
    ).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "加入隊伍" })).toBeNull()
  })

  it("S19：開啟預覽後隊伍才送出，加入被拒（ROSTER_LOCKED）時顯示「連結已失效：名單已鎖定。」", async () => {
    const user = userEvent.setup()
    signInAs()
    mockPreview()
    vi.spyOn(RegistrationService, "joinTeam").mockRejectedValue(
      httpError(409, {
        detail: { code: "ROSTER_LOCKED", message: "名單已鎖定，無法加入。" },
      }),
    )
    renderApp("/join/tok-1")

    const button = await screen.findByRole("button", { name: "加入隊伍" })
    await waitFor(() => expect(button).toBeEnabled())
    await user.click(button)

    expect(
      await screen.findByText("連結已失效：名單已鎖定。"),
    ).toBeInTheDocument()
    expect(screen.queryByText("名單已鎖定，無法加入。")).toBeNull()
    expect(screen.getByRole("link", { name: "回到賽事頁" })).toHaveAttribute(
      "href",
      "/tournaments/tour-1",
    )
  })

  it("S19：已送出的隊伍顯示「連結已失效：名單已鎖定。」與回賽事頁", async () => {
    signInAs()
    mockPreview({ ...INVITE, member_count: 5, invite_status: "locked" })
    renderApp("/join/tok-1")

    expect(
      await screen.findByText("連結已失效：名單已鎖定。"),
    ).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "加入隊伍" })).toBeNull()
    expect(screen.getByRole("link", { name: "回到賽事頁" })).toHaveAttribute(
      "href",
      "/tournaments/tour-1",
    )
  })
})

describe("名額分配結果（S17、S12）", () => {
  const inMs = (ms: number) => new Date(Date.now() + ms).toISOString()
  const ALLOCATED: TeamDetail = {
    ...TEAM,
    my_role: "captain",
    invite_status: "locked",
    profile_editable: false,
    submitted_at: "2026-11-03T10:00:00Z",
    priority_end: inMs(-60 * 60 * 1000),
  }
  const UNRANKED_REASON =
    "先搶期只遞補優先期沒有報名、目前也沒有正取的學校；報名截止後改依平均段位積分排序。"
  const BACKFILL = "本校代表隊退出時，由本校平均段位積分次高的隊伍遞補。"
  const FIRST_COME_RULE =
    "先搶期由優先期沒有報名、目前也沒有正取的學校，依送出先後遞補。"
  const AFTER_DEADLINE_RULE =
    "報名截止後依平均段位積分由高到低遞補，每校最多 2 隊正取。"

  it("S17 候補沒有順位：徽章、原因、代表隊補充與先搶期的遞補規則", async () => {
    signInAs()
    mockReadTeam({
      ...ALLOCATED,
      registration_status: "waitlisted",
      waitlist_position: null,
      waitlist_reason: "SCHOOL_NOT_ELIGIBLE",
      representative_backfill: true,
      waitlist_phase: "first_come",
    })
    renderApp("/teams/team-1")

    const header = (
      await screen.findByRole("heading", { level: 1, name: "夜貓隊" })
    ).closest("header") as HTMLElement
    expect(
      within(header).getByText("候補・目前不在遞補順序中"),
    ).toBeInTheDocument()
    expect(waitlistLines(within(header).getByText(UNRANKED_REASON))).toEqual([
      UNRANKED_REASON,
      BACKFILL,
      FIRST_COME_RULE,
    ])
    // 候補不顯示倒數
    expect(screen.queryByText("報名截止")).toBeNull()
  })

  it.each([
    [
      "LATER_THAN_SCHOOLMATE",
      "先搶期每校只遞補最早送出的一隊，本校已有更早送出的候補。",
      "first_come",
      FIRST_COME_RULE,
    ],
    [
      "SCHOOL_LIMIT_REACHED",
      "每校最多 2 隊正取：本校正取加上排在前面的本校候補已達 2 隊。",
      "after_deadline",
      AFTER_DEADLINE_RULE,
    ],
  ] as const)(
    "S17 候補原因 %s：原因與當下階段的遞補規則",
    async (reason, message, phase, rule) => {
      signInAs()
      mockReadTeam({
        ...ALLOCATED,
        registration_status: "waitlisted",
        waitlist_position: null,
        waitlist_reason: reason,
        representative_backfill: false,
        waitlist_phase: phase,
      })
      renderApp("/teams/team-1")

      expect(waitlistLines(await screen.findByText(message))).toEqual([
        message,
        rule,
      ])
    },
  )

  it("S17 候補有順位：「候補第 N 位」＋截止後的遞補規則，不顯示原因", async () => {
    signInAs()
    mockReadTeam({
      ...ALLOCATED,
      registration_status: "waitlisted",
      waitlist_position: 3,
      waitlist_reason: null,
      representative_backfill: false,
      waitlist_phase: "after_deadline",
    })
    renderApp("/teams/team-1")

    expect(await screen.findByText("候補第 3 位")).toBeInTheDocument()
    expect(waitlistLines(screen.getByText(AFTER_DEADLINE_RULE))).toEqual([
      AFTER_DEADLINE_RULE,
    ])
    expect(screen.queryByText(UNRANKED_REASON)).toBeNull()
  })

  it("S17 正取：「正取」與報名截止倒數", async () => {
    signInAs()
    mockReadTeam({
      ...ALLOCATED,
      registration_status: "accepted",
      registration_end: inMs(3 * 24 * 60 * 60 * 1000),
    })
    renderApp("/teams/team-1")

    expect(await screen.findByText("正取")).toBeInTheDocument()
    const countdown = screen
      .getByText("報名截止")
      .closest<HTMLElement>("[data-slot=countdown]")
    expect(countdown).not.toBeNull()
    expect(screen.queryByText("優先期結束後分配名額")).toBeNull()
    expect(document.querySelector("[data-slot=waitlist-details]")).toBeNull()
  })

  it("S17 正取、報名已截止：不顯示倒數", async () => {
    signInAs()
    mockReadTeam({
      ...ALLOCATED,
      registration_status: "accepted",
      registration_end: inMs(-60_000),
    })
    renderApp("/teams/team-1")

    expect(await screen.findByText("正取")).toBeInTheDocument()
    expect(screen.queryByText("報名截止")).toBeNull()
  })

  it("S12 卡片：候補顯示順位或原因，正取只顯示徽章", async () => {
    signInAs()
    const base = {
      tournament_id: "tour-1",
      tournament_name: "政大校園盃",
      game_name: "特戰英豪",
    }
    const cards: MyTeamCard[] = [
      {
        ...base,
        team_id: "team-1",
        team_name: "夜貓隊",
        registration_status: "waitlisted",
        waitlist_position: null,
        waitlist_reason: "SCHOOL_NOT_ELIGIBLE",
        representative_backfill: true,
        waitlist_phase: "first_come",
      },
      {
        ...base,
        team_id: "team-2",
        team_name: "晨鳥隊",
        registration_status: "waitlisted",
        waitlist_position: 2,
        waitlist_reason: null,
        representative_backfill: false,
        waitlist_phase: "first_come",
      },
      {
        ...base,
        team_id: "team-3",
        team_name: "午茶隊",
        registration_status: "accepted",
        ...NO_WAITLIST,
      },
    ]
    vi.spyOn(RegistrationService, "listMyTeams").mockResolvedValue({
      data: cards,
    } as MyTeamsResult)
    renderApp("/me/teams")

    const unranked = await screen.findByRole("link", { name: /夜貓隊/ })
    expect(
      within(unranked).getByText("候補・目前不在遞補順序中"),
    ).toBeInTheDocument()
    expect(within(unranked).getByText(UNRANKED_REASON)).toBeInTheDocument()
    expect(within(unranked).getByText(BACKFILL)).toBeInTheDocument()
    expect(within(unranked).getByText(FIRST_COME_RULE)).toBeInTheDocument()
    // 說明放在隊名與徽章那一列的下方、用卡片全寬（375 px 時才不會被長徽章擠窄）
    const details = unranked.querySelector("[data-slot=waitlist-details]")
    expect(details?.parentElement).toBe(unranked)
    expect(
      unranked.querySelector(
        "[data-slot=card-row] [data-slot=waitlist-details]",
      ),
    ).toBeNull()

    const ranked = screen.getByRole("link", { name: /晨鳥隊/ })
    expect(within(ranked).getByText("候補第 2 位")).toBeInTheDocument()
    expect(within(ranked).getByText(FIRST_COME_RULE)).toBeInTheDocument()
    expect(within(ranked).queryByText(UNRANKED_REASON)).toBeNull()

    const accepted = screen.getByRole("link", { name: /午茶隊/ })
    expect(within(accepted).getByText("正取")).toBeInTheDocument()
    expect(accepted.querySelector("[data-slot=waitlist-details]")).toBeNull()
  })
})
