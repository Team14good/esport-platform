import { act, fireEvent, render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { ComponentProps } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"

import {
  CheckInPanel,
  type CheckInReason,
} from "@/features/competition/CheckInPanel"
import { UNEXPECTED_ERROR_MESSAGE } from "@/lib/api-error"
import { httpError } from "./helpers"

type PanelProps = ComponentProps<typeof CheckInPanel>

const KRAKEN = { id: "team-a", name: "成大 Kraken", checkedInAt: null }
const EMBER = { id: "team-b", name: "北科 Ember", checkedInAt: null }
// 台北 2025/10/18（六）19:00
const OPENS_AT = "2025-10-18T11:00:00Z"
const COUNTDOWN = <p>報到開放倒數 02:00:00</p>

function panel(props: Partial<PanelProps> = {}) {
  return (
    <CheckInPanel
      teams={{ a: KRAKEN, b: EMBER }}
      ownSide={null}
      isScheduled
      teamsPending={false}
      reason={null}
      opensAt={OPENS_AT}
      onCheckIn={vi.fn().mockResolvedValue(undefined)}
      {...props}
    />
  )
}

function renderPanel(props: Partial<PanelProps> = {}) {
  return render(panel(props))
}

/** 某一隊那一欄（清單項目）。 */
function teamColumn(name: string) {
  const column = screen
    .getAllByRole("listitem")
    .find((item) => within(item).queryByText(name))
  if (!column) throw new Error(`找不到 ${name} 那一欄`)
  return column
}

/** 可以從外部決定何時完成的 Promise，用來停在「送出中」。 */
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

afterEach(() => {
  vi.useRealTimers()
})

describe("Check-in panel", () => {
  it("觀眾：兩隊各一欄「未報到」，沒有按鈕", () => {
    renderPanel()

    expect(screen.getByRole("heading", { name: "報到" })).toBeInTheDocument()
    expect(within(teamColumn("成大 Kraken")).getByText("未報到")).toBeVisible()
    expect(within(teamColumn("北科 Ember")).getByText("未報到")).toBeVisible()
    expect(screen.queryByRole("button")).toBeNull()
  })

  it("隊長、太早：本隊那欄按鈕停用、寫可報到時間，下方是倒數；對手那欄沒有按鈕", () => {
    vi.useFakeTimers({ toFake: ["Date"] })
    vi.setSystemTime(new Date("2025-10-18T09:00:00Z"))
    renderPanel({ ownSide: "a", reason: "too_early", countdown: COUNTDOWN })

    const own = within(teamColumn("成大 Kraken"))
    const button = own.getByRole("button", { name: "報到" })
    expect(button).toBeDisabled()
    expect(button).toHaveAccessibleDescription("10/18（六）19:00 起可報到")
    expect(own.getByText("報到開放倒數 02:00:00")).toBeInTheDocument()
    expect(within(teamColumn("北科 Ember")).queryByRole("button")).toBeNull()
  })

  it("隊長、可報到：按鈕在本隊（b）那欄且可按，沒有停用說明", async () => {
    const user = userEvent.setup()
    const onCheckIn = vi.fn().mockResolvedValue(undefined)
    renderPanel({ ownSide: "b", onCheckIn })

    expect(within(teamColumn("成大 Kraken")).queryByRole("button")).toBeNull()
    const button = within(teamColumn("北科 Ember")).getByRole("button", {
      name: "報到",
    })
    expect(button).toBeEnabled()
    expect(screen.queryByText(/起可報到|已截止|對手確定後/)).toBeNull()

    await user.click(button)
    expect(onCheckIn).toHaveBeenCalledTimes(1)
  })

  it("送出中：按鈕停用並顯示載入，連按只呼叫一次；完成後恢復", async () => {
    const user = userEvent.setup()
    const request = deferred<undefined>()
    const onCheckIn = vi.fn().mockReturnValue(request.promise)
    renderPanel({ ownSide: "a", onCheckIn })
    const button = screen.getByRole("button", { name: "報到" })

    await user.click(button)
    await user.click(button)

    expect(onCheckIn).toHaveBeenCalledTimes(1)
    expect(button).toBeDisabled()
    expect(button).toHaveAttribute("aria-busy", "true")

    request.resolve(undefined)
    await vi.waitFor(() => expect(button).toBeEnabled())
    expect(button).toHaveAttribute("aria-busy", "false")
    expect(screen.queryByRole("alert")).toBeNull()
  })

  it("報到失敗（callback 拋錯）：面板內顯示伺服器訊息，按鈕恢復", async () => {
    const user = userEvent.setup()
    const onCheckIn = vi.fn().mockRejectedValue(
      httpError(409, {
        detail: { code: "CHECK_IN_CLOSED", message: "報到時間已過。" },
      }),
    )
    renderPanel({ ownSide: "a", onCheckIn })

    await user.click(screen.getByRole("button", { name: "報到" }))

    expect(await screen.findByRole("alert")).toHaveTextContent("報到時間已過。")
    expect(screen.getByRole("button", { name: "報到" })).toBeEnabled()
  })

  it("報到失敗（callback 回傳錯誤訊息）：顯示該訊息；再按一次時先清掉", async () => {
    const user = userEvent.setup()
    const retry = deferred<undefined>()
    const onCheckIn = vi
      .fn()
      .mockResolvedValueOnce("本隊隊長才能報到。")
      .mockReturnValueOnce(retry.promise)
    renderPanel({ ownSide: "a", onCheckIn })
    const button = screen.getByRole("button", { name: "報到" })

    await user.click(button)
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "本隊隊長才能報到。",
    )
    expect(button).toBeEnabled()

    await user.click(button)
    expect(screen.queryByRole("alert")).toBeNull()
    retry.resolve(undefined)
    await vi.waitFor(() => expect(button).toBeEnabled())
  })

  it("同一個 tick 內連按兩次：只呼叫一次", () => {
    const request = deferred<undefined>()
    const onCheckIn = vi.fn().mockReturnValue(request.promise)
    renderPanel({ ownSide: "a", onCheckIn })
    const button = screen.getByRole("button", { name: "報到" })

    // 同一個 act 內 React 不會在兩次點擊之間重新 render，按鈕還沒停用；只能靠 ref 擋住
    act(() => {
      fireEvent.click(button)
      fireEvent.click(button)
    })

    expect(onCheckIn).toHaveBeenCalledTimes(1)
    request.resolve(undefined)
  })

  it("報到失敗（callback 拋出非 HTTP 錯誤）：顯示泛用錯誤訊息，按鈕恢復", async () => {
    const user = userEvent.setup()
    const onCheckIn = vi.fn().mockRejectedValue(new Error("boom"))
    renderPanel({ ownSide: "a", onCheckIn })

    await user.click(screen.getByRole("button", { name: "報到" }))

    expect(await screen.findByRole("alert")).toHaveTextContent(
      UNEXPECTED_ERROR_MESSAGE,
    )
    expect(screen.getByRole("button", { name: "報到" })).toBeEnabled()
  })

  it("callback 回傳空字串：不顯示錯誤", async () => {
    const user = userEvent.setup()
    const onCheckIn = vi.fn().mockResolvedValue("")
    renderPanel({ ownSide: "a", onCheckIn })
    const button = screen.getByRole("button", { name: "報到" })

    await user.click(button)

    await vi.waitFor(() => expect(button).toBeEnabled())
    expect(onCheckIn).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole("alert")).toBeNull()
  })

  it("錯誤顯示後重新取得的資料改變了狀態：舊錯誤消失", async () => {
    const user = userEvent.setup()
    const onCheckIn = vi.fn().mockResolvedValue("報到時間已過。")
    const { rerender } = renderPanel({ ownSide: "a", onCheckIn })

    await user.click(screen.getByRole("button", { name: "報到" }))
    expect(await screen.findByRole("alert")).toHaveTextContent("報到時間已過。")

    rerender(panel({ ownSide: "a", onCheckIn, reason: "closed" }))
    expect(screen.queryByRole("alert")).toBeNull()
    expect(screen.getByText("已截止")).toBeInTheDocument()
  })

  it("已報到：本隊那欄「已報到 19:32」，沒有按鈕", () => {
    renderPanel({
      teams: {
        a: { ...KRAKEN, checkedInAt: "2025-10-18T11:32:00Z" },
        b: EMBER,
      },
      ownSide: "a",
      reason: "already_checked_in",
    })

    expect(
      within(teamColumn("成大 Kraken")).getByText("已報到 19:32"),
    ).toBeInTheDocument()
    expect(within(teamColumn("北科 Ember")).getByText("未報到")).toBeVisible()
    expect(screen.queryByRole("button")).toBeNull()
  })

  it("本隊報到時間已回來、reason 還沒更新：視為已報到，沒有按鈕", () => {
    renderPanel({
      teams: {
        a: { ...KRAKEN, checkedInAt: "2025-10-18T11:32:00Z" },
        b: EMBER,
      },
      ownSide: "a",
      reason: null,
    })

    expect(
      within(teamColumn("成大 Kraken")).getByText("已報到 19:32"),
    ).toBeInTheDocument()
    expect(screen.queryByRole("button")).toBeNull()
  })

  it("兩隊未確定（隊長）：面板停用，按鈕停用並以「對手確定後才能報到」說明", () => {
    renderPanel({ ownSide: "a", teamsPending: true, reason: "teams_pending" })

    const button = screen.getByRole("button", { name: "報到" })
    expect(button).toBeDisabled()
    expect(button).toHaveAccessibleDescription("對手確定後才能報到")
    expect(screen.getAllByText("對手確定後才能報到")).toHaveLength(1)
  })

  it("兩隊未確定（觀眾）：未定的一側寫「待定」，同樣看到面板停用與說明", () => {
    renderPanel({ teams: { a: KRAKEN, b: null }, teamsPending: true })

    const items = screen.getAllByRole("listitem")
    expect(items[0]).toHaveTextContent("成大 Kraken")
    expect(items[0]).toHaveTextContent("未報到")
    expect(items[1]).toHaveTextContent("待定")
    expect(items[1]).not.toHaveTextContent("報到")
    expect(screen.getByText("對手確定後才能報到")).toBeInTheDocument()
    expect(screen.queryByRole("button")).toBeNull()
  })

  it("清單不帶 aria-disabled（list 角色不支援，停用改由按鈕與說明文字表達）", () => {
    renderPanel({ ownSide: "a", teamsPending: true, reason: "teams_pending" })

    expect(screen.getByRole("list")).not.toHaveAttribute("aria-disabled")
  })

  it("已截止：按鈕停用，寫「已截止」", () => {
    renderPanel({ ownSide: "a", reason: "closed" })

    const button = screen.getByRole("button", { name: "報到" })
    expect(button).toBeDisabled()
    expect(button).toHaveAccessibleDescription("已截止")
  })

  it("不認得的原因代碼：按鈕停用，請使用者重新整理", () => {
    renderPanel({
      ownSide: "a",
      reason: "suspended" as unknown as CheckInReason,
    })

    const button = screen.getByRole("button", { name: "報到" })
    expect(button).toBeDisabled()
    expect(button).toHaveAccessibleDescription("目前無法報到，請重新整理頁面")
  })

  it.each(["not_checkable", "not_captain"] as const)(
    "後端的 %s 原因：按鈕停用，沿用預設說明",
    (reason) => {
      renderPanel({ ownSide: "a", reason })

      const button = screen.getByRole("button", { name: "報到" })
      expect(button).toBeDisabled()
      expect(button).toHaveAccessibleDescription("目前無法報到，請重新整理頁面")
    },
  )

  it("離開待開打：只留兩隊報到時間，沒有按鈕、說明與倒數", () => {
    renderPanel({
      teams: {
        a: { ...KRAKEN, checkedInAt: "2025-10-18T11:32:00Z" },
        b: { ...EMBER, checkedInAt: "2025-10-18T11:41:00Z" },
      },
      ownSide: "a",
      isScheduled: false,
      reason: "closed",
      countdown: COUNTDOWN,
    })

    expect(
      within(teamColumn("成大 Kraken")).getByText("已報到 19:32"),
    ).toBeInTheDocument()
    expect(
      within(teamColumn("北科 Ember")).getByText("已報到 19:41"),
    ).toBeInTheDocument()
    expect(screen.queryByRole("button")).toBeNull()
    expect(screen.queryByText("已截止")).toBeNull()
    expect(screen.queryByText("報到開放倒數 02:00:00")).toBeNull()
  })

  it("觀眾的倒數放在兩隊下方；離開待開打時一併收起", () => {
    const { rerender } = renderPanel({ countdown: COUNTDOWN })
    const countdown = screen.getByText("報到開放倒數 02:00:00")
    expect(
      screen.getAllByRole("listitem").some((item) => item.contains(countdown)),
    ).toBe(false)

    rerender(panel({ isScheduled: false, countdown: COUNTDOWN }))
    expect(screen.queryByText("報到開放倒數 02:00:00")).toBeNull()
  })

  it("手機版的結構：兩隊依序是兩個清單項目，按鈕在本隊那一項內", () => {
    // 375px 的上下兩列與滿版按鈕是 CSS 版面，jsdom 量不到；這裡只確認排版依賴的結構
    renderPanel({ ownSide: "b" })

    const items = screen.getAllByRole("listitem")
    expect(items).toHaveLength(2)
    expect(items[0]).toHaveTextContent("成大 Kraken")
    expect(items[1]).toHaveTextContent("北科 Ember")
    expect(
      within(items[1]).getByRole("button", { name: "報到" }),
    ).toBeInTheDocument()
  })
})
