import { screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { toast } from "sonner"
import { describe, expect, it, vi } from "vitest"

import {
  type AdminOrganizerApplication,
  IdentityService,
  type OrganizerApplicationPage,
} from "@/client"
import {
  FILTERED_EMPTY_TEXT,
  PENDING_EMPTY_TEXT,
  REJECT_DESCRIPTION_TEXT,
} from "@/features/identity/AdminApplicationsPage"
import {
  APPROVED_TOAST_TEXT,
  parseFilter,
  parsePage,
  REJECTED_TOAST_TEXT,
} from "@/features/identity/admin-applications"
import { FORBIDDEN_FALLBACK_MESSAGE } from "@/lib/api-error"
import { ACCOUNT, renderApp, signInAs } from "./auth-fixtures"
import { httpError } from "./helpers"

vi.mock("@tanstack/react-router-devtools", () => ({
  TanStackRouterDevtools: () => null,
}))
vi.mock("@tanstack/react-query-devtools", () => ({
  ReactQueryDevtools: () => null,
}))

type ListResult = Awaited<
  ReturnType<typeof IdentityService.listOrganizerApplications>
>
type ApproveResult = Awaited<
  ReturnType<typeof IdentityService.approveOrganizerApplication>
>
type RejectResult = Awaited<
  ReturnType<typeof IdentityService.rejectOrganizerApplication>
>

const ADMIN = { ...ACCOUNT, is_platform_admin: true }

const PENDING: AdminOrganizerApplication = {
  id: "app-1",
  club_name: "臺大電競社",
  school_id: "school-ntu",
  school_name: "國立臺灣大學",
  status: "pending",
  reject_reason: null,
  // 台北時間 2026/10/29 14:05
  created_at: "2026-10-29T06:05:00Z",
  applicant_display_name: "阿明",
  applicant_email: "ming@example.com",
}

const APPROVED: AdminOrganizerApplication = {
  ...PENDING,
  id: "app-2",
  club_name: "清大電競社",
  status: "approved",
}

function page(
  items: AdminOrganizerApplication[],
  overrides: Partial<OrganizerApplicationPage> = {},
): ListResult {
  return {
    data: { items, total: items.length, page: 1, page_size: 20, ...overrides },
  } as ListResult
}

function mockList(result: ListResult = page([PENDING])) {
  return vi
    .spyOn(IdentityService, "listOrganizerApplications")
    .mockResolvedValue(result)
}

function tableArea(): HTMLElement {
  return document.querySelector("[data-slot=data-table]") as HTMLElement
}

function cardArea(): HTMLElement {
  return document.querySelector("[data-slot=data-table-cards]") as HTMLElement
}

describe("S35 網址參數", () => {
  it("預設值（待審核、第 1 頁）與不認得的值都不留在網址上", () => {
    expect(parseFilter("approved")).toBe("approved")
    expect(parseFilter("all")).toBe("all")
    expect(parseFilter("pending")).toBeUndefined()
    expect(parseFilter("deleted")).toBeUndefined()
    expect(parsePage(3)).toBe(3)
    expect(parsePage("2")).toBe(2)
    expect(parsePage(1)).toBeUndefined()
    expect(parsePage(0)).toBeUndefined()
    expect(parsePage(1.5)).toBeUndefined()
    expect(parsePage("abc")).toBeUndefined()
  })
})

describe("S35 主辦方申請審核", () => {
  it("未登入：導向 S6 並帶 redirect", async () => {
    const router = renderApp("/admin/applications")

    await screen.findByRole("heading", { name: "登入" })
    expect(router.state.location.search).toEqual({
      redirect: "/admin/applications",
    })
  })

  it("不是平台管理員：顯示 S38 的 403，不呼叫審核 API", async () => {
    const list = mockList()
    signInAs()
    renderApp("/admin/applications")

    expect(
      await screen.findByRole("heading", { name: FORBIDDEN_FALLBACK_MESSAGE }),
    ).toBeInTheDocument()
    expect(list).not.toHaveBeenCalled()
  })

  it("/admin 直接到 S35", async () => {
    mockList()
    signInAs({ account: ADMIN })
    const router = renderApp("/admin")

    await screen.findByRole("heading", { name: "主辦方申請" })
    expect(router.state.location.pathname).toBe("/admin/applications")
  })

  it("預設篩選「待審核」第 1 頁；欄位與 Status badge；只有待審核列有審核按鈕", async () => {
    const list = mockList(page([PENDING, APPROVED]))
    signInAs({ account: ADMIN })
    renderApp("/admin/applications")

    await screen.findByRole("table", { name: "主辦方申請" })
    const table = within(tableArea()).getByRole("table", {
      name: "主辦方申請",
    })
    expect(list).toHaveBeenCalledWith({
      query: { status: "pending", page: 1 },
    })
    expect(
      within(table)
        .getAllByRole("columnheader")
        .map((header) => header.textContent),
    ).toEqual(["社團名稱", "學校", "申請人", "送出時間", "狀態", "操作"])
    const [, pendingRow, approvedRow] = within(table).getAllByRole("row")
    expect(within(pendingRow).getByText("臺大電競社")).toBeInTheDocument()
    expect(within(pendingRow).getByText("國立臺灣大學")).toBeInTheDocument()
    expect(within(pendingRow).getByText("阿明")).toBeInTheDocument()
    expect(within(pendingRow).getByText("ming@example.com")).toBeInTheDocument()
    expect(within(pendingRow).getByText("2026/10/29 14:05")).toHaveAttribute(
      "datetime",
      "2026-10-29T06:05:00Z",
    )
    expect(within(pendingRow).getByText("待審核")).toHaveAttribute(
      "data-slot",
      "status-badge",
    )
    expect(
      within(pendingRow).getByRole("button", { name: "核准" }),
    ).toBeInTheDocument()
    expect(
      within(pendingRow).getByRole("button", { name: "退回申請" }),
    ).toBeInTheDocument()
    expect(within(approvedRow).getByText("核准")).toHaveAttribute(
      "data-tone",
      "confirmed",
    )
    expect(within(approvedRow).queryByRole("button")).toBeNull()
    expect(screen.getByRole("combobox", { name: "狀態" })).toHaveTextContent(
      "待審核",
    )
  })

  it("< md 卡片清單：每筆一張卡片，也有審核按鈕", async () => {
    mockList()
    signInAs({ account: ADMIN })
    renderApp("/admin/applications")

    await screen.findByRole("table", { name: "主辦方申請" })
    const [card] = within(cardArea()).getAllByRole("listitem")
    expect(
      within(card)
        .getAllByRole("term")
        .map((term) => term.textContent),
    ).toEqual(["社團名稱", "學校", "申請人", "送出時間", "狀態", "操作"])
    expect(
      within(card).getByRole("button", { name: "核准" }),
    ).toBeInTheDocument()
  })

  it.each([
    ["待審核", "/admin/applications", PENDING_EMPTY_TEXT],
    ["其他篩選", "/admin/applications?status=rejected", FILTERED_EMPTY_TEXT],
  ])("沒有資料（%s）：Empty state", async (_, url, text) => {
    mockList(page([]))
    signInAs({ account: ADMIN })
    renderApp(url)

    expect(await screen.findByText(text)).toBeInTheDocument()
    expect(screen.queryByRole("table")).toBeNull()
  })

  it("換篩選：寫入網址並回到第 1 頁；「全部」不帶 status", async () => {
    const user = userEvent.setup()
    const list = mockList(page([PENDING], { total: 45, page: 2 }))
    signInAs({ account: ADMIN })
    const router = renderApp("/admin/applications?page=2")

    await screen.findByRole("table", { name: "主辦方申請" })
    expect(list).toHaveBeenLastCalledWith({
      query: { status: "pending", page: 2 },
    })

    await user.click(screen.getByRole("combobox", { name: "狀態" }))
    await user.click(await screen.findByRole("option", { name: "核准" }))

    await waitFor(() =>
      expect(router.state.location.search).toEqual({ status: "approved" }),
    )
    expect(list).toHaveBeenLastCalledWith({
      query: { status: "approved", page: 1 },
    })

    await user.click(screen.getByRole("combobox", { name: "狀態" }))
    await user.click(await screen.findByRole("option", { name: "全部" }))

    await waitFor(() =>
      expect(router.state.location.search).toEqual({ status: "all" }),
    )
    expect(list).toHaveBeenLastCalledWith({
      query: { status: undefined, page: 1 },
    })
  })

  it("換頁：寫入網址並保留篩選", async () => {
    const user = userEvent.setup()
    const list = mockList(page([PENDING], { total: 45 }))
    signInAs({ account: ADMIN })
    const router = renderApp("/admin/applications?status=rejected")

    await screen.findByRole("table", { name: "主辦方申請" })
    await user.click(screen.getByRole("button", { name: "下一頁" }))

    await waitFor(() =>
      expect(router.state.location.search).toEqual({
        status: "rejected",
        page: 2,
      }),
    )
    expect(list).toHaveBeenLastCalledWith({
      query: { status: "rejected", page: 2 },
    })
  })

  it("頁碼超出（最後一頁都審核完）：換到最後一頁", async () => {
    const list = vi
      .spyOn(IdentityService, "listOrganizerApplications")
      .mockImplementation(
        // 產生的 client 回傳型別含錯誤分支，這裡只模擬成功的回應
        (async (options?: { query?: { page?: number } }) =>
          options?.query?.page === 3
            ? page([], { total: 21, page: 3 })
            : page([PENDING], {
                total: 21,
                page: 2,
              })) as unknown as typeof IdentityService.listOrganizerApplications,
      )
    signInAs({ account: ADMIN })
    const router = renderApp("/admin/applications?page=3")

    await waitFor(() =>
      expect(router.state.location.search).toEqual({ page: 2 }),
    )
    expect(list).toHaveBeenLastCalledWith({
      query: { status: "pending", page: 2 },
    })
  })

  it("核准：確認對話框寫後果，確認後 Toast 並重新整理列表", async () => {
    const user = userEvent.setup()
    const success = vi.spyOn(toast, "success")
    const list = mockList()
    const approve = vi
      .spyOn(IdentityService, "approveOrganizerApplication")
      .mockResolvedValue({
        data: { ...PENDING, status: "approved" },
      } as ApproveResult)
    signInAs({ account: ADMIN })
    renderApp("/admin/applications")

    const table = await screen.findByRole("table", { name: "主辦方申請" })
    await user.click(within(table).getByRole("button", { name: "核准" }))

    const dialog = await screen.findByRole("alertdialog", {
      name: "核准主辦方申請",
    })
    expect(dialog).toHaveAccessibleDescription(
      "核准後，阿明 會立即取得主辦方權限。",
    )
    const callsBefore = list.mock.calls.length
    await user.click(within(dialog).getByRole("button", { name: "核准" }))

    expect(approve).toHaveBeenCalledWith({ path: { application_id: "app-1" } })
    await waitFor(() =>
      expect(success).toHaveBeenCalledWith(APPROVED_TOAST_TEXT, {
        duration: 3000,
      }),
    )
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull())
    await waitFor(() =>
      expect(list.mock.calls.length).toBeGreaterThan(callsBefore),
    )
  })

  it("退回：理由沒填時確認鈕停用；送出去除前後空白的原因並 Toast", async () => {
    const user = userEvent.setup()
    const success = vi.spyOn(toast, "success")
    mockList()
    const reject = vi
      .spyOn(IdentityService, "rejectOrganizerApplication")
      .mockResolvedValue({
        data: { ...PENDING, status: "rejected", reject_reason: "名稱不完整" },
      } as RejectResult)
    signInAs({ account: ADMIN })
    renderApp("/admin/applications")

    const table = await screen.findByRole("table", { name: "主辦方申請" })
    await user.click(within(table).getByRole("button", { name: "退回申請" }))

    const dialog = await screen.findByRole("alertdialog", {
      name: "退回主辦方申請",
    })
    expect(dialog).toHaveAccessibleDescription(REJECT_DESCRIPTION_TEXT)
    const confirm = within(dialog).getByRole("button", { name: "退回申請" })
    expect(confirm).toBeDisabled()
    await user.type(within(dialog).getByLabelText("退回原因"), "  名稱不完整 ")
    await user.click(confirm)

    expect(reject).toHaveBeenCalledWith({
      path: { application_id: "app-1" },
      body: { reason: "名稱不完整" },
    })
    await waitFor(() =>
      expect(success).toHaveBeenCalledWith(REJECTED_TOAST_TEXT, {
        duration: 3000,
      }),
    )
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull())
  })

  it("重複審核（409）：錯誤顯示在對話框，對話框不關；關閉後重新整理列表", async () => {
    const user = userEvent.setup()
    const list = mockList()
    vi.spyOn(IdentityService, "approveOrganizerApplication").mockRejectedValue(
      httpError(409, {
        detail: {
          code: "APPLICATION_NOT_PENDING",
          message: "這筆申請已經審核過了。",
        },
      }),
    )
    signInAs({ account: ADMIN })
    renderApp("/admin/applications")

    const table = await screen.findByRole("table", { name: "主辦方申請" })
    await user.click(within(table).getByRole("button", { name: "核准" }))
    const dialog = await screen.findByRole("alertdialog")
    await user.click(within(dialog).getByRole("button", { name: "核准" }))

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "這筆申請已經審核過了。",
    )
    expect(screen.getByRole("alertdialog")).toBeInTheDocument()

    const callsBefore = list.mock.calls.length
    await user.click(within(dialog).getByRole("button", { name: "取消" }))
    await waitFor(() =>
      expect(list.mock.calls.length).toBeGreaterThan(callsBefore),
    )
  })

  it("列表載入失敗：顯示錯誤與「重新載入」", async () => {
    const user = userEvent.setup()
    const list = vi
      .spyOn(IdentityService, "listOrganizerApplications")
      .mockRejectedValueOnce(httpError(500, {}))
      .mockResolvedValue(page([PENDING]))
    signInAs({ account: ADMIN })
    renderApp("/admin/applications")

    expect(await screen.findByText("伺服器發生錯誤（500）")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "重新載入" }))

    expect(
      await screen.findByRole("table", { name: "主辦方申請" }),
    ).toBeInTheDocument()
    expect(list).toHaveBeenCalledTimes(2)
  })
})
