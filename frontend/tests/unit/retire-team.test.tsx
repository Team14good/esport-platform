import { QueryClient } from "@tanstack/react-query"
import { configure, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { toast } from "sonner"
import { beforeEach, describe, expect, it, vi } from "vitest"

import {
  CompetitionService,
  RegistrationService,
  type TeamDetail,
} from "@/client"
import { nextMatchesQueryKey } from "@/features/competition/next-match-queries"
import { retirementQueryKey } from "@/features/competition/retirement-queries"
import { myTeamsQueryOptions } from "@/features/registration/queries"
import { renderApp, signInAs } from "./auth-fixtures"
import { httpError } from "./helpers"

vi.mock("@tanstack/react-router-devtools", () => ({
  TanStackRouterDevtools: () => null,
}))
vi.mock("@tanstack/react-query-devtools", () => ({
  ReactQueryDevtools: () => null,
}))

// 第一次載入路由要轉譯整棵路由樹，預設 1 秒在冷啟動時不夠
configure({ asyncUtilTimeout: 5000 })

type ReadTeamResult = Awaited<ReturnType<typeof RegistrationService.readTeam>>
type StatusResult = Awaited<
  ReturnType<typeof CompetitionService.readRetirementStatus>
>
type RetireResult = Awaited<ReturnType<typeof CompetitionService.retireTeam>>

const DESCRIPTION =
  "退賽後無法恢復。有候補隊伍時，由候補第 1 位接手你們在對戰表上的位置；沒有候補時，對手以輪空晉級。"
const PENDING_REASON = "對手確定後才能退賽。"

// 目前帳號是 acc-1（auth-fixtures 的 ACCOUNT），在這裡是隊長
const DRAWN: TeamDetail = {
  id: "team-1",
  name: "夜貓隊",
  tournament_id: "tour-1",
  tournament_name: "政大校園盃",
  game_name: "特戰英豪",
  starters: 1,
  substitutes: 0,
  max_members: 1,
  members: [
    {
      account_id: "acc-1",
      display_name: "阿哲",
      role: "captain",
      joined_at: "2026-10-30T10:00:00Z",
      game_account_id: "阿哲#TW",
      rank_tier: "鑽石",
      rank_score: 30,
      has_rank_screenshot: true,
      rank_screenshot_name: null,
      missing_fields: [],
    },
  ],
  registration_status: "drawn",
  invite_token: "tok-1",
  invite_status: "locked",
  my_role: "captain",
  rank_tiers: [{ name: "鑽石", score: 30 }],
  avg_rank_score: 30,
  rank_filled_count: 1,
  profile_editable: false,
  submit_blockers: [],
  priority_end: "2026-11-01T00:00:00Z",
  registration_end: "2026-11-08T00:00:00Z",
  submitted_at: "2026-11-03T10:00:00Z",
  waitlist_position: null,
  waitlist_reason: null,
  representative_backfill: null,
  waitlist_phase: null,
  backfilled: false,
  withdrawable: false,
}

function mockTeam(team: TeamDetail = DRAWN) {
  return vi
    .spyOn(RegistrationService, "readTeam")
    .mockResolvedValue({ data: team } as ReadTeamResult)
}

function mockStatus(retirable: boolean, reason: string | null = null) {
  return vi
    .spyOn(CompetitionService, "readRetirementStatus")
    .mockResolvedValue({ data: { retirable, reason } } as StatusResult)
}

beforeEach(() => {
  // S17 會渲染 S18；jsdom 沒有 matchMedia
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }))
  URL.createObjectURL = vi.fn(() => "blob:preview")
  URL.revokeObjectURL = vi.fn()
})

describe("抽籤後退賽（Story 4.5，S17）", () => {
  it("可退賽：按「退賽」開確認對話框，確認後 Toast「已退賽」並讓相關查詢失效", async () => {
    const user = userEvent.setup()
    const success = vi.spyOn(toast, "success")
    signInAs()
    mockTeam()
    const status = mockStatus(true)
    const retire = vi
      .spyOn(CompetitionService, "retireTeam")
      .mockResolvedValue({
        data: { match_id: "m-1", replacement_team_id: "team-9" },
      } as RetireResult)
    const invalidate = vi.spyOn(QueryClient.prototype, "invalidateQueries")
    renderApp("/teams/team-1")

    await user.click(await screen.findByRole("button", { name: "退賽" }))
    const dialog = await screen.findByRole("alertdialog")
    expect(dialog).toHaveAccessibleName("退賽")
    expect(dialog).toHaveAccessibleDescription(DESCRIPTION)
    const confirm = within(dialog).getByRole("button", { name: "退賽" })
    expect(confirm.className).toContain("destructive")
    await user.click(confirm)

    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull())
    expect(status).toHaveBeenCalledWith({ path: { team_id: "team-1" } })
    expect(retire).toHaveBeenCalledWith({ path: { team_id: "team-1" } })
    expect(success).toHaveBeenCalledWith("已退賽", expect.anything())
    for (const queryKey of [
      myTeamsQueryOptions().queryKey,
      nextMatchesQueryKey,
      retirementQueryKey("team-1"),
    ]) {
      expect(invalidate).toHaveBeenCalledWith({ queryKey })
    }
  })

  it("退賽後隊伍變「退賽」：按鈕隨之消失", async () => {
    const user = userEvent.setup()
    signInAs()
    const readTeam = mockTeam()
    mockStatus(true)
    vi.spyOn(CompetitionService, "retireTeam").mockResolvedValue({
      data: { match_id: "m-1", replacement_team_id: null },
    } as RetireResult)
    renderApp("/teams/team-1")

    await user.click(await screen.findByRole("button", { name: "退賽" }))
    // 退賽成功後重新取得的隊伍已是「退賽」
    readTeam.mockResolvedValue({
      data: { ...DRAWN, registration_status: "retired" },
    } as ReadTeamResult)
    const dialog = await screen.findByRole("alertdialog")
    await user.click(within(dialog).getByRole("button", { name: "退賽" }))

    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull())
    const header = screen
      .getByRole("heading", { level: 1, name: "夜貓隊" })
      .closest("header") as HTMLElement
    expect(await within(header).findByText("退賽")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "退賽" })).toBeNull()
  })

  it("被拒時錯誤訊息留在對話框，關閉後按鈕才消失", async () => {
    const user = userEvent.setup()
    signInAs()
    mockTeam()
    const status = mockStatus(true)
    vi.spyOn(CompetitionService, "retireTeam").mockRejectedValue(
      httpError(409, {
        detail: {
          code: "TEAM_NOT_RETIRABLE",
          message: "已有隊伍報到，無法退賽。",
        },
      }),
    )
    renderApp("/teams/team-1")

    await user.click(await screen.findByRole("button", { name: "退賽" }))
    const dialog = await screen.findByRole("alertdialog")
    // 被拒後重新取得的狀態是不可退賽（且沒有原因）
    status.mockResolvedValue({
      data: { retirable: false, reason: null },
    } as StatusResult)
    await user.click(within(dialog).getByRole("button", { name: "退賽" }))

    expect(
      await within(dialog).findByText("已有隊伍報到，無法退賽。"),
    ).toBeInTheDocument()
    await waitFor(() => expect(status).toHaveBeenCalledTimes(2))
    expect(
      within(screen.getByRole("alertdialog")).getByText(
        "已有隊伍報到，無法退賽。",
      ),
    ).toBeInTheDocument()

    await user.click(within(dialog).getByRole("button", { name: "取消" }))
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull())
    expect(screen.queryByRole("button", { name: "退賽" })).toBeNull()
  })

  it("被拒後隊伍重新取得已不是已參賽：錯誤訊息仍留在對話框，關閉後區塊才消失", async () => {
    const user = userEvent.setup()
    signInAs()
    const readTeam = mockTeam()
    mockStatus(true)
    vi.spyOn(CompetitionService, "retireTeam").mockRejectedValue(
      httpError(409, {
        detail: {
          code: "TEAM_NOT_RETIRABLE",
          message: "只有已參賽的隊伍可以退賽。",
        },
      }),
    )
    renderApp("/teams/team-1")

    await user.click(await screen.findByRole("button", { name: "退賽" }))
    const dialog = await screen.findByRole("alertdialog")
    // 被拒後重新取得的隊伍已是「退賽」（例如另一個裝置先退賽了）
    readTeam.mockResolvedValue({
      data: { ...DRAWN, registration_status: "retired" },
    } as ReadTeamResult)
    await user.click(within(dialog).getByRole("button", { name: "退賽" }))

    expect(
      await within(dialog).findByText("只有已參賽的隊伍可以退賽。"),
    ).toBeInTheDocument()
    await waitFor(() => expect(readTeam).toHaveBeenCalledTimes(2))
    expect(
      within(screen.getByRole("alertdialog")).getByText(
        "只有已參賽的隊伍可以退賽。",
      ),
    ).toBeInTheDocument()

    await user.click(within(dialog).getByRole("button", { name: "取消" }))
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull())
    expect(screen.queryByRole("button", { name: "退賽" })).toBeNull()
  })

  it("對手未定又沒有候補：按鈕停用並顯示原因", async () => {
    signInAs()
    mockTeam()
    mockStatus(false, PENDING_REASON)
    renderApp("/teams/team-1")

    const button = await screen.findByRole("button", { name: "退賽" })
    expect(button).toBeDisabled()
    expect(button).toHaveAccessibleDescription(PENDING_REASON)
    expect(screen.getByText(PENDING_REASON)).toBeInTheDocument()
  })

  it("不可退賽且沒有原因：看不到按鈕", async () => {
    signInAs()
    mockTeam()
    const status = mockStatus(false)
    renderApp("/teams/team-1")

    await screen.findByRole("heading", { level: 1, name: "夜貓隊" })
    await waitFor(() => expect(status).toHaveBeenCalled())
    expect(screen.queryByRole("button", { name: "退賽" })).toBeNull()
  })

  it("隊員不是隊長：不查詢也看不到按鈕", async () => {
    signInAs()
    mockTeam({ ...DRAWN, my_role: "player" })
    const status = mockStatus(true)
    renderApp("/teams/team-1")

    await screen.findByRole("heading", { level: 1, name: "夜貓隊" })
    expect(screen.queryByRole("button", { name: "退賽" })).toBeNull()
    expect(status).not.toHaveBeenCalled()
  })

  it.each(["accepted", "waitlisted", "retired"] as const)(
    "報名是 %s：不查詢退賽狀態",
    async (registration_status) => {
      signInAs()
      mockTeam({ ...DRAWN, registration_status })
      const status = mockStatus(true)
      renderApp("/teams/team-1")

      await screen.findByRole("heading", { level: 1, name: "夜貓隊" })
      expect(screen.queryByRole("button", { name: "退賽" })).toBeNull()
      expect(status).not.toHaveBeenCalled()
    },
  )
})
