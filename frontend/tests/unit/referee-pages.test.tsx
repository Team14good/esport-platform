import { focusManager } from "@tanstack/react-query"
import { createMemoryHistory, createRouter } from "@tanstack/react-router"
import { act, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { toast } from "sonner"
import { beforeAll, describe, expect, it, vi } from "vitest"

import {
  IdentityService,
  type PublicRefereeInvitation,
  type RefereeInvitationRead,
  type RefereeRead,
  type TournamentRead,
  TournamentsService,
} from "@/client"
import { formatMatchDateTime } from "@/features/competition/match-time"
import { COPIED_TEXT } from "@/features/registration/InviteLinkField"
import {
  INVITE_EXPIRED_TEXT,
  INVITE_NOT_FOUND_TEXT,
  ORGANIZER_CANNOT_BE_REFEREE_TEXT,
} from "@/features/tournaments/RefereeInvitePage"
import {
  NO_INVITATION_TEXT,
  NO_REFEREES_DESCRIPTION,
  NO_REFEREES_TITLE,
  REGENERATE_DESCRIPTION,
} from "@/features/tournaments/RefereesPage"
import { NOT_ACCEPTING_TEXT } from "@/features/tournaments/referee-queries"
import { routeTree } from "@/routeTree.gen"
import { ACCOUNT, renderApp, signInAs } from "./auth-fixtures"
import { httpError } from "./helpers"

vi.mock("@tanstack/react-router-devtools", () => ({
  TanStackRouterDevtools: () => null,
}))
vi.mock("@tanstack/react-query-devtools", () => ({
  ReactQueryDevtools: () => null,
}))

type ReadMyTournamentResult = Awaited<
  ReturnType<typeof TournamentsService.readMyTournament>
>
type ReadInvitationResult = Awaited<
  ReturnType<typeof TournamentsService.readRefereeInvitation>
>
type CreateInvitationResult = Awaited<
  ReturnType<typeof TournamentsService.createRefereeInvitation>
>
type ListRefereesResult = Awaited<
  ReturnType<typeof TournamentsService.listTournamentReferees>
>
type PreviewResult = Awaited<
  ReturnType<typeof TournamentsService.previewRefereeInvitation>
>
type AcceptResult = Awaited<
  ReturnType<typeof TournamentsService.acceptRefereeInvitation>
>

const ORGANIZER = { ...ACCOUNT, is_organizer: true }
const S31_URL = "/organizer/tournaments/t-1/referees"
const S23_URL = "/referee-invite/tok-1"

const TOURNAMENT = {
  id: "t-1",
  organizer_id: ORGANIZER.id,
  name: "臺大秋季盃",
  status: "open",
} as TournamentRead

const INVITATION: RefereeInvitationRead = {
  tournament_id: "t-1",
  token: "tok-1",
  created_at: "2026-11-05T02:00:00Z",
  expires_at: "2026-11-12T02:00:00Z",
  expired: false,
  accepting: true,
}

const NEW_INVITATION: RefereeInvitationRead = {
  ...INVITATION,
  token: "tok-2",
  created_at: "2026-11-05T03:00:00Z",
  expires_at: "2026-11-12T03:00:00Z",
}

const referee = (id: string, name: string, acceptedAt: string) =>
  ({
    account_id: id,
    display_name: name,
    accepted_at: acceptedAt,
  }) satisfies RefereeRead

const PREVIEW: PublicRefereeInvitation = {
  tournament_name: "臺大秋季盃",
  expires_at: "2026-11-12T02:00:00Z",
  expired: false,
  accepting: true,
}

const inviteUrl = (token: string) =>
  `${window.location.origin}/referee-invite/${token}`

function business(status: number, code: string, message = "伺服器訊息") {
  return httpError(status, { detail: { code, message } })
}

// 路由以 autoCodeSplitting 延遲載入：先載入本檔用到的路由，讓每個測試只等待畫面本身
beforeAll(async () => {
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: ["/"] }),
  })
  await Promise.all(
    (
      [
        "/organizer/tournaments/$tournamentId",
        "/organizer/tournaments/$tournamentId/referees",
        "/referee-invite/$inviteToken",
      ] as const
    ).map((path) => router.loadRouteChunk(router.routesByPath[path])),
  )
}, 30_000)

// ---------------------------------------------------------------- S31

function mockInvitation(invitation: RefereeInvitationRead | null = INVITATION) {
  // 從未產生過時後端回 null，但產生的 client 會把 null 回應換成 {}（`data ?? {}`）
  return vi
    .spyOn(TournamentsService, "readRefereeInvitation")
    .mockResolvedValue({
      data: invitation ?? {},
    } as ReadInvitationResult)
}

function mockReferees(referees: RefereeRead[] = []) {
  return vi
    .spyOn(TournamentsService, "listTournamentReferees")
    .mockResolvedValue({ data: referees } as ListRefereesResult)
}

function mockCreate(created: RefereeInvitationRead = NEW_INVITATION) {
  return vi
    .spyOn(TournamentsService, "createRefereeInvitation")
    .mockResolvedValue({ data: created } as CreateInvitationResult)
}

function openS31(tournament: TournamentRead = TOURNAMENT) {
  vi.spyOn(TournamentsService, "readMyTournament").mockResolvedValue({
    data: tournament,
  } as ReadMyTournamentResult)
  signInAs({ account: ORGANIZER })
  return renderApp(S31_URL)
}

function sidebar(): HTMLElement {
  return document.querySelector("[data-slot=backoffice-sidebar]") as HTMLElement
}

describe("S31 裁判管理：邀請連結", () => {
  it("側欄有「裁判」；有效連結顯示網址、「複製連結」、到期時間與「產生新連結」", async () => {
    const user = userEvent.setup()
    const success = vi.spyOn(toast, "success")
    mockInvitation()
    mockReferees()
    openS31()

    const input = await screen.findByLabelText("裁判邀請連結")
    expect(input).toHaveValue(inviteUrl("tok-1"))
    expect(
      within(sidebar()).getByRole("link", { name: "裁判" }),
    ).toHaveAttribute("href", S31_URL)
    expect(
      screen.getByText(`${formatMatchDateTime(INVITATION.expires_at)} 到期`),
    ).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "產生新連結" })).toBeEnabled()

    await user.click(screen.getByRole("button", { name: "複製連結" }))
    expect(await navigator.clipboard.readText()).toBe(inviteUrl("tok-1"))
    expect(success).toHaveBeenCalledWith(COPIED_TEXT, { duration: 3000 })
  })

  it("從未產生：說明文字＋「產生邀請連結」，按下後顯示連結與到期時間", async () => {
    const user = userEvent.setup()
    const read = mockInvitation(null)
    mockReferees()
    const create = mockCreate()
    openS31()

    expect(await screen.findByText(NO_INVITATION_TEXT)).toBeInTheDocument()
    expect(screen.queryByLabelText("裁判邀請連結")).toBeNull()
    await user.click(screen.getByRole("button", { name: "產生邀請連結" }))

    expect(await screen.findByLabelText("裁判邀請連結")).toHaveValue(
      inviteUrl("tok-2"),
    )
    expect(create).toHaveBeenCalledWith({ path: { tournament_id: "t-1" } })
    // 以產生的回應填入快取，不再多抓一次目前邀請
    expect(read).toHaveBeenCalledTimes(1)
    expect(
      screen.getByText(
        `${formatMatchDateTime(NEW_INVITATION.expires_at)} 到期`,
      ),
    ).toBeInTheDocument()
  })

  it("產生失敗顯示錯誤 Toast", async () => {
    const user = userEvent.setup()
    const error = vi.spyOn(toast, "error")
    mockInvitation(null)
    mockReferees()
    vi.spyOn(TournamentsService, "createRefereeInvitation").mockRejectedValue(
      business(409, "TOURNAMENT_NOT_ACCEPTING_REFEREES", "不能再邀請裁判。"),
    )
    openS31()

    await user.click(
      await screen.findByRole("button", { name: "產生邀請連結" }),
    )

    await waitFor(() =>
      expect(error).toHaveBeenCalledWith(
        "不能再邀請裁判。",
        expect.objectContaining({ id: "不能再邀請裁判。" }),
      ),
    )
    expect(screen.queryByLabelText("裁判邀請連結")).toBeNull()
  })

  it("已過期：「連結已過期」、停用複製，「產生新連結」不確認直接產生", async () => {
    const user = userEvent.setup()
    mockInvitation({ ...INVITATION, expired: true })
    mockReferees()
    const create = mockCreate()
    openS31()

    expect(await screen.findByText("連結已過期")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "複製連結" })).toBeDisabled()
    expect(screen.queryByText(/到期$/)).toBeNull()

    await user.click(screen.getByRole("button", { name: "產生新連結" }))

    expect(screen.queryByRole("alertdialog")).toBeNull()
    expect(await screen.findByLabelText("裁判邀請連結")).toHaveValue(
      inviteUrl("tok-2"),
    )
    expect(create).toHaveBeenCalledTimes(1)
    expect(screen.getByRole("button", { name: "複製連結" })).toBeEnabled()
  })

  it("舊連結仍有效：先確認；取消則不變", async () => {
    const user = userEvent.setup()
    mockInvitation()
    mockReferees()
    const create = mockCreate()
    openS31()

    await user.click(await screen.findByRole("button", { name: "產生新連結" }))
    const dialog = await screen.findByRole("alertdialog")
    expect(
      within(dialog).getByRole("heading", { name: "產生新連結" }),
    ).toBeInTheDocument()
    expect(within(dialog).getByText(REGENERATE_DESCRIPTION)).toBeInTheDocument()

    await user.click(within(dialog).getByRole("button", { name: "取消" }))

    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull())
    expect(create).not.toHaveBeenCalled()
    expect(screen.getByLabelText("裁判邀請連結")).toHaveValue(
      inviteUrl("tok-1"),
    )
  })

  it("舊連結仍有效：確認後產生新連結，以回應更新連結", async () => {
    const user = userEvent.setup()
    const read = mockInvitation()
    mockReferees()
    const create = mockCreate()
    openS31()

    await user.click(await screen.findByRole("button", { name: "產生新連結" }))
    const dialog = await screen.findByRole("alertdialog")
    await user.click(within(dialog).getByRole("button", { name: "產生新連結" }))

    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull())
    expect(create).toHaveBeenCalledTimes(1)
    expect(screen.getByLabelText("裁判邀請連結")).toHaveValue(
      inviteUrl("tok-2"),
    )
    expect(read).toHaveBeenCalledTimes(1)
  })

  it("舊連結仍有效：確認後產生失敗，對話框顯示錯誤、連結不變，並重新取得目前邀請", async () => {
    const user = userEvent.setup()
    const read = mockInvitation()
    mockReferees()
    vi.spyOn(TournamentsService, "createRefereeInvitation").mockRejectedValue(
      business(409, "TOURNAMENT_NOT_ACCEPTING_REFEREES", "不能再邀請裁判。"),
    )
    openS31()

    await user.click(await screen.findByRole("button", { name: "產生新連結" }))
    const dialog = await screen.findByRole("alertdialog")
    await user.click(within(dialog).getByRole("button", { name: "產生新連結" }))

    expect(
      await within(dialog).findByText("不能再邀請裁判。"),
    ).toBeInTheDocument()
    expect(screen.getByLabelText("裁判邀請連結")).toHaveValue(
      inviteUrl("tok-1"),
    )
    // 失敗後重抓，`accepting` 等狀態以伺服器為準
    await waitFor(() => expect(read).toHaveBeenCalledTimes(2))
  })

  it("賽事已結束或已取消：停用複製與「產生新連結」並寫出原因", async () => {
    mockInvitation({ ...INVITATION, accepting: false })
    mockReferees()
    openS31({ ...TOURNAMENT, status: "finished" })

    expect(
      await screen.findByText(`：${NOT_ACCEPTING_TEXT}`),
    ).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "複製連結" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "產生新連結" })).toBeDisabled()
  })

  it("賽事已結束且從未產生：停用「產生邀請連結」並寫出原因", async () => {
    mockInvitation(null)
    mockReferees()
    openS31({ ...TOURNAMENT, status: "cancelled" })

    expect(await screen.findByText(NOT_ACCEPTING_TEXT)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "產生邀請連結" })).toBeDisabled()
  })
})

describe("S31 裁判管理：裁判名單", () => {
  it("依接受時間列出顯示名稱與接受時間（卡片版面，375 px 不橫向捲動）", async () => {
    mockInvitation()
    // 故意不照順序回傳
    mockReferees([
      referee("r-3", "陳裁判", "2026-11-03T05:00:00Z"),
      referee("r-1", "王裁判", "2026-11-01T05:00:00Z"),
      referee(
        "r-2",
        "很長很長很長很長很長很長很長的裁判名字",
        "2026-11-02T05:00:00Z",
      ),
    ])
    openS31()

    const list = await screen.findByRole("list", { name: "裁判名單" })
    const items = within(list).getAllByRole("listitem")
    expect(items.map((item) => item.firstElementChild?.textContent)).toEqual([
      "王裁判",
      "很長很長很長很長很長很長很長的裁判名字",
      "陳裁判",
    ])
    expect(
      within(items[0]).getByText(
        `${formatMatchDateTime("2026-11-01T05:00:00Z")} 接受`,
      ),
    ).toBeInTheDocument()
    // jsdom 不排版：確認 375 px 時卡片上下排列、長名字換行，≥ sm 才左右排
    expect(items[1]).toHaveClass("flex-col", "min-w-0", "sm:flex-row")
    expect(items[1].firstElementChild).toHaveClass("min-w-0", "break-words")
  })

  it("沒有裁判：空狀態文案", async () => {
    mockInvitation()
    mockReferees([])
    openS31()

    expect(await screen.findByText(NO_REFEREES_TITLE)).toBeInTheDocument()
    expect(screen.getByText(NO_REFEREES_DESCRIPTION)).toBeInTheDocument()
    expect(NO_REFEREES_TITLE + NO_REFEREES_DESCRIPTION).toBe(
      "還沒有裁判接受邀請。複製邀請連結傳給裁判。",
    )
  })

  it("讀取失敗：顯示錯誤＋「重新載入」", async () => {
    const user = userEvent.setup()
    mockInvitation()
    const list = vi
      .spyOn(TournamentsService, "listTournamentReferees")
      .mockRejectedValue(
        business(409, "SOMETHING_WRONG", "暫時無法取得裁判名單。"),
      )
    openS31()

    expect(
      await screen.findByText("暫時無法取得裁判名單。"),
    ).toBeInTheDocument()
    list.mockResolvedValue({
      data: [referee("r-1", "王裁判", "2026-11-01T05:00:00Z")],
    } as ListRefereesResult)
    await user.click(screen.getByRole("button", { name: "重新載入" }))

    expect(await screen.findByText("王裁判")).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------- S23

function mockPreview(preview: PublicRefereeInvitation = PREVIEW) {
  return vi
    .spyOn(TournamentsService, "previewRefereeInvitation")
    .mockResolvedValue({ data: preview } as PreviewResult)
}

async function clickAccept(user: ReturnType<typeof userEvent.setup>) {
  const button = await screen.findByRole("button", { name: "接受邀請" })
  await waitFor(() => expect(button).toBeEnabled())
  await user.click(button)
}

describe("S23 接受裁判邀請", () => {
  it("已驗證：顯示賽事名稱與到期時間，接受後顯示已成為裁判並讓身分清單重抓", async () => {
    const user = userEvent.setup()
    const { listIdentities } = signInAs()
    mockPreview()
    const accept = vi
      .spyOn(TournamentsService, "acceptRefereeInvitation")
      .mockResolvedValue({
        data: referee(ACCOUNT.id, ACCOUNT.display_name, "2026-11-05T03:00:00Z"),
      } as AcceptResult)
    renderApp(S23_URL)

    expect(await screen.findByText("臺大秋季盃")).toBeInTheDocument()
    expect(
      screen.getByText(`${formatMatchDateTime(PREVIEW.expires_at)} 到期`),
    ).toBeInTheDocument()
    await waitFor(() => expect(listIdentities).toHaveBeenCalled())
    const before = listIdentities.mock.calls.length
    await clickAccept(user)

    expect(
      await screen.findByText("你已成為「臺大秋季盃」的裁判"),
    ).toBeInTheDocument()
    expect(accept).toHaveBeenCalledWith({ path: { token: "tok-1" } })
    expect(
      screen.getByRole("link", { name: "查看我執法的場次" }),
    ).toHaveAttribute("href", "/me/referee")
    expect(screen.queryByRole("button", { name: "接受邀請" })).toBeNull()
    await waitFor(() =>
      expect(listIdentities.mock.calls.length).toBeGreaterThan(before),
    )
  })

  it("未登入：不需登入即可預覽，提供註冊與登入（帶 redirect 回 S23）", async () => {
    const preview = mockPreview()
    const readAccount = vi.spyOn(IdentityService, "readCurrentAccount")
    renderApp(S23_URL)

    expect(await screen.findByText("臺大秋季盃")).toBeInTheDocument()
    expect(preview).toHaveBeenCalledWith({ path: { token: "tok-1" } })
    expect(readAccount).not.toHaveBeenCalled()
    expect(screen.getByRole("link", { name: "註冊帳號" })).toHaveAttribute(
      "href",
      "/signup?redirect=%2Freferee-invite%2Ftok-1",
    )
    // 頂欄也有「登入」：限定在 S23 的內容裡
    const page = within(
      screen
        .getByRole("heading", { name: "裁判邀請" })
        .closest("section") as HTMLElement,
    )
    expect(page.getByRole("link", { name: "登入" })).toHaveAttribute(
      "href",
      "/login?redirect=%2Freferee-invite%2Ftok-1",
    )
    expect(screen.queryByRole("button", { name: "接受邀請" })).toBeNull()
  })

  it("未驗證 Email：「接受邀請」停用並提示驗證", async () => {
    signInAs({ account: { ...ACCOUNT, email_verified: false } })
    mockPreview()
    renderApp(S23_URL)

    expect(
      await screen.findByText("完成 Email 驗證後才能接受裁判邀請。"),
    ).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "接受邀請" })).toBeDisabled()
  })

  it("預覽已過期：顯示過期文案，不提供「接受邀請」", async () => {
    signInAs()
    mockPreview({ ...PREVIEW, expired: true })
    renderApp(S23_URL)

    expect(await screen.findByText(INVITE_EXPIRED_TEXT)).toBeInTheDocument()
    expect(INVITE_EXPIRED_TEXT).toBe("此裁判邀請已過期，請向主辦方索取新連結。")
    expect(screen.queryByRole("button", { name: "接受邀請" })).toBeNull()
  })

  it("已過期且賽事已結束：先顯示過期文案（與後端的檢查順序一致）", async () => {
    signInAs()
    mockPreview({ ...PREVIEW, expired: true, accepting: false })
    renderApp(S23_URL)

    expect(await screen.findByText(INVITE_EXPIRED_TEXT)).toBeInTheDocument()
    expect(screen.queryByText(NOT_ACCEPTING_TEXT)).toBeNull()
    expect(screen.queryByRole("button", { name: "接受邀請" })).toBeNull()
  })

  it("未登入且已過期：同樣只顯示過期文案", async () => {
    mockPreview({ ...PREVIEW, expired: true })
    renderApp(S23_URL)

    expect(await screen.findByText(INVITE_EXPIRED_TEXT)).toBeInTheDocument()
    expect(screen.queryByRole("link", { name: "註冊帳號" })).toBeNull()
  })

  it("接受時才發現已過期（REFEREE_INVITATION_EXPIRED）：顯示過期文案", async () => {
    const user = userEvent.setup()
    signInAs()
    const preview = mockPreview()
    vi.spyOn(TournamentsService, "acceptRefereeInvitation").mockRejectedValue(
      business(409, "REFEREE_INVITATION_EXPIRED"),
    )
    renderApp(S23_URL)

    const button = await screen.findByRole("button", { name: "接受邀請" })
    await waitFor(() => expect(button).toBeEnabled())
    // 接受失敗後重抓預覽時回傳已過期
    preview.mockResolvedValue({
      data: { ...PREVIEW, expired: true },
    } as PreviewResult)
    await user.click(button)

    expect(await screen.findByText(INVITE_EXPIRED_TEXT)).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "接受邀請" })).toBeNull()
    // 重抓預覽後卡片不再顯示「{時間} 到期」
    expect(await screen.findByText("連結已過期")).toBeInTheDocument()
    expect(preview).toHaveBeenCalledTimes(2)
  })

  it("已有預覽時背景重抓失敗：保留卡片與接受成功的狀態", async () => {
    const user = userEvent.setup()
    signInAs()
    const preview = mockPreview()
    vi.spyOn(TournamentsService, "acceptRefereeInvitation").mockResolvedValue({
      data: referee(ACCOUNT.id, ACCOUNT.display_name, "2026-11-05T03:00:00Z"),
    } as AcceptResult)
    renderApp(S23_URL)

    await clickAccept(user)
    expect(
      await screen.findByText("你已成為「臺大秋季盃」的裁判"),
    ).toBeInTheDocument()
    // 業務錯誤不重試：重抓一次就進入錯誤狀態
    preview.mockRejectedValue(business(409, "SOMETHING_WRONG", "讀取失敗。"))
    // 模擬切到別的視窗再切回來，觸發背景重抓
    try {
      act(() => {
        focusManager.setFocused(false)
        focusManager.setFocused(true)
      })
      await waitFor(() => expect(preview).toHaveBeenCalledTimes(2))
      // 等重抓的錯誤寫進查詢、畫面重新渲染後再斷言
      await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 50))
      })
    } finally {
      focusManager.setFocused(undefined)
    }

    expect(screen.getByText("你已成為「臺大秋季盃」的裁判")).toBeInTheDocument()
    expect(screen.queryByText("讀取失敗。")).toBeNull()
    expect(screen.queryByRole("button", { name: "重新載入" })).toBeNull()
  })

  it("邀請不存在（404）：「找不到這個裁判邀請」＋回首頁", async () => {
    vi.spyOn(TournamentsService, "previewRefereeInvitation").mockRejectedValue(
      business(404, "REFEREE_INVITATION_NOT_FOUND", "找不到這個裁判邀請。"),
    )
    renderApp("/referee-invite/nope")

    expect(await screen.findByText(INVITE_NOT_FOUND_TEXT)).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "回到首頁" })).toHaveAttribute(
      "href",
      "/",
    )
  })

  it("主辦方本人接受（ORGANIZER_CANNOT_BE_REFEREE）：顯示繁中說明", async () => {
    const user = userEvent.setup()
    signInAs({ account: ORGANIZER })
    mockPreview()
    vi.spyOn(TournamentsService, "acceptRefereeInvitation").mockRejectedValue(
      business(409, "ORGANIZER_CANNOT_BE_REFEREE"),
    )
    renderApp(S23_URL)

    await clickAccept(user)

    expect(
      await screen.findByText(ORGANIZER_CANNOT_BE_REFEREE_TEXT),
    ).toBeInTheDocument()
    expect(ORGANIZER_CANNOT_BE_REFEREE_TEXT).toBe(
      "主辦方不能擔任自己賽事的裁判。",
    )
    expect(screen.queryByRole("button", { name: "接受邀請" })).toBeNull()
  })

  it("賽事已結束或已取消（accepting: false）：不提供「接受邀請」並寫出原因", async () => {
    signInAs()
    mockPreview({ ...PREVIEW, accepting: false })
    renderApp(S23_URL)

    expect(await screen.findByText(NOT_ACCEPTING_TEXT)).toBeInTheDocument()
    expect(NOT_ACCEPTING_TEXT).toBe(
      "這場賽事已結束或已取消，無法接受裁判邀請。",
    )
    expect(screen.queryByRole("button", { name: "接受邀請" })).toBeNull()
  })

  it("接受時賽事已結束（TOURNAMENT_NOT_ACCEPTING_REFEREES）：寫出同一原因", async () => {
    const user = userEvent.setup()
    signInAs()
    mockPreview()
    vi.spyOn(TournamentsService, "acceptRefereeInvitation").mockRejectedValue(
      business(409, "TOURNAMENT_NOT_ACCEPTING_REFEREES"),
    )
    renderApp(S23_URL)

    await clickAccept(user)

    expect(await screen.findByText(NOT_ACCEPTING_TEXT)).toBeInTheDocument()
  })

  it("接受時邀請已不存在（REFEREE_INVITATION_NOT_FOUND）：「找不到這個裁判邀請」", async () => {
    const user = userEvent.setup()
    signInAs()
    mockPreview()
    vi.spyOn(TournamentsService, "acceptRefereeInvitation").mockRejectedValue(
      business(404, "REFEREE_INVITATION_NOT_FOUND"),
    )
    renderApp(S23_URL)

    await clickAccept(user)

    expect(await screen.findByText(INVITE_NOT_FOUND_TEXT)).toBeInTheDocument()
  })

  it("其他錯誤（500）：顯示「伺服器發生錯誤（500）」並保留「接受邀請」可重試", async () => {
    const user = userEvent.setup()
    signInAs()
    mockPreview()
    vi.spyOn(TournamentsService, "acceptRefereeInvitation").mockRejectedValue(
      httpError(500, {}),
    )
    renderApp(S23_URL)

    await clickAccept(user)

    expect(await screen.findByText("伺服器發生錯誤（500）")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "接受邀請" })).toBeEnabled()
  })
})
