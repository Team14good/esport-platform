import { act, render, screen, within } from "@testing-library/react"
import { AxiosError } from "axios"
import { toast } from "sonner"
import { afterEach, describe, expect, it, vi } from "vitest"

import { ThemeProvider } from "@/components/theme-provider"
import { Toaster } from "@/components/ui/sonner"
import {
  notifyError,
  notifySuccess,
  SUCCESS_TOAST_DURATION,
} from "@/lib/feedback"
import { httpError } from "./helpers"

afterEach(() => {
  act(() => {
    toast.dismiss()
  })
})

describe("Toast 回饋", () => {
  it("非表單業務錯誤：錯誤 Toast 顯示 message，不會自動消失", () => {
    const spy = vi.spyOn(toast, "error")

    notifyError(
      httpError(409, {
        detail: { code: "REGISTRATION_CLOSED", message: "報名已截止。" },
      }),
    )

    expect(spy).toHaveBeenCalledWith("報名已截止。", {
      id: "報名已截止。",
      duration: Infinity,
      closeButton: true,
    })
  })

  it("連不到伺服器：錯誤 Toast 顯示「無法連線到伺服器」", () => {
    const spy = vi.spyOn(toast, "error")

    notifyError(new AxiosError("Network Error", "ERR_NETWORK"))

    expect(spy).toHaveBeenCalledWith("無法連線到伺服器", {
      id: "無法連線到伺服器",
      duration: Infinity,
      closeButton: true,
    })
  })

  it("成功回饋：一句話的成功 Toast，3 秒後消失", () => {
    const spy = vi.spyOn(toast, "success")

    notifySuccess("已複製")

    expect(SUCCESS_TOAST_DURATION).toBe(3000)
    expect(spy).toHaveBeenCalledWith("已複製", { duration: 3000 })
  })

  it("錯誤 Toast 自帶關閉鈕、3 秒後仍在、相同錯誤只留一則；成功 Toast 3 秒後消失", async () => {
    vi.useFakeTimers()
    try {
      render(
        <ThemeProvider>
          <Toaster />
        </ThemeProvider>,
      )

      const error = httpError(400, {
        detail: { code: "X", message: "錯誤訊息" },
      })
      act(() => {
        notifyError(error)
        notifyError(error)
        notifySuccess("已儲存")
      })
      await act(async () => {
        await vi.advanceTimersByTimeAsync(100)
      })
      expect(screen.getAllByText("錯誤訊息")).toHaveLength(1)
      expect(screen.getByText("已儲存")).toBeInTheDocument()
      const errorToast = screen
        .getByText("錯誤訊息")
        .closest("[data-sonner-toast]") as HTMLElement
      expect(errorToast).not.toBeNull()
      expect(
        within(errorToast).getByRole("button", { name: "關閉" }),
      ).toBeInTheDocument()

      await act(async () => {
        await vi.advanceTimersByTimeAsync(SUCCESS_TOAST_DURATION + 1000)
      })
      expect(screen.getByText("錯誤訊息")).toBeInTheDocument()
      expect(screen.queryByText("已儲存")).toBeNull()
    } finally {
      vi.useRealTimers()
    }
  })
})
