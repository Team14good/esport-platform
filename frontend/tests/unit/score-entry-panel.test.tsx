import { act, fireEvent, render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import {
  type SavedGame,
  ScoreEntryPanel,
  type ScoreEntryPanelProps,
  type ScoreOutcome,
  type ScoreReason,
} from "@/features/competition/ScoreEntryPanel"

const A = "成大 Kraken"
const B = "北科 Ember"

function renderPanel(overrides: Partial<ScoreEntryPanelProps> = {}) {
  const props: ScoreEntryPanelProps = {
    teamA: A,
    teamB: B,
    scoreType: "rounds",
    bothCheckedIn: true,
    games: [],
    series: {
      winsA: 0,
      winsB: 0,
      winner: null,
      canSubmit: false,
      winsNeeded: 2,
    },
    submission: null,
    onRecord: vi.fn<ScoreEntryPanelProps["onRecord"]>(async () => null),
    onDelete: vi.fn<ScoreEntryPanelProps["onDelete"]>(async () => null),
    onSubmit: vi.fn<ScoreEntryPanelProps["onSubmit"]>(async () => null),
    ...overrides,
  }
  const { rerender } = render(<ScoreEntryPanel {...props} />)
  // 模擬呼叫端更新 props（例如重新取得局與系列結果）
  const update = (next: Partial<ScoreEntryPanelProps>) => {
    Object.assign(props, next)
    rerender(<ScoreEntryPanel {...props} />)
  }
  return Object.assign(props, { update })
}

function gameRow(gameNo: number) {
  return screen.getByRole("row", { name: new RegExp(`^第 ${gameNo} 局`) })
}

function scoreBox(gameNo: number, team: string) {
  return screen.getByRole("textbox", { name: `第 ${gameNo} 局 ${team} 分數` })
}

function deferred() {
  let resolve!: (value: ScoreReason | null) => void
  const promise: ScoreOutcome = new Promise((r) => {
    resolve = r
  })
  return { promise, resolve }
}

const DECIDED = {
  winsA: 2,
  winsB: 1,
  winner: "a" as const,
  canSubmit: true,
  winsNeeded: 2,
}

async function openSubmitDialog(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: "送出系列結果" }))
  return screen.findByRole("alertdialog", { name: "送出系列結果" })
}

const ROUNDS_3: SavedGame[] = [
  { winner: "a", scoreA: 13, scoreB: 11 },
  { winner: "b", scoreA: 9, scoreB: 13 },
  { winner: "a", scoreA: 13, scoreB: 10 },
]

describe("S24 Score entry panel：開始前", () => {
  it("兩隊未都報到：寫「等待雙方報到」，整個面板停用、沒有「可開始」", () => {
    renderPanel({ bothCheckedIn: false })

    expect(screen.getByText("等待雙方報到")).toBeInTheDocument()
    expect(screen.queryByText("可開始")).toBeNull()
    expect(scoreBox(1, A)).toBeDisabled()
    expect(scoreBox(1, B)).toBeDisabled()
    for (const button of screen.getAllByRole("button")) {
      expect(button).toBeDisabled()
    }
  })

  it("兩隊已報到、沒有局：標題旁「可開始」，第 1 局是輸入列", () => {
    renderPanel()

    expect(
      screen.getByRole("heading", { name: "比分登錄" }),
    ).toBeInTheDocument()
    expect(screen.getByText("可開始")).toBeInTheDocument()
    expect(screen.queryByText("等待雙方報到")).toBeNull()
    expect(scoreBox(1, A)).toBeEnabled()
    expect(
      within(gameRow(1)).getByRole("button", { name: "登錄" }),
    ).toBeDisabled()
    // 表頭是「局」＋兩隊隊名
    expect(screen.getByRole("columnheader", { name: "局" })).toBeInTheDocument()
    expect(screen.getByRole("columnheader", { name: A })).toBeInTheDocument()
    expect(screen.getByRole("columnheader", { name: B })).toBeInTheDocument()
  })

  it("已有任何一局：不顯示「可開始」", () => {
    renderPanel({
      games: ROUNDS_3.slice(0, 1),
      series: {
        winsA: 1,
        winsB: 0,
        winner: null,
        canSubmit: false,
        winsNeeded: 2,
      },
    })

    expect(screen.queryByText("可開始")).toBeNull()
  })
})

describe("S24 Score entry panel：登錄一局", () => {
  it('勝負型態：選 a 後按「登錄」→ onRecord(1, {winner: "a"})', async () => {
    const user = userEvent.setup()
    const props = renderPanel({ scoreType: "win_loss" })
    const record = within(gameRow(1)).getByRole("button", { name: "登錄" })
    expect(record).toBeDisabled()

    await user.click(screen.getByRole("button", { name: A }))

    expect(screen.getByRole("button", { name: A })).toHaveAttribute(
      "aria-pressed",
      "true",
    )
    expect(screen.getByRole("button", { name: B })).toHaveAttribute(
      "aria-pressed",
      "false",
    )
    await user.click(record)
    expect(props.onRecord).toHaveBeenCalledTimes(1)
    expect(props.onRecord).toHaveBeenCalledWith(1, { winner: "a" })
  })

  it("勝負型態已存的局：顯示勝方隊名＋「勝」", () => {
    renderPanel({
      scoreType: "win_loss",
      games: [{ winner: "b" }],
      series: {
        winsA: 0,
        winsB: 1,
        winner: null,
        canSubmit: false,
        winsNeeded: 2,
      },
    })

    expect(within(gameRow(1)).getByText(`${B} 勝`)).toBeInTheDocument()
    expect(within(gameRow(1)).getByText("已登錄")).toBeInTheDocument()
  })

  it("回合型態 12：12：「登錄」停用並寫「不能平手」，不呼叫 callback", async () => {
    const user = userEvent.setup()
    const props = renderPanel()

    await user.type(scoreBox(1, A), "12")
    const record = within(gameRow(1)).getByRole("button", { name: "登錄" })
    expect(record).toBeDisabled()
    expect(screen.queryByText("不能平手")).toBeNull()
    await user.type(scoreBox(1, B), "12")

    expect(record).toBeDisabled()
    expect(screen.getByText("不能平手")).toBeInTheDocument()
    await user.click(record)
    expect(props.onRecord).not.toHaveBeenCalled()
  })

  it("回合型態只收非負整數：負號、小數點與文字輸入不進去", async () => {
    const user = userEvent.setup()
    renderPanel()

    await user.type(scoreBox(1, A), "-1.5a")

    expect(scoreBox(1, A)).toHaveValue("15")
  })

  it("回合型態 13：11：按「新增一局」後登錄 → onRecord(2, {scoreA: 13, scoreB: 11})", async () => {
    const user = userEvent.setup()
    const props = renderPanel({
      games: ROUNDS_3.slice(0, 1),
      series: {
        winsA: 1,
        winsB: 0,
        winner: null,
        canSubmit: false,
        winsNeeded: 2,
      },
    })
    expect(screen.queryByRole("row", { name: /^第 2 局/ })).toBeNull()

    await user.click(screen.getByRole("button", { name: "新增一局" }))
    await user.type(scoreBox(2, A), "13")
    await user.type(scoreBox(2, B), "11")
    await user.click(within(gameRow(2)).getByRole("button", { name: "登錄" }))

    expect(props.onRecord).toHaveBeenCalledTimes(1)
    expect(props.onRecord).toHaveBeenCalledWith(2, { scoreA: 13, scoreB: 11 })
  })

  it("送出中：該列停用，再按一次「登錄」callback 只被呼叫一次", async () => {
    const user = userEvent.setup()
    const { promise, resolve } = deferred()
    const onRecord = vi.fn<ScoreEntryPanelProps["onRecord"]>(() => promise)
    renderPanel({ onRecord })
    await user.type(scoreBox(1, A), "13")
    await user.type(scoreBox(1, B), "11")
    const record = within(gameRow(1)).getByRole("button", { name: "登錄" })

    await user.click(record)
    await user.click(record)

    expect(onRecord).toHaveBeenCalledTimes(1)
    expect(record).toBeDisabled()
    expect(scoreBox(1, A)).toBeDisabled()
    expect(scoreBox(1, B)).toBeDisabled()

    resolve(null)
    await vi.waitFor(() => expect(scoreBox(1, A)).toBeEnabled())
  })
})

describe("S24 Score entry panel：修改與刪除", () => {
  const props3 = {
    games: ROUNDS_3,
    series: {
      winsA: 2,
      winsB: 1,
      winner: "a" as const,
      canSubmit: true,
      winsNeeded: 2,
    },
  }

  it("已存的列：等寬文字比分＋「已登錄」＋「修改」，沒有輸入框", () => {
    renderPanel(props3)

    const row = gameRow(2)
    expect(row).toHaveTextContent("9:13")
    expect(within(row).getByText("已登錄")).toBeInTheDocument()
    expect(within(row).getByRole("button", { name: "修改" })).toBeEnabled()
    expect(within(row).queryByRole("textbox")).toBeNull()
  })

  it("伺服器拒絕 redundant_games：該列顯示對應中文、可再編輯並重送", async () => {
    const user = userEvent.setup()
    const onRecord = vi
      .fn<ScoreEntryPanelProps["onRecord"]>()
      .mockResolvedValueOnce("redundant_games")
      .mockResolvedValueOnce(null)
    renderPanel({ ...props3, onRecord })

    await user.click(within(gameRow(2)).getByRole("button", { name: "修改" }))
    await user.clear(scoreBox(2, A))
    await user.type(scoreBox(2, A), "14")
    await user.click(within(gameRow(2)).getByRole("button", { name: "登錄" }))

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "這樣修改後，後面的局就不需要打了。請先刪除後面的局再修改",
    )
    expect(onRecord).toHaveBeenCalledWith(2, { scoreA: 14, scoreB: 13 })
    expect(scoreBox(2, A)).toBeEnabled()
    expect(scoreBox(2, A)).toHaveValue("14")

    await user.clear(scoreBox(2, A))
    await user.type(scoreBox(2, A), "11")
    await user.click(within(gameRow(2)).getByRole("button", { name: "登錄" }))

    expect(onRecord).toHaveBeenLastCalledWith(2, { scoreA: 11, scoreB: 13 })
    // 成功後回到已存的列（顯示 props 傳入的值），錯誤訊息消失
    await vi.waitFor(() =>
      expect(within(gameRow(2)).getByText("已登錄")).toBeInTheDocument(),
    )
    expect(screen.queryByRole("alert")).toBeNull()
  })

  it.each([
    ["tie", "不能平手"],
    ["invalid_score", "比分格式不正確"],
    ["series_decided", "已有隊伍達到勝局門檻"],
    ["invalid_game_no", "這一局無法修改，請重新整理頁面"],
    ["not_last_game", "這一局無法修改，請重新整理頁面"],
  ] as const)("伺服器拒絕 %s：顯示「%s」", async (reason, text) => {
    const user = userEvent.setup()
    const onRecord = vi.fn<ScoreEntryPanelProps["onRecord"]>(async () => reason)
    renderPanel({ onRecord })

    await user.type(scoreBox(1, A), "13")
    await user.type(scoreBox(1, B), "11")
    await user.click(within(gameRow(1)).getByRole("button", { name: "登錄" }))

    expect(await screen.findByRole("alert")).toHaveTextContent(text)
  })

  it("按「修改」改值後「取消」：恢復原值、不呼叫 callback", async () => {
    const user = userEvent.setup()
    const props = renderPanel(props3)

    await user.click(within(gameRow(1)).getByRole("button", { name: "修改" }))
    expect(scoreBox(1, A)).toHaveValue("13")
    await user.clear(scoreBox(1, A))
    await user.type(scoreBox(1, A), "2")
    await user.click(within(gameRow(1)).getByRole("button", { name: "取消" }))

    expect(gameRow(1)).toHaveTextContent("13:11")
    expect(within(gameRow(1)).queryByRole("textbox")).toBeNull()
    expect(props.onRecord).not.toHaveBeenCalled()
    // 再按「修改」也是從已存的值開始
    await user.click(within(gameRow(1)).getByRole("button", { name: "修改" }))
    expect(scoreBox(1, A)).toHaveValue("13")
  })

  it("正在修改第 1 局：其他列的「修改」「刪除」與「新增一局」停用", async () => {
    const user = userEvent.setup()
    renderPanel({
      games: ROUNDS_3.slice(0, 2),
      series: {
        winsA: 1,
        winsB: 1,
        winner: null,
        canSubmit: false,
        winsNeeded: 2,
      },
    })
    expect(screen.getByRole("button", { name: "新增一局" })).toBeEnabled()
    expect(
      within(gameRow(2)).getByRole("button", { name: "刪除" }),
    ).toBeEnabled()

    await user.click(within(gameRow(1)).getByRole("button", { name: "修改" }))

    expect(
      within(gameRow(2)).getByRole("button", { name: "修改" }),
    ).toBeDisabled()
    expect(
      within(gameRow(2)).getByRole("button", { name: "刪除" }),
    ).toBeDisabled()
    expect(screen.getByRole("button", { name: "新增一局" })).toBeDisabled()
  })

  it("3 局已存：只有第 3 局有「刪除」，按下即 onDelete(3)、不另外確認", async () => {
    const user = userEvent.setup()
    const props = renderPanel(props3)

    const deletes = screen.getAllByRole("button", { name: "刪除" })
    expect(deletes).toHaveLength(1)
    expect(within(gameRow(3)).getByRole("button", { name: "刪除" })).toBe(
      deletes[0],
    )

    await user.click(deletes[0])

    expect(props.onDelete).toHaveBeenCalledTimes(1)
    expect(props.onDelete).toHaveBeenCalledWith(3)
    expect(screen.queryByRole("alertdialog")).toBeNull()
  })
})

describe("S24 Score entry panel：系列結果", () => {
  it("系列勝方 a：沒有「新增一局」，「送出系列結果」可按", () => {
    renderPanel({
      games: ROUNDS_3,
      series: {
        winsA: 2,
        winsB: 1,
        winner: "a",
        canSubmit: true,
        winsNeeded: 2,
      },
    })

    expect(screen.queryByRole("button", { name: "新增一局" })).toBeNull()
    expect(screen.queryByRole("textbox")).toBeNull()
    expect(screen.getByRole("button", { name: "送出系列結果" })).toBeEnabled()
    expect(screen.queryByText(/勝後才能送出/)).toBeNull()
  })

  it("門檻 2、1：0：「送出系列結果」停用並寫「任一隊拿到 2 勝後才能送出」", () => {
    renderPanel({
      games: ROUNDS_3.slice(0, 1),
      series: {
        winsA: 1,
        winsB: 0,
        winner: null,
        canSubmit: false,
        winsNeeded: 2,
      },
    })

    expect(screen.getByText("系列結果預覽")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "送出系列結果" })).toBeDisabled()
    expect(screen.getByText("任一隊拿到 2 勝後才能送出")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "新增一局" })).toBeEnabled()
  })

  it("預覽比分只顯示 props 的勝局數，不含輸入中的局", async () => {
    const user = userEvent.setup()
    renderPanel({
      games: ROUNDS_3.slice(0, 1),
      series: {
        winsA: 1,
        winsB: 0,
        winner: null,
        canSubmit: false,
        winsNeeded: 2,
      },
    })
    const preview = screen.getByText("系列結果預覽")
      .parentElement as HTMLElement
    expect(preview).toHaveTextContent(`${A}1:0${B}`)

    await user.click(screen.getByRole("button", { name: "新增一局" }))
    await user.type(scoreBox(2, A), "13")
    await user.type(scoreBox(2, B), "5")

    expect(preview).toHaveTextContent(`${A}1:0${B}`)
  })

  it("按「送出系列結果」開 AlertDialog：取消不呼叫，確認後 onSubmit()", async () => {
    const user = userEvent.setup()
    const props = renderPanel({
      games: ROUNDS_3,
      series: {
        winsA: 2,
        winsB: 1,
        winner: "a",
        canSubmit: true,
        winsNeeded: 2,
      },
    })

    await user.click(screen.getByRole("button", { name: "送出系列結果" }))
    let dialog = await screen.findByRole("alertdialog", {
      name: "送出系列結果",
    })
    expect(dialog).toHaveTextContent("送出後無法再修改，只能經由申訴更正。")
    await user.click(within(dialog).getByRole("button", { name: "取消" }))
    expect(screen.queryByRole("alertdialog")).toBeNull()
    expect(props.onSubmit).not.toHaveBeenCalled()

    await user.click(screen.getByRole("button", { name: "送出系列結果" }))
    dialog = await screen.findByRole("alertdialog", { name: "送出系列結果" })
    await user.click(
      within(dialog).getByRole("button", { name: "送出系列結果" }),
    )

    expect(props.onSubmit).toHaveBeenCalledTimes(1)
    expect(props.onSubmit).toHaveBeenCalledWith()
  })

  it("送出被伺服器拒絕：在按鈕下方顯示原因", async () => {
    const user = userEvent.setup()
    renderPanel({
      games: ROUNDS_3,
      series: {
        winsA: 2,
        winsB: 1,
        winner: "a",
        canSubmit: true,
        winsNeeded: 2,
      },
      onSubmit: async () => "not_decided",
    })

    await user.click(screen.getByRole("button", { name: "送出系列結果" }))
    const dialog = await screen.findByRole("alertdialog")
    await user.click(
      within(dialog).getByRole("button", { name: "送出系列結果" }),
    )

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "任一隊拿到 2 勝後才能送出",
    )
  })
})

describe("S24 Score entry panel：已送出", () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it("唯讀：標籤「系列結果」、送出者與時間，沒有任何按鈕與輸入框", () => {
    vi.useFakeTimers({ toFake: ["Date"] })
    vi.setSystemTime(new Date("2026-10-17T06:00:00Z"))
    renderPanel({
      games: ROUNDS_3,
      series: {
        winsA: 2,
        winsB: 1,
        winner: "a",
        canSubmit: true,
        winsNeeded: 2,
      },
      submission: {
        submittedBy: "王小明",
        submittedAt: "2026-10-17T03:52:00Z",
      },
    })

    expect(screen.getByText("系列結果")).toBeInTheDocument()
    expect(screen.queryByText("系列結果預覽")).toBeNull()
    expect(
      screen.getByText("王小明 送出 · 10/17（六）11:52"),
    ).toBeInTheDocument()
    expect(screen.queryAllByRole("button")).toHaveLength(0)
    expect(screen.queryAllByRole("textbox")).toHaveLength(0)
    expect(screen.queryByText("已登錄")).toBeNull()
    expect(gameRow(3)).toHaveTextContent("13:10")
  })
})

describe("S24 Score entry panel：手機寬度", () => {
  it("表格放在可橫向捲動的容器內，面板本身不被表格撐寬", () => {
    renderPanel({ games: ROUNDS_3.slice(0, 1) })

    // jsdom 不排版，只能檢查會讓 375px 寬度成立的結構；實際寬度要在瀏覽器確認
    const table = screen.getByRole("table")
    expect(table.parentElement).toHaveClass("overflow-x-auto")
    expect(table.closest("fieldset")).toHaveClass("min-w-0")
  })
})

describe("S24 Score entry panel：審查後補強", () => {
  it("同步連按兩次「登錄」（送出中）：onRecord 只被呼叫一次", async () => {
    const user = userEvent.setup()
    const { promise, resolve } = deferred()
    const onRecord = vi.fn<ScoreEntryPanelProps["onRecord"]>(() => promise)
    renderPanel({ onRecord })
    await user.type(scoreBox(1, A), "13")
    await user.type(scoreBox(1, B), "11")
    const record = within(gameRow(1)).getByRole("button", { name: "登錄" })

    fireEvent.click(record)
    fireEvent.click(record)

    expect(onRecord).toHaveBeenCalledTimes(1)
    await act(async () => resolve(null))
  })

  it("刪除第 3 局送出中：「修改」與「送出系列結果」停用，完成後恢復", async () => {
    const user = userEvent.setup()
    const { promise, resolve } = deferred()
    const onDelete = vi.fn<ScoreEntryPanelProps["onDelete"]>(() => promise)
    renderPanel({ games: ROUNDS_3, series: DECIDED, onDelete })

    await user.click(within(gameRow(3)).getByRole("button", { name: "刪除" }))

    expect(onDelete).toHaveBeenCalledWith(3)
    for (const button of screen.getAllByRole("button", { name: "修改" })) {
      expect(button).toBeDisabled()
    }
    expect(screen.getByRole("button", { name: "送出系列結果" })).toBeDisabled()

    await act(async () => resolve(null))
    expect(screen.getByRole("button", { name: "送出系列結果" })).toBeEnabled()
    for (const button of screen.getAllByRole("button", { name: "修改" })) {
      expect(button).toBeEnabled()
    }
  })

  it("刪除最後一局送出中（系列未決定）：「新增一局」停用，完成後恢復", async () => {
    const user = userEvent.setup()
    const { promise, resolve } = deferred()
    renderPanel({
      games: ROUNDS_3.slice(0, 2),
      series: {
        winsA: 1,
        winsB: 1,
        winner: null,
        canSubmit: false,
        winsNeeded: 2,
      },
      onDelete: () => promise,
    })

    await user.click(within(gameRow(2)).getByRole("button", { name: "刪除" }))

    expect(screen.getByRole("button", { name: "新增一局" })).toBeDisabled()
    await act(async () => resolve(null))
    expect(screen.getByRole("button", { name: "新增一局" })).toBeEnabled()
  })

  it("onDelete 回傳 not_last_game：在第 3 局下方顯示原因", async () => {
    const user = userEvent.setup()
    renderPanel({
      games: ROUNDS_3,
      series: DECIDED,
      onDelete: async () => "not_last_game",
    })

    await user.click(within(gameRow(3)).getByRole("button", { name: "刪除" }))

    const alert = await screen.findByRole("alert")
    expect(alert).toHaveTextContent("這一局無法修改，請重新整理頁面")
    expect(gameRow(3).nextElementSibling).toContainElement(alert)
  })

  it("onRecord 回傳沒有對應文字的代碼：列內顯示「操作失敗，請重新整理頁面」", async () => {
    const user = userEvent.setup()
    renderPanel({ onRecord: async () => "not_decided" })

    await user.type(scoreBox(1, A), "13")
    await user.type(scoreBox(1, B), "11")
    await user.click(within(gameRow(1)).getByRole("button", { name: "登錄" }))

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "操作失敗，請重新整理頁面",
    )
  })

  it("onSubmit 回傳 not_decided 以外的代碼：顯示「送出失敗，請重新整理頁面」", async () => {
    const user = userEvent.setup()
    renderPanel({
      games: ROUNDS_3,
      series: DECIDED,
      onSubmit: async () => "redundant_games",
    })

    const dialog = await openSubmitDialog(user)
    await user.click(
      within(dialog).getByRole("button", { name: "送出系列結果" }),
    )

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "送出失敗，請重新整理頁面",
    )
    expect(screen.queryByText(/後面的局就不需要打了/)).toBeNull()
  })

  it("onRecord reject：該列恢復可編輯，不顯示錯誤", async () => {
    const user = userEvent.setup()
    const onRecord = vi.fn<ScoreEntryPanelProps["onRecord"]>(async () => {
      throw new Error("network")
    })
    renderPanel({ onRecord })

    await user.type(scoreBox(1, A), "13")
    await user.type(scoreBox(1, B), "11")
    await user.click(within(gameRow(1)).getByRole("button", { name: "登錄" }))

    await vi.waitFor(() => expect(scoreBox(1, A)).toBeEnabled())
    expect(onRecord).toHaveBeenCalledTimes(1)
    expect(scoreBox(1, A)).toHaveValue("13")
    expect(
      within(gameRow(1)).getByRole("button", { name: "登錄" }),
    ).toBeEnabled()
    expect(screen.queryByRole("alert")).toBeNull()
  })

  it("有列在編輯中：「送出系列結果」停用並寫「請先登錄或取消正在編輯的局」", async () => {
    const user = userEvent.setup()
    renderPanel({ games: ROUNDS_3, series: DECIDED })
    expect(screen.queryByText("請先登錄或取消正在編輯的局")).toBeNull()

    await user.click(within(gameRow(2)).getByRole("button", { name: "修改" }))

    expect(screen.getByRole("button", { name: "送出系列結果" })).toBeDisabled()
    expect(screen.getByText("請先登錄或取消正在編輯的局")).toBeInTheDocument()

    await user.click(within(gameRow(2)).getByRole("button", { name: "取消" }))
    expect(screen.getByRole("button", { name: "送出系列結果" })).toBeEnabled()
    expect(screen.queryByText("請先登錄或取消正在編輯的局")).toBeNull()
  })

  it("編輯中收到 submission：離開編輯狀態，只剩唯讀列", async () => {
    const user = userEvent.setup()
    const panel = renderPanel({ games: ROUNDS_3, series: DECIDED })
    await user.click(within(gameRow(2)).getByRole("button", { name: "修改" }))
    expect(scoreBox(2, A)).toBeInTheDocument()

    panel.update({
      submission: {
        submittedBy: "王小明",
        submittedAt: "2026-10-17T03:52:00Z",
      },
    })

    expect(screen.queryAllByRole("textbox")).toHaveLength(0)
    expect(screen.queryAllByRole("button")).toHaveLength(0)
    expect(gameRow(2)).toHaveTextContent("9:13")
  })

  it("games 或 series 更新：清掉舊的列內錯誤與送出錯誤", async () => {
    const user = userEvent.setup()
    const panel = renderPanel({
      games: ROUNDS_3,
      series: DECIDED,
      onDelete: async () => "not_last_game",
      onSubmit: async () => "not_decided",
    })
    await user.click(within(gameRow(3)).getByRole("button", { name: "刪除" }))
    expect(await screen.findByRole("alert")).toBeInTheDocument()

    panel.update({ games: [...ROUNDS_3] })
    expect(screen.queryByRole("alert")).toBeNull()

    const dialog = await openSubmitDialog(user)
    await user.click(
      within(dialog).getByRole("button", { name: "送出系列結果" }),
    )
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "任一隊拿到 2 勝後才能送出",
    )

    panel.update({ series: { ...DECIDED } })
    expect(screen.queryByRole("alert")).toBeNull()
  })

  it("有勝方但不能送出：不顯示「任一隊拿到 N 勝後才能送出」", () => {
    renderPanel({ games: ROUNDS_3, series: { ...DECIDED, canSubmit: false } })

    expect(screen.getByRole("button", { name: "送出系列結果" })).toBeDisabled()
    expect(screen.queryByText(/勝後才能送出/)).toBeNull()
  })

  it.each([
    ["１３", "13"],
    ["0013", "13"],
    ["0", "0"],
    ["00", "0"],
    ["1234", "123"],
  ])("數字框輸入 %s：得到 %s", async (typed, value) => {
    const user = userEvent.setup()
    renderPanel()

    await user.type(scoreBox(1, A), typed)

    expect(scoreBox(1, A)).toHaveValue(value)
    expect(scoreBox(1, A)).toHaveAttribute("maxlength", "3")
  })

  it("數字框按 Enter：登錄該列", async () => {
    const user = userEvent.setup()
    const props = renderPanel()

    await user.type(scoreBox(1, A), "13")
    await user.type(scoreBox(1, B), "11{Enter}")

    expect(props.onRecord).toHaveBeenCalledTimes(1)
    expect(props.onRecord).toHaveBeenCalledWith(1, { scoreA: 13, scoreB: 11 })
  })

  it("數字框按 Enter 但平手：不呼叫 callback", async () => {
    const user = userEvent.setup()
    const props = renderPanel()

    await user.type(scoreBox(1, A), "12")
    await user.type(scoreBox(1, B), "12{Enter}")

    expect(props.onRecord).not.toHaveBeenCalled()
  })

  it("AlertDialog 在固定說明上方顯示要送出的系列比分", async () => {
    const user = userEvent.setup()
    renderPanel({ games: ROUNDS_3, series: DECIDED })

    const dialog = await openSubmitDialog(user)

    expect(within(dialog).getByText(`${A} 2 : 1 ${B}`)).toBeInTheDocument()
    expect(dialog).toHaveTextContent(
      `${A} 2 : 1 ${B}送出後無法再修改，只能經由申訴更正。`,
    )
  })
})
