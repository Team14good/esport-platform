import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
} from "@tanstack/react-router"
import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { toast } from "sonner"
import { describe, expect, it, vi } from "vitest"

import { RegistrationService, type TeamDetail } from "@/client"
import { CreateTeamDialog } from "@/features/registration/CreateTeamDialog"
import {
  COPIED_TEXT,
  InviteLinkField,
} from "@/features/registration/InviteLinkField"
import {
  avgRankScoreText,
  profileCaption,
  profileStatusText,
  RosterList,
} from "@/features/registration/RosterList"
import {
  registrationStatusLabel,
  WaitlistDetails,
} from "@/features/registration/registration-status"
import { ACCOUNT, signInAs } from "./auth-fixtures"
import { httpError } from "./helpers"
import { renderRouter } from "./render-router"

type CreateTeamResult = Awaited<
  ReturnType<typeof RegistrationService.createTeam>
>

const URL = "http://localhost/join/tok-1"

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
    {
      account_id: "acc-1",
      display_name: "阿哲",
      role: "captain",
      joined_at: "2026-10-30T10:00:00Z",
      game_account_id: null,
      rank_tier: null,
      rank_score: null,
      has_rank_screenshot: false,
      rank_screenshot_name: null,
      missing_fields: ["game_account_id", "rank_tier", "rank_screenshot"],
    },
    {
      account_id: "acc-2",
      display_name: "小芸",
      role: "player",
      joined_at: "2026-10-30T10:05:00Z",
      game_account_id: null,
      rank_tier: null,
      rank_score: null,
      has_rank_screenshot: false,
      rank_screenshot_name: null,
      missing_fields: ["game_account_id", "rank_tier", "rank_screenshot"],
    },
    {
      account_id: "acc-3",
      display_name: "阿凱",
      role: "player",
      joined_at: "2026-10-30T10:06:00Z",
      game_account_id: null,
      rank_tier: null,
      rank_score: null,
      has_rank_screenshot: false,
      rank_screenshot_name: null,
      missing_fields: ["game_account_id", "rank_tier", "rank_screenshot"],
    },
    {
      account_id: "acc-4",
      display_name: "小晴",
      role: "player",
      joined_at: "2026-10-30T10:07:00Z",
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
  submit_blockers: [],
  priority_end: "2099-01-01T00:00:00Z",
  registration_end: "2099-01-08T00:00:00Z",
  submitted_at: null,
  waitlist_position: null,
  waitlist_reason: null,
  representative_backfill: null,
  waitlist_phase: null,
}

describe("Invite link field", () => {
  it("唯讀顯示連結；「複製連結」寫入剪貼簿並 Toast「已複製」", async () => {
    const user = userEvent.setup()
    const success = vi.spyOn(toast, "success")
    render(<InviteLinkField label="隊伍邀請連結" url={URL} />)

    const input = screen.getByLabelText("隊伍邀請連結")
    expect(input).toHaveValue(URL)
    expect(input).toHaveAttribute("readonly")

    await user.click(screen.getByRole("button", { name: "複製連結" }))

    expect(await navigator.clipboard.readText()).toBe(URL)
    expect(success).toHaveBeenCalledWith(COPIED_TEXT, { duration: 3000 })
  })

  it("失效時顯示「連結已失效」與原因，並停用「複製連結」", () => {
    render(
      <InviteLinkField
        label="隊伍邀請連結"
        url={URL}
        invalid={{ reason: "隊伍已滿" }}
      />,
    )

    expect(screen.getByText("連結已失效")).toBeInTheDocument()
    expect(screen.getByText(/隊伍已滿/)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "複製連結" })).toBeDisabled()
    expect(screen.getByLabelText("隊伍邀請連結")).toHaveAccessibleDescription(
      /連結已失效.*隊伍已滿/,
    )
  })

  it("可改寫失效標題並顯示補充說明（裁判邀請連結沿用）", () => {
    render(
      <InviteLinkField
        label="裁判邀請連結"
        url={URL}
        invalid={{ title: "連結已過期", reason: "請產生新連結" }}
        note="11/6（五）10:00 到期"
      />,
    )

    expect(screen.getByText("連結已過期")).toBeInTheDocument()
    expect(screen.getByText("11/6（五）10:00 到期")).toBeInTheDocument()
  })
})

describe("Roster list", () => {
  it("每人一列顯示名稱，隊長有「隊長」徽章，下方顯示人數", () => {
    render(
      <RosterList
        members={TEAM.members}
        starters={TEAM.starters}
        maxMembers={TEAM.max_members}
        avgRankScore={null}
        rankFilledCount={0}
      />,
    )

    const rows = within(
      screen.getByRole("list", { name: "隊伍名單" }),
    ).getAllByRole("listitem")
    const missing = "缺：遊戲 ID、段位、段位截圖"
    expect(rows.map((row) => row.textContent)).toEqual([
      `阿哲隊長${missing}`,
      `小芸${missing}`,
      `阿凱${missing}`,
      `小晴${missing}`,
    ])
    expect(within(rows[0]).getByText("隊長")).toBeInTheDocument()
    expect(screen.getByText("4／6 人（先發 5）")).toBeInTheDocument()
    // 沒有傳目前帳號或 onEditMyProfile 時不顯示「填寫我的資料」
    expect(screen.queryByRole("button", { name: "填寫我的資料" })).toBeNull()
  })

  it("自己那列的「填寫我的資料」呼叫 onEditMyProfile", async () => {
    const user = userEvent.setup()
    const onEdit = vi.fn()
    render(
      <RosterList
        members={TEAM.members}
        starters={TEAM.starters}
        maxMembers={TEAM.max_members}
        avgRankScore={null}
        rankFilledCount={0}
        currentAccountId="acc-3"
        onEditMyProfile={onEdit}
      />,
    )

    const rows = within(
      screen.getByRole("list", { name: "隊伍名單" }),
    ).getAllByRole("listitem")
    await user.click(
      within(rows[2]).getByRole("button", { name: "填寫我的資料" }),
    )

    expect(onEdit).toHaveBeenCalledTimes(1)
    expect(
      screen.getAllByRole("button", { name: "填寫我的資料" }),
    ).toHaveLength(1)
  })

  it("缺漏依遊戲 ID、段位、段位截圖的順序列出；caption 只列有填的部分", () => {
    const base = TEAM.members[0]
    expect(
      profileStatusText({ ...base, missing_fields: ["rank_screenshot"] }),
    ).toBe("缺：段位截圖")
    expect(
      profileStatusText({
        ...base,
        missing_fields: ["game_account_id", "rank_screenshot"],
      }),
    ).toBe("缺：遊戲 ID、段位截圖")
    expect(profileStatusText({ ...base, missing_fields: [] })).toBe("資料完成")
    expect(profileCaption(base)).toBe("")
    expect(profileCaption({ ...base, rank_tier: "鑽石" })).toBe("鑽石")
    expect(
      profileCaption({
        ...base,
        game_account_id: "Zhe#TW",
        has_rank_screenshot: true,
      }),
    ).toBe("Zhe#TW · 段位截圖：已上傳")
  })

  it.each([
    [null, 0, 4, "平均段位積分：尚無人填寫"],
    [23.33, 3, 5, "平均段位積分 23.33（3／5 人已填）"],
    [23.33, 3, 3, "平均段位積分 23.33"],
    [30, 1, 1, "平均段位積分 30.00"],
    [0.1, 2, 4, "平均段位積分 0.10（2／4 人已填）"],
  ])(
    "平均段位積分 %s（%s／%s 人已填）顯示「%s」",
    (avg, filled, total, text) => {
      expect(avgRankScoreText(avg, filled, total)).toBe(text)
    },
  )

  it("名單下方顯示平均段位積分", () => {
    render(
      <RosterList
        members={TEAM.members}
        starters={TEAM.starters}
        maxMembers={TEAM.max_members}
        avgRankScore={20}
        rankFilledCount={2}
      />,
    )

    expect(
      screen.getByText("平均段位積分 20.00（2／4 人已填）"),
    ).toBeInTheDocument()
  })
})

function renderCreateTeamDialog() {
  const rootRoute = createRootRoute({
    component: () => (
      <>
        <CreateTeamDialog tournamentId="tour-1" />
        <Outlet />
      </>
    ),
  })
  const teamRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/teams/$teamId",
    component: () => <p>隊伍頁</p>,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([teamRoute]),
    history: createMemoryHistory({ initialEntries: ["/"] }),
  })
  renderRouter(router)
  return router
}

describe("建立隊伍（S16）", () => {
  it("送出成功後導向該隊 S17", async () => {
    const user = userEvent.setup()
    signInAs()
    const create = vi
      .spyOn(RegistrationService, "createTeam")
      .mockResolvedValue({ data: TEAM } as CreateTeamResult)
    const router = renderCreateTeamDialog()

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "建立隊伍" })).toBeEnabled(),
    )
    await user.click(screen.getByRole("button", { name: "建立隊伍" }))
    const dialog = await screen.findByRole("dialog", { name: "建立隊伍" })
    await user.type(within(dialog).getByLabelText("隊名"), "  夜貓隊 ")
    await user.click(within(dialog).getByRole("button", { name: "建立隊伍" }))

    await waitFor(() =>
      expect(router.state.location.pathname).toBe("/teams/team-1"),
    )
    expect(create).toHaveBeenCalledWith({
      path: { tournament_id: "tour-1" },
      body: { name: "夜貓隊" },
    })
  })

  it("隊名空白或超過 30 字時不送出", async () => {
    const user = userEvent.setup()
    signInAs()
    const create = vi.spyOn(RegistrationService, "createTeam")
    renderCreateTeamDialog()

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "建立隊伍" })).toBeEnabled(),
    )
    await user.click(screen.getByRole("button", { name: "建立隊伍" }))
    const dialog = await screen.findByRole("dialog", { name: "建立隊伍" })
    const submit = within(dialog).getByRole("button", { name: "建立隊伍" })

    await user.type(within(dialog).getByLabelText("隊名"), "   ")
    await user.click(submit)
    expect(await within(dialog).findByText("請輸入隊名")).toBeInTheDocument()

    await user.clear(within(dialog).getByLabelText("隊名"))
    await user.type(within(dialog).getByLabelText("隊名"), "隊".repeat(31))
    await user.click(submit)
    expect(
      await within(dialog).findByText("隊名最多 30 個字"),
    ).toBeInTheDocument()
    expect(create).not.toHaveBeenCalled()
  })

  it("伺服器拒絕（隊名重複）時在表單頂部顯示原因", async () => {
    const user = userEvent.setup()
    signInAs()
    vi.spyOn(RegistrationService, "createTeam").mockRejectedValue(
      httpError(409, {
        detail: {
          code: "TEAM_NAME_TAKEN",
          message: "這個賽事已經有同名的隊伍。",
        },
      }),
    )
    renderCreateTeamDialog()

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "建立隊伍" })).toBeEnabled(),
    )
    await user.click(screen.getByRole("button", { name: "建立隊伍" }))
    const dialog = await screen.findByRole("dialog", { name: "建立隊伍" })
    await user.type(within(dialog).getByLabelText("隊名"), "夜貓隊")
    await user.click(within(dialog).getByRole("button", { name: "建立隊伍" }))

    expect(
      await within(dialog).findByText("這個賽事已經有同名的隊伍。"),
    ).toBeInTheDocument()
  })

  it("Email 未驗證：「建立隊伍」停用並說明原因", async () => {
    signInAs({ account: { ...ACCOUNT, email_verified: false } })
    renderCreateTeamDialog()

    expect(
      await screen.findByText("完成 Email 驗證後才能建立隊伍。"),
    ).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "建立隊伍" })).toBeDisabled()
  })
})

describe("Status badge（候補）", () => {
  const WAITLIST = {
    waitlist_position: null,
    waitlist_reason: null,
    representative_backfill: null,
    waitlist_phase: null,
  } as const

  it("沒有候補資訊時用狀態名；有順位、沒有順位各自的文字", () => {
    expect(registrationStatusLabel("waitlisted")).toBe("候補")
    expect(registrationStatusLabel("waitlisted", WAITLIST)).toBe("候補")
    expect(
      registrationStatusLabel("waitlisted", {
        ...WAITLIST,
        waitlist_position: 1,
        representative_backfill: false,
        waitlist_phase: "first_come",
      }),
    ).toBe("候補第 1 位")
    expect(
      registrationStatusLabel("waitlisted", {
        ...WAITLIST,
        waitlist_reason: "SCHOOL_LIMIT_REACHED",
        representative_backfill: false,
        waitlist_phase: "after_deadline",
      }),
    ).toBe("候補・目前不在遞補順序中")
    expect(registrationStatusLabel("accepted", WAITLIST)).toBe("正取")
  })

  it("不是候補時不顯示說明", () => {
    const { container } = render(
      <WaitlistDetails
        status="accepted"
        waitlist={{ ...WAITLIST, waitlist_phase: "first_come" }}
      />,
    )
    expect(container).toBeEmptyDOMElement()
  })
})
