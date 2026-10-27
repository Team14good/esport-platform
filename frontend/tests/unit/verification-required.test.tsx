import {
  createMemoryHistory,
  createRootRoute,
  createRouter,
} from "@tanstack/react-router"
import { screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { toast } from "sonner"
import { describe, expect, it, vi } from "vitest"

import { IdentityService } from "@/client"
import { Button } from "@/components/ui/button"
import { RESEND_SUCCESS_TEXT } from "@/features/identity/ResendVerificationForm"
import { VerificationRequired } from "@/features/identity/VerificationRequired"
import { ACCOUNT, signInAs } from "./auth-fixtures"
import { renderRouter } from "./render-router"

type ResendResult = Awaited<
  ReturnType<typeof IdentityService.resendVerificationEmail>
>

function renderGuardedAction() {
  const rootRoute = createRootRoute({
    component: () => (
      <VerificationRequired action="申請成為主辦方">
        <Button>申請成為主辦方</Button>
      </VerificationRequired>
    ),
  })
  renderRouter(
    createRouter({
      routeTree: rootRoute,
      history: createMemoryHistory({ initialEntries: ["/"] }),
    }),
  )
}

describe("Email 未驗證時的動作", () => {
  it("未驗證：動作停用，說明「完成 Email 驗證後才能…」並可重寄驗證信", async () => {
    const user = userEvent.setup()
    const success = vi.spyOn(toast, "success")
    signInAs({ account: { ...ACCOUNT, email_verified: false } })
    const resend = vi
      .spyOn(IdentityService, "resendVerificationEmail")
      .mockResolvedValue({ data: undefined } as ResendResult)
    renderGuardedAction()

    expect(
      await screen.findByText("完成 Email 驗證後才能申請成為主辦方。"),
    ).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: "申請成為主辦方" }),
    ).toBeDisabled()

    await user.click(screen.getByRole("button", { name: "重寄驗證信" }))

    expect(resend).toHaveBeenCalledWith({
      body: { email: "an@example.com", redirect: null },
    })
    await waitFor(() =>
      expect(success).toHaveBeenCalledWith(RESEND_SUCCESS_TEXT, {
        duration: 3000,
      }),
    )
  })

  it("已登入、帳號資料還在載入：先停用動作，不顯示說明", async () => {
    signInAs()
    vi.spyOn(IdentityService, "readCurrentAccount").mockReturnValue(
      new Promise<never>(() => {}),
    )
    renderGuardedAction()

    expect(
      await screen.findByRole("button", { name: "申請成為主辦方" }),
    ).toBeDisabled()
    expect(screen.queryByText(/完成 Email 驗證後才能/)).toBeNull()
  })

  it("未登入：動作原樣可用（交給 401 導向 S6 的流程）", async () => {
    renderGuardedAction()

    expect(
      await screen.findByRole("button", { name: "申請成為主辦方" }),
    ).toBeEnabled()
  })

  it("已驗證：動作可用，不顯示說明", async () => {
    signInAs()
    renderGuardedAction()

    // 帳號資料載入完成前先停用；載入後換成可用的按鈕
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "申請成為主辦方" }),
      ).toBeEnabled(),
    )
    expect(screen.queryByText(/完成 Email 驗證後才能/)).toBeNull()
  })
})
