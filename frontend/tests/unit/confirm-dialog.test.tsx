import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { ConfirmDialog } from "@/components/common/ConfirmDialog"
import { Button } from "@/components/ui/button"
import { httpError } from "./helpers"

function renderDialog(
  props: Partial<React.ComponentProps<typeof ConfirmDialog>> = {},
) {
  const onConfirm = vi.fn().mockResolvedValue(undefined)
  render(
    <ConfirmDialog
      title="退回主辦方申請"
      description="申請人會看到退回原因，並可以修改後重新申請。"
      confirmLabel="退回申請"
      onConfirm={onConfirm}
      trigger={<Button>開啟</Button>}
      {...props}
    />,
  )
  return { onConfirm: (props.onConfirm as typeof onConfirm) ?? onConfirm }
}

describe("ConfirmDialog", () => {
  it("標題寫動作、內文寫後果、確認鈕重複動作名，另有「取消」", async () => {
    const user = userEvent.setup()
    renderDialog()

    await user.click(screen.getByRole("button", { name: "開啟" }))

    const dialog = await screen.findByRole("alertdialog")
    expect(dialog).toHaveAccessibleName("退回主辦方申請")
    expect(dialog).toHaveAccessibleDescription(
      "申請人會看到退回原因，並可以修改後重新申請。",
    )
    expect(screen.getByRole("button", { name: "退回申請" })).toBeEnabled()
    expect(screen.getByRole("button", { name: "取消" })).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "確定" })).toBeNull()
  })

  it("確認成功：以 undefined 呼叫 onConfirm 後關閉", async () => {
    const user = userEvent.setup()
    const { onConfirm } = renderDialog()

    await user.click(screen.getByRole("button", { name: "開啟" }))
    await user.click(await screen.findByRole("button", { name: "退回申請" }))

    expect(onConfirm).toHaveBeenCalledWith(undefined)
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull())
  })

  it("必填理由欄：沒填或只有空白時確認鈕停用，送出時帶去除前後空白的理由", async () => {
    const user = userEvent.setup()
    const { onConfirm } = renderDialog({
      destructive: true,
      reason: { label: "退回原因", maxLength: 200 },
    })

    await user.click(screen.getByRole("button", { name: "開啟" }))
    const confirm = await screen.findByRole("button", { name: "退回申請" })
    const field = screen.getByLabelText("退回原因")
    expect(field).toHaveAttribute("maxlength", "200")
    expect(confirm).toBeDisabled()

    await user.type(field, "   ")
    expect(confirm).toBeDisabled()

    await user.type(field, " 名稱不完整 ")
    expect(confirm).toBeEnabled()
    expect(screen.getByText("10／200")).toBeInTheDocument()
    await user.click(confirm)

    expect(onConfirm).toHaveBeenCalledWith("名稱不完整")
  })

  it("送出中：確認鈕顯示 spinner 並停用，取消也停用", async () => {
    const user = userEvent.setup()
    let resolve: () => void = () => {}
    const onConfirm = vi.fn(
      () =>
        new Promise<void>((done) => {
          resolve = done
        }),
    )
    renderDialog({ onConfirm })

    await user.click(screen.getByRole("button", { name: "開啟" }))
    const confirm = await screen.findByRole("button", { name: "退回申請" })
    await user.click(confirm)

    expect(confirm).toBeDisabled()
    expect(confirm.querySelector("svg.animate-spin")).not.toBeNull()
    expect(screen.getByRole("button", { name: "取消" })).toBeDisabled()

    resolve()
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull())
  })

  it("送出失敗：對話框不關，顯示伺服器的 detail.message，理由保留", async () => {
    const user = userEvent.setup()
    const onConfirm = vi.fn().mockRejectedValue(
      httpError(409, {
        detail: {
          code: "APPLICATION_NOT_PENDING",
          message: "這筆申請已經審核過了。",
        },
      }),
    )
    renderDialog({ onConfirm, reason: { label: "退回原因", maxLength: 200 } })

    await user.click(screen.getByRole("button", { name: "開啟" }))
    await user.type(await screen.findByLabelText("退回原因"), "不符資格")
    await user.click(screen.getByRole("button", { name: "退回申請" }))

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "這筆申請已經審核過了。",
    )
    expect(screen.getByRole("alertdialog")).toBeInTheDocument()
    expect(screen.getByLabelText("退回原因")).toHaveValue("不符資格")
    expect(screen.getByRole("button", { name: "退回申請" })).toBeEnabled()
  })

  it("取消後重新開啟：理由與錯誤都清空", async () => {
    const user = userEvent.setup()
    const onOpenChange = vi.fn()
    renderDialog({
      onOpenChange,
      reason: { label: "退回原因", maxLength: 200 },
    })

    await user.click(screen.getByRole("button", { name: "開啟" }))
    await user.type(await screen.findByLabelText("退回原因"), "草稿")
    await user.click(screen.getByRole("button", { name: "取消" }))
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull())
    expect(onOpenChange).toHaveBeenLastCalledWith(false)

    await user.click(screen.getByRole("button", { name: "開啟" }))
    expect(await screen.findByLabelText("退回原因")).toHaveValue("")
  })
})
