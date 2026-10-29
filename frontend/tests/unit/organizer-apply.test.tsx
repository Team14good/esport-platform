import { screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { toast } from "sonner"
import { describe, expect, it, vi } from "vitest"

import { IdentityService, type OrganizerApplicationRead } from "@/client"
import {
  ALREADY_ORGANIZER_TEXT,
  APPLICATION_SUBMITTED_TEXT,
  PENDING_SUMMARY_TEXT,
} from "@/features/identity/OrganizerApplyPage"
import { GO_TO_VERIFY_TEXT } from "@/features/identity/VerificationRequired"
import { formatDateTime } from "@/lib/datetime"
import { ACCOUNT, renderApp, signInAs } from "./auth-fixtures"
import { httpError } from "./helpers"

vi.mock("@tanstack/react-router-devtools", () => ({
  TanStackRouterDevtools: () => null,
}))
vi.mock("@tanstack/react-query-devtools", () => ({
  ReactQueryDevtools: () => null,
}))

type ListSchoolsResult = Awaited<ReturnType<typeof IdentityService.listSchools>>
type ReadApplicationResult = Awaited<
  ReturnType<typeof IdentityService.readCurrentOrganizerApplication>
>
type SubmitResult = Awaited<
  ReturnType<typeof IdentityService.submitOrganizerApplication>
>

const SCHOOLS = [
  { id: "school-ntu", name: "國立臺灣大學" },
  { id: "school-nthu", name: "國立清華大學" },
]

const PENDING: OrganizerApplicationRead = {
  id: "app-1",
  club_name: "臺大電競社",
  school_id: "school-ntu",
  school_name: "國立臺灣大學",
  status: "pending",
  reject_reason: null,
  // 台北時間 2026/10/29 14:05
  created_at: "2026-10-29T06:05:00Z",
}

function mockSchools() {
  vi.spyOn(IdentityService, "listSchools").mockResolvedValue({
    data: SCHOOLS,
  } as ListSchoolsResult)
}

// 後端回 null（沒有申請）時，產生的 client 給的 data 是 {}（`data ?? {}`），這裡照實模擬
const NO_APPLICATION = { data: {} } as unknown as ReadApplicationResult

function mockApplication(application: OrganizerApplicationRead | null) {
  return vi
    .spyOn(IdentityService, "readCurrentOrganizerApplication")
    .mockResolvedValue(
      application
        ? ({ data: application } as ReadApplicationResult)
        : NO_APPLICATION,
    )
}

describe("formatDateTime", () => {
  it("以台北時間顯示 yyyy/MM/dd HH:mm", () => {
    expect(formatDateTime("2026-10-29T06:05:00Z")).toBe("2026/10/29 14:05")
    expect(formatDateTime("2026-10-28T16:00:00Z")).toBe("2026/10/29 00:00")
  })
})

describe("S15 主辦方申請", () => {
  it("未登入開啟：導向 S6 並帶 redirect", async () => {
    const router = renderApp("/organizer/apply")

    await screen.findByRole("heading", { name: "登入" })
    expect(router.state.location.pathname).toBe("/login")
    expect(router.state.location.search).toEqual({
      redirect: "/organizer/apply",
    })
  })

  it("沒有申請（client 給 {}）：顯示表單，學校預設帶入帳號的學校", async () => {
    mockSchools()
    mockApplication(null)
    signInAs({ account: { ...ACCOUNT, school_id: "school-ntu" } })
    renderApp("/organizer/apply")

    expect(
      await screen.findByRole("heading", { name: "申請成為主辦方" }),
    ).toBeInTheDocument()
    expect(
      screen.getByText("平台管理員會依社團名稱與學校審核。"),
    ).toBeInTheDocument()
    expect(screen.getByLabelText("社團名稱")).toHaveValue("")
    expect(await screen.findByText("國立臺灣大學")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "送出申請" })).toBeEnabled()
  })

  it("送出申請：成功 Toast，以回傳值換成唯讀摘要（待審核），不再重抓", async () => {
    const user = userEvent.setup()
    const success = vi.spyOn(toast, "success")
    mockSchools()
    const read = mockApplication(null)
    signInAs()
    const submit = vi
      .spyOn(IdentityService, "submitOrganizerApplication")
      .mockResolvedValue({
        data: {
          ...PENDING,
          school_id: "school-nthu",
          school_name: "國立清華大學",
        },
      } as SubmitResult)
    renderApp("/organizer/apply")

    await user.type(await screen.findByLabelText("社團名稱"), "  臺大電競社 ")
    await user.click(screen.getByLabelText("學校"))
    await user.type(
      await screen.findByRole("combobox", { name: "搜尋學校" }),
      "清華",
    )
    await user.click(screen.getByRole("option", { name: "國立清華大學" }))
    await user.click(screen.getByRole("button", { name: "送出申請" }))

    expect(
      await screen.findByRole("heading", { name: "主辦方申請" }),
    ).toBeInTheDocument()
    expect(submit).toHaveBeenCalledWith({
      body: { club_name: "臺大電競社", school_id: "school-nthu" },
    })
    await waitFor(() =>
      expect(success).toHaveBeenCalledWith(APPLICATION_SUBMITTED_TEXT, {
        duration: 3000,
      }),
    )
    expect(screen.getByText("待審核")).toHaveAttribute("data-tone", "appeal")
    expect(screen.getByText("國立清華大學")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "送出申請" })).toBeNull()
    expect(read).toHaveBeenCalledTimes(1)
  })

  it("已有申請時開啟（重新整理）：直接顯示唯讀摘要與「待審核」徽章", async () => {
    mockSchools()
    mockApplication(PENDING)
    signInAs()
    renderApp("/organizer/apply")

    const heading = await screen.findByRole("heading", { name: "主辦方申請" })
    const card = heading.closest("[data-slot=card]") as HTMLElement
    const badge = within(card).getByText("待審核")
    expect(badge).toHaveAttribute("data-slot", "status-badge")
    expect(badge).toHaveAttribute("data-tone", "appeal")
    const terms = within(card)
      .getAllByRole("term")
      .map((term) => term.textContent)
    expect(terms).toEqual(["社團名稱", "學校", "送出時間"])
    expect(within(card).getByText("臺大電競社")).toBeInTheDocument()
    expect(within(card).getByText("國立臺灣大學")).toBeInTheDocument()
    expect(within(card).getByText("2026/10/29 14:05")).toHaveAttribute(
      "datetime",
      "2026-10-29T06:05:00Z",
    )
    expect(within(card).getByText(PENDING_SUMMARY_TEXT)).toBeInTheDocument()
    expect(screen.queryByLabelText("社團名稱")).toBeNull()
  })

  it("重複送出（409 APPLICATION_PENDING）：訊息顯示在表單頂部 Alert", async () => {
    const user = userEvent.setup()
    mockSchools()
    mockApplication(null)
    signInAs({ account: { ...ACCOUNT, school_id: "school-ntu" } })
    vi.spyOn(IdentityService, "submitOrganizerApplication").mockRejectedValue(
      httpError(409, {
        detail: {
          code: "APPLICATION_PENDING",
          message: "你已有一筆待審核的主辦方申請。",
        },
      }),
    )
    renderApp("/organizer/apply")

    await user.type(await screen.findByLabelText("社團名稱"), "電競社")
    await screen.findByText("國立臺灣大學")
    await user.click(screen.getByRole("button", { name: "送出申請" }))

    const alert = await screen.findByRole("alert")
    expect(alert).toHaveTextContent("你已有一筆待審核的主辦方申請。")
    expect(
      alert.compareDocumentPosition(screen.getByLabelText("社團名稱")) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy()
  })

  it.each([
    ["社團名稱空白", "   ", "請輸入社團名稱"],
    ["社團名稱超過 50 字", "社".repeat(51), "社團名稱最多 50 個字"],
  ])("%s：在欄位下方提示，不呼叫 API", async (_, value, message) => {
    const user = userEvent.setup()
    mockSchools()
    mockApplication(null)
    signInAs({ account: { ...ACCOUNT, school_id: "school-ntu" } })
    const submit = vi.spyOn(IdentityService, "submitOrganizerApplication")
    renderApp("/organizer/apply")

    await user.type(await screen.findByLabelText("社團名稱"), value)
    await user.click(screen.getByRole("button", { name: "送出申請" }))

    const error = await screen.findByText(message)
    expect(error.closest("[data-slot=form-item]")).toContainElement(
      screen.getByLabelText("社團名稱"),
    )
    expect(submit).not.toHaveBeenCalled()
  })

  it("社團名稱正好 50 字可以送出", async () => {
    const user = userEvent.setup()
    mockSchools()
    mockApplication(null)
    signInAs({ account: { ...ACCOUNT, school_id: "school-ntu" } })
    const submit = vi
      .spyOn(IdentityService, "submitOrganizerApplication")
      .mockResolvedValue({ data: PENDING } as SubmitResult)
    renderApp("/organizer/apply")

    await user.type(await screen.findByLabelText("社團名稱"), "社".repeat(50))
    await screen.findByText("國立臺灣大學")
    await user.click(screen.getByRole("button", { name: "送出申請" }))

    await waitFor(() =>
      expect(submit).toHaveBeenCalledWith({
        body: { club_name: "社".repeat(50), school_id: "school-ntu" },
      }),
    )
  })

  it("沒選學校：在學校欄位下方提示，不呼叫 API", async () => {
    const user = userEvent.setup()
    mockSchools()
    mockApplication(null)
    signInAs()
    const submit = vi.spyOn(IdentityService, "submitOrganizerApplication")
    renderApp("/organizer/apply")

    await user.type(await screen.findByLabelText("社團名稱"), "電競社")
    await user.click(screen.getByRole("button", { name: "送出申請" }))

    const error = await screen.findByText("請選擇學校")
    expect(error.closest("[data-slot=form-item]")).toContainElement(
      screen.getByLabelText("學校"),
    )
    expect(submit).not.toHaveBeenCalled()
  })

  it("學校不存在（422 SCHOOL_NOT_FOUND）：錯誤顯示在學校欄位下方", async () => {
    const user = userEvent.setup()
    mockSchools()
    mockApplication(null)
    signInAs({ account: { ...ACCOUNT, school_id: "school-ntu" } })
    vi.spyOn(IdentityService, "submitOrganizerApplication").mockRejectedValue(
      httpError(422, {
        detail: [
          {
            type: "SCHOOL_NOT_FOUND",
            loc: ["body", "school_id"],
            msg: "找不到這間學校",
          },
        ],
      }),
    )
    renderApp("/organizer/apply")

    await user.type(await screen.findByLabelText("社團名稱"), "電競社")
    await screen.findByText("國立臺灣大學")
    await user.click(screen.getByRole("button", { name: "送出申請" }))

    const message = await screen.findByText("找不到這間學校")
    expect(message.closest("[data-slot=form-item]")).toContainElement(
      screen.getByLabelText("學校"),
    )
    expect(screen.queryByRole("alert")).toBeNull()
  })

  it("未驗證 Email：表單整個停用，說明並連到 S7（帶 redirect 回 S15），沒有重寄按鈕", async () => {
    mockSchools()
    mockApplication(null)
    signInAs({ account: { ...ACCOUNT, email_verified: false } })
    renderApp("/organizer/apply")

    expect(
      await screen.findByText("完成 Email 驗證後才能申請成為主辦方。"),
    ).toBeInTheDocument()
    expect(screen.getByLabelText("社團名稱")).toBeDisabled()
    expect(screen.getByLabelText("學校")).toBeDisabled()
    expect(screen.getByRole("button", { name: "送出申請" })).toBeDisabled()
    expect(
      screen.getByRole("link", { name: GO_TO_VERIFY_TEXT }),
    ).toHaveAttribute("href", "/verify-email?redirect=%2Forganizer%2Fapply")
    expect(screen.queryByRole("button", { name: "重寄驗證信" })).toBeNull()
  })

  it("主辦方且沒有任何申請：只顯示「你已經是主辦方。」", async () => {
    mockSchools()
    mockApplication(null)
    signInAs({ account: { ...ACCOUNT, is_organizer: true } })
    renderApp("/organizer/apply")

    expect(await screen.findByText(ALREADY_ORGANIZER_TEXT)).toBeInTheDocument()
    expect(screen.queryByLabelText("社團名稱")).toBeNull()
    expect(screen.queryByRole("button", { name: "送出申請" })).toBeNull()
  })

  it("查詢失敗：顯示錯誤與「重新載入」，重新載入後顯示表單", async () => {
    const user = userEvent.setup()
    mockSchools()
    signInAs()
    const read = vi
      .spyOn(IdentityService, "readCurrentOrganizerApplication")
      .mockRejectedValueOnce(httpError(500, {}))
      .mockResolvedValue(NO_APPLICATION)
    renderApp("/organizer/apply")

    expect(await screen.findByText("伺服器發生錯誤（500）")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "重新載入" }))

    expect(
      await screen.findByRole("heading", { name: "申請成為主辦方" }),
    ).toBeInTheDocument()
    expect(read).toHaveBeenCalledTimes(2)
  })
})
