import { focusManager } from "@tanstack/react-query"
import {
  configure,
  fireEvent,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { toast } from "sonner"
import { describe, expect, it, vi } from "vitest"

import {
  CompetitionService,
  type ManagedMatch,
  type RefereeRead,
  type TournamentRead,
  TournamentsService,
} from "@/client"
import { formatMatchDateTime } from "@/features/competition/match-time"
import { NO_BRACKET_TEXT } from "@/features/competition/OrganizerMatchesPage"
import {
  NO_REFEREE_TEXT,
  NO_REFEREES_TEXT,
  ORGANIZER_SCORES_TEXT,
} from "@/features/competition/RefereeSelect"
import { FORBIDDEN_FALLBACK_MESSAGE } from "@/lib/api-error"
import { isoToTaipeiLocal } from "@/lib/datetime"
import { ACCOUNT, renderApp, signInAs } from "./auth-fixtures"
import { httpError } from "./helpers"

vi.mock("@tanstack/react-router-devtools", () => ({
  TanStackRouterDevtools: () => null,
}))
vi.mock("@tanstack/react-query-devtools", () => ({
  ReactQueryDevtools: () => null,
}))

// 第一次載入路由要轉譯整棵路由樹，預設 1 秒在冷啟動時不夠
configure({ asyncUtilTimeout: 5000 })

const ORGANIZER = { ...ACCOUNT, is_organizer: true }
const URL = "/organizer/tournaments/t-1/matches"

const TOURNAMENT = {
  id: "t-1",
  organizer_id: ORGANIZER.id,
  name: "臺大秋季盃",
  status: "published",
} as TournamentRead

const REFEREES: RefereeRead[] = [
  {
    account_id: "r-1",
    display_name: "王裁判",
    accepted_at: "2026-11-01T00:00:00Z",
  },
  {
    account_id: "r-2",
    display_name: "李裁判",
    accepted_at: "2026-11-01T00:00:00Z",
  },
]

const CAN_RESCHEDULE = {
  can_reschedule: true,
  reason: null,
  // 台北時間 2026/11/10 19:00 ～ 2026/11/10 22:30
  earliest: "2026-11-10T11:00:00Z",
  latest: "2026-11-10T14:30:00Z",
}

function match(overrides: Partial<ManagedMatch> = {}): ManagedMatch {
  return {
    id: "m-1",
    code: "M1",
    round_no: 1,
    slot_no: 1,
    is_third_place: false,
    team_a: { id: "a", name: "甲隊" },
    team_b: { id: "b", name: "乙隊" },
    source_a: null,
    source_b: null,
    scheduled_at: "2026-11-10T12:00:00Z",
    status: "scheduled",
    referee_account_id: null,
    reschedule: CAN_RESCHEDULE,
    assignable_referee_ids: ["r-1", "r-2"],
    can_assign_referee: true,
    ...overrides,
  }
}

// 4 強賽制：兩場準決賽（第 1 輪）、決賽與季軍賽（第 2 輪，故意把季軍賽排在決賽前）
const SEMI_1 = match({ id: "m-1", code: "M1" })
const SEMI_2 = match({
  id: "m-2",
  code: "M2",
  slot_no: 2,
  team_a: { id: "c", name: "丙隊" },
  team_b: { id: "d", name: "丁隊" },
})
const THIRD = match({
  id: "m-4",
  code: "M4",
  round_no: 2,
  slot_no: 2,
  is_third_place: true,
  team_a: null,
  team_b: null,
  source_a: "M1 敗者",
  source_b: "M2 敗者",
  can_assign_referee: false,
  assignable_referee_ids: [],
  reschedule: {
    can_reschedule: false,
    reason: "match_not_reschedulable",
    earliest: null,
    latest: null,
  },
})
const FINAL = match({
  id: "m-3",
  code: "M3",
  round_no: 2,
  slot_no: 1,
  team_a: null,
  team_b: null,
  source_a: "M1 勝者",
  source_b: "M2 勝者",
  reschedule: { ...CAN_RESCHEDULE, latest: null },
})

type ListResult = Awaited<
  ReturnType<typeof CompetitionService.listManagedMatches>
>
type RefereesResult = Awaited<
  ReturnType<typeof TournamentsService.listTournamentReferees>
>
type ReadResult = Awaited<
  ReturnType<typeof TournamentsService.readMyTournament>
>

function mockList(...pages: ManagedMatch[][]) {
  const spy = vi.spyOn(CompetitionService, "listManagedMatches")
  for (const page of pages) {
    spy.mockResolvedValueOnce({ data: page } as ListResult)
  }
  // 超過準備的次數就一直回傳最後一份
  spy.mockResolvedValue({ data: pages[pages.length - 1] } as ListResult)
  return spy
}

function mockReferees(referees: RefereeRead[] = REFEREES) {
  return vi
    .spyOn(TournamentsService, "listTournamentReferees")
    .mockResolvedValue({ data: referees } as RefereesResult)
}

function open(url = URL) {
  vi.spyOn(TournamentsService, "readMyTournament").mockResolvedValue({
    data: TOURNAMENT,
  } as ReadResult)
  signInAs({ account: ORGANIZER })
  return renderApp(url)
}

/** 桌機的表格區（jsdom 沒有 CSS，卡片清單也會一起渲染，所以查詢都限定在表格內）。 */
function tableArea(): HTMLElement {
  return document.querySelector("[data-slot=data-table]") as HTMLElement
}

function tableRows() {
  const table = within(
    document.querySelector("[data-slot=data-table]") as HTMLElement,
  ).getByRole("table", { name: "場次管理" })
  return within(table).getAllByRole("row").slice(1)
}

async function rowOf(label: string) {
  await screen.findByRole("table", { name: "場次管理" })
  const row = tableRows().find(
    (r) => within(r).queryAllByText(label).length > 0,
  )
  if (!row) throw new Error(`找不到 ${label} 那一列`)
  return row
}

describe("S30 場次管理：列表", () => {
  it("側欄有「場次管理」；依輪次排序、季軍賽在決賽之後；欄位與內容", async () => {
    mockList([THIRD, FINAL, SEMI_2, SEMI_1])
    mockReferees()
    open()

    await screen.findByRole("table", { name: "場次管理" })
    expect(
      within(
        document.querySelector("[data-slot=backoffice-sidebar]") as HTMLElement,
      ).getByRole("link", { name: "場次管理" }),
    ).toHaveAttribute("href", URL)
    const table = within(
      document.querySelector("[data-slot=data-table]") as HTMLElement,
    ).getByRole("table", { name: "場次管理" })
    expect(
      within(table)
        .getAllByRole("columnheader")
        .map((header) => header.textContent),
    ).toEqual(["場次", "輪次", "對戰", "時間", "狀態", "裁判", "操作"])

    const rows = tableRows()
    expect(
      rows.map((r) => within(r).getAllByRole("cell")[0].textContent),
    ).toEqual(["M1", "M2", "M3", "季軍賽"])
    // 兩輪：第 1 輪「4 強」、第 2 輪「決賽」，季軍賽寫「季軍賽」
    const roundOf = (r: HTMLElement) =>
      within(r).getAllByRole("cell")[1].textContent
    expect(rows.map(roundOf)).toEqual(["4 強", "4 強", "決賽", "季軍賽"])
    const teamsOf = (r: HTMLElement) =>
      within(r).getAllByRole("cell")[2].textContent
    expect(teamsOf(rows[0])).toBe("甲隊 vs 乙隊")
    expect(teamsOf(rows[2])).toBe("M1 勝者 vs M2 勝者")
    expect(teamsOf(rows[3])).toBe("M1 敗者 vs M2 敗者")
    expect(
      within(rows[0]).getByText(formatMatchDateTime(SEMI_1.scheduled_at)),
    ).toBeInTheDocument()
    expect(within(rows[0]).getByText("待開打")).toHaveAttribute(
      "data-tone",
      "muted",
    )
    expect(
      within(rows[0]).getByRole("link", { name: "查看場次" }),
    ).toHaveAttribute("href", "/tournaments/t-1/matches/m-1")
  })

  it("每頁 20 筆，頁碼寫在網址", async () => {
    const user = userEvent.setup()
    const many = Array.from({ length: 21 }, (_, i) =>
      match({ id: `m-${i + 1}`, code: `M${i + 1}`, slot_no: i + 1 }),
    )
    mockList(many)
    mockReferees()
    const router = open()

    await rowOf("M20")
    expect(tableRows()).toHaveLength(20)
    await user.click(screen.getByRole("button", { name: "下一頁" }))
    await rowOf("M21")
    expect(tableRows()).toHaveLength(1)
    expect(router.state.location.search).toEqual({ page: 2 })
  })

  it("未抽籤（404 BRACKET_NOT_FOUND）：空狀態", async () => {
    vi.spyOn(CompetitionService, "listManagedMatches").mockRejectedValue(
      httpError(404, {
        detail: { code: "BRACKET_NOT_FOUND", message: "尚未抽籤" },
      }),
    )
    mockReferees()
    open()

    expect(await screen.findByText(NO_BRACKET_TEXT)).toBeInTheDocument()
  })

  it("載入失敗：顯示錯誤，按重新載入會重抓", async () => {
    const user = userEvent.setup()
    const list = vi
      .spyOn(CompetitionService, "listManagedMatches")
      .mockRejectedValueOnce(
        httpError(400, { detail: { code: "X", message: "壞掉了" } }),
      )
      .mockResolvedValue({ data: [SEMI_1] } as ListResult)
    mockReferees()
    open()

    expect(await screen.findByText("壞掉了")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "重新載入" }))
    await rowOf("M1")
    expect(list).toHaveBeenCalledTimes(2)
  })

  it("非主辦方（403）：顯示無權限畫面", async () => {
    vi.spyOn(CompetitionService, "listManagedMatches").mockRejectedValue(
      httpError(403, {
        detail: { code: "TOURNAMENT_OWNER_REQUIRED", message: "不是你的賽事" },
      }),
    )
    mockReferees()
    open()

    expect(
      await screen.findByRole("heading", { name: FORBIDDEN_FALLBACK_MESSAGE }),
    ).toBeInTheDocument()
  })
})

describe("S30 列表：補充", () => {
  it("網址頁碼超出：換到最後一頁", async () => {
    const many = Array.from({ length: 21 }, (_, i) =>
      match({ id: `m-${i + 1}`, code: `M${i + 1}`, slot_no: i + 1 }),
    )
    mockList(many)
    mockReferees()
    const router = open(`${URL}?page=9`)

    await rowOf("M21")
    await waitFor(() =>
      expect(router.state.location.search).toEqual({ page: 2 }),
    )
  })

  it("裁判清單還在載入（含重試）：場次列照常顯示，裁判欄為「—」", async () => {
    mockList([SEMI_1])
    vi.spyOn(TournamentsService, "listTournamentReferees").mockReturnValue(
      new Promise(() => {}) as ReturnType<
        typeof TournamentsService.listTournamentReferees
      >,
    )
    open()

    const row = await rowOf("M1")
    expect(within(row).getByText("—")).toBeInTheDocument()
    expect(within(row).queryByRole("combobox")).toBeNull()
  })

  it("裁判清單載入失敗：顯示錯誤與重新載入，不顯示「沒有裁判」或「未知的裁判」", async () => {
    const user = userEvent.setup()
    mockList([match({ referee_account_id: "r-1" })])
    const referees = vi
      .spyOn(TournamentsService, "listTournamentReferees")
      .mockRejectedValueOnce(httpError(403, { detail: "forbidden" }))
      .mockResolvedValue({ data: REFEREES } as RefereesResult)
    open()

    expect(await screen.findByText(/裁判清單載入失敗/)).toBeInTheDocument()
    await rowOf("M1")
    expect(screen.queryByText(NO_REFEREES_TEXT)).toBeNull()
    expect(screen.queryByText("未知的裁判")).toBeNull()
    expect(within(tableArea()).queryByRole("combobox")).toBeNull()
    // 改時間不受影響
    expect(
      within(tableArea()).getByRole("button", { name: "修改時間" }),
    ).toBeEnabled()

    await user.click(screen.getByRole("button", { name: "重新載入" }))
    await waitFor(() =>
      expect(
        within(tableArea()).getByRole("combobox", { name: "M1的裁判" }),
      ).toHaveTextContent("王裁判"),
    )
    expect(referees).toHaveBeenCalledTimes(2)
  })

  it("裁判清單 500：重試後顯示錯誤，不顯示「沒有裁判」或「未知的裁判」", async () => {
    mockList([match({ referee_account_id: "r-1" })])
    vi.spyOn(TournamentsService, "listTournamentReferees").mockRejectedValue(
      httpError(500, "Internal Server Error"),
    )
    open()

    // 預設重試 3 次（約 7 秒）後才會進入錯誤狀態
    expect(
      await screen.findByText(/裁判清單載入失敗/, undefined, {
        timeout: 15000,
      }),
    ).toBeInTheDocument()
    expect(screen.queryByText(NO_REFEREES_TEXT)).toBeNull()
    expect(screen.queryByText("未知的裁判")).toBeNull()
  }, 20000)
})

describe("S30 修改時間", () => {
  it("已報到：按鈕停用並寫原因", async () => {
    mockList([
      match({
        reschedule: {
          can_reschedule: false,
          reason: "already_checked_in",
          earliest: null,
          latest: null,
        },
      }),
    ])
    mockReferees()
    open()

    const row = await rowOf("M1")
    expect(within(row).getByRole("button", { name: "修改時間" })).toBeDisabled()
    expect(
      within(row).getByText("已有隊伍報到，無法修改時間"),
    ).toBeInTheDocument()
  })

  it("Dialog 的 min／max 是 earliest／latest 轉成台北時間；latest 為 null 不設上限", async () => {
    const user = userEvent.setup()
    mockList([SEMI_1, FINAL])
    mockReferees()
    open()

    const row = await rowOf("M1")
    await user.click(within(row).getByRole("button", { name: "修改時間" }))
    const input = await screen.findByLabelText("新的開打時間（台北時間）")
    expect(input).toHaveAttribute("min", "2026-11-10T19:00")
    expect(input).toHaveAttribute("max", "2026-11-10T22:30")
    expect(input).toHaveValue(isoToTaipeiLocal(SEMI_1.scheduled_at))
    expect(
      screen.getByText(/可選 11\/10（二）19:00～11\/10（二）22:30/),
    ).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "取消" }))
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull())

    const finalRow = await rowOf("M3")
    await user.click(within(finalRow).getByRole("button", { name: "修改時間" }))
    const finalInput = await screen.findByLabelText("新的開打時間（台北時間）")
    expect(finalInput).toHaveAttribute("min", "2026-11-10T19:00")
    expect(finalInput).not.toHaveAttribute("max")
    expect(screen.getByText(/11\/10（二）19:00 以後/)).toBeInTheDocument()
  })

  it("範圍內送出：送 UTC、成功提示、列表重抓顯示新時間", async () => {
    const user = userEvent.setup()
    const success = vi.spyOn(toast, "success")
    const moved = match({ scheduled_at: "2026-11-10T13:00:00Z" })
    const list = mockList([SEMI_1], [moved])
    mockReferees()
    const reschedule = vi
      .spyOn(CompetitionService, "rescheduleMatch")
      .mockResolvedValue({ data: {} } as never)
    open()

    const row = await rowOf("M1")
    await user.click(within(row).getByRole("button", { name: "修改時間" }))
    const input = await screen.findByLabelText("新的開打時間（台北時間）")
    fireEvent.change(input, { target: { value: "2026-11-10T21:00" } })
    await user.click(screen.getByRole("button", { name: "儲存時間" }))

    await waitFor(() => expect(reschedule).toHaveBeenCalledTimes(1))
    expect(reschedule.mock.calls[0][0]).toMatchObject({
      path: { tournament_id: "t-1", match_id: "m-1" },
      body: { scheduled_at: "2026-11-10T13:00:00.000Z" },
    })
    expect(success).toHaveBeenCalledWith("已修改場次時間", expect.anything())
    await waitFor(() => expect(list).toHaveBeenCalledTimes(2))
    expect(
      await within(tableArea()).findByText(
        formatMatchDateTime(moved.scheduled_at),
      ),
    ).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull())
  })

  it("409：顯示後端訊息、重抓列表、Dialog 維持開啟", async () => {
    const user = userEvent.setup()
    const error = vi.spyOn(toast, "error")
    const list = mockList([SEMI_1])
    mockReferees()
    vi.spyOn(CompetitionService, "rescheduleMatch").mockRejectedValue(
      httpError(409, {
        detail: {
          code: "RESCHEDULE_BEFORE_NOW",
          message: "可選 11/10（二）19:00～22:30。",
        },
      }),
    )
    open()

    const row = await rowOf("M1")
    await user.click(within(row).getByRole("button", { name: "修改時間" }))
    const input = await screen.findByLabelText("新的開打時間（台北時間）")
    fireEvent.change(input, { target: { value: "2026-11-10T21:00" } })
    await user.click(screen.getByRole("button", { name: "儲存時間" }))

    await waitFor(() =>
      expect(error).toHaveBeenCalledWith(
        "可選 11/10（二）19:00～22:30。",
        expect.anything(),
      ),
    )
    await waitFor(() => expect(list).toHaveBeenCalledTimes(2))
    expect(screen.getByRole("dialog")).toBeInTheDocument()
  })

  it("409 重抓後起點變晚：輸入值調到新起點", async () => {
    const user = userEvent.setup()
    mockList(
      [SEMI_1],
      [
        match({
          reschedule: {
            ...CAN_RESCHEDULE,
            earliest: "2026-11-10T13:00:00Z",
          },
        }),
      ],
    )
    mockReferees()
    vi.spyOn(CompetitionService, "rescheduleMatch").mockRejectedValue(
      httpError(409, {
        detail: { code: "RESCHEDULE_BEFORE_NOW", message: "可選範圍已變更。" },
      }),
    )
    open()

    const row = await rowOf("M1")
    await user.click(within(row).getByRole("button", { name: "修改時間" }))
    const input = await screen.findByLabelText("新的開打時間（台北時間）")
    fireEvent.change(input, { target: { value: "2026-11-10T20:30" } })
    await user.click(screen.getByRole("button", { name: "儲存時間" }))

    // 新起點是台北 21:00，20:30 低於它，調到 21:00
    await waitFor(() => expect(input).toHaveValue("2026-11-10T21:00"))
    expect(input).toHaveAttribute("min", "2026-11-10T21:00")
  })

  it("原時間早於允許起點：預填起點；沒改時間時不能儲存", async () => {
    const user = userEvent.setup()
    mockList([
      match({ scheduled_at: "2026-11-10T10:00:00Z" }),
      match({ id: "m-2", code: "M2", slot_no: 2 }),
    ])
    mockReferees()
    open()

    const early = await rowOf("M1")
    await user.click(within(early).getByRole("button", { name: "修改時間" }))
    const input = await screen.findByLabelText("新的開打時間（台北時間）")
    // earliest 是台北時間 19:00，原時間 18:00 低於 min，預填 19:00
    expect(input).toHaveValue("2026-11-10T19:00")
    expect(screen.getByRole("button", { name: "儲存時間" })).toBeEnabled()
    await user.click(screen.getByRole("button", { name: "取消" }))
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull())

    const same = await rowOf("M2")
    await user.click(within(same).getByRole("button", { name: "修改時間" }))
    await screen.findByLabelText("新的開打時間（台北時間）")
    expect(screen.getByRole("button", { name: "儲存時間" })).toBeDisabled()
  })

  it("開著的 Dialog 在不能修改時關閉，之後恢復也不會自己重開", async () => {
    const user = userEvent.setup()
    const blocked = match({
      reschedule: {
        can_reschedule: false,
        reason: "already_checked_in",
        earliest: null,
        latest: null,
      },
    })
    const list = mockList([SEMI_1], [blocked], [SEMI_1])
    mockReferees()
    vi.spyOn(CompetitionService, "rescheduleMatch").mockRejectedValue(
      httpError(409, {
        detail: { code: "MATCH_ALREADY_CHECKED_IN", message: "已有隊伍報到" },
      }),
    )
    open()

    const row = await rowOf("M1")
    await user.click(within(row).getByRole("button", { name: "修改時間" }))
    const input = await screen.findByLabelText("新的開打時間（台北時間）")
    fireEvent.change(input, { target: { value: "2026-11-10T21:00" } })
    await user.click(screen.getByRole("button", { name: "儲存時間" }))

    // 第二次抓到的列表不能修改：Dialog 關閉
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull())
    // 再抓一次恢復可修改：不會自己重新打開
    await rowOf("M1")
    // 視窗重新取得焦點會讓列表重抓（第三份：恢復可修改）
    focusManager.setFocused(false)
    focusManager.setFocused(true)
    await waitFor(() => expect(list).toHaveBeenCalledTimes(3))
    expect(
      within(tableArea()).getByRole("button", { name: "修改時間" }),
    ).toBeEnabled()
    expect(screen.queryByRole("dialog")).toBeNull()
  })

  it("時間欄清空：不送出，顯示提示", async () => {
    const user = userEvent.setup()
    mockList([SEMI_1])
    mockReferees()
    const reschedule = vi.spyOn(CompetitionService, "rescheduleMatch")
    open()

    const row = await rowOf("M1")
    await user.click(within(row).getByRole("button", { name: "修改時間" }))
    const input = await screen.findByLabelText("新的開打時間（台北時間）")
    fireEvent.change(input, { target: { value: "" } })
    await user.click(screen.getByRole("button", { name: "儲存時間" }))

    expect(await screen.findByText("請選擇有效的時間")).toBeInTheDocument()
    expect(reschedule).not.toHaveBeenCalled()
  })
})

describe("S30 指派裁判", () => {
  it("選一位裁判：送出、提示、列表重抓後顯示", async () => {
    const user = userEvent.setup()
    const success = vi.spyOn(toast, "success")
    const list = mockList([SEMI_1], [match({ referee_account_id: "r-2" })])
    mockReferees()
    const assign = vi
      .spyOn(CompetitionService, "assignReferee")
      .mockResolvedValue({ data: {} } as never)
    open()

    await rowOf("M1")
    await user.click(
      within(tableArea()).getByRole("combobox", { name: "M1的裁判" }),
    )
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual([
      NO_REFEREE_TEXT,
      "王裁判",
      "李裁判",
    ])
    await user.click(screen.getByRole("option", { name: "李裁判" }))

    await waitFor(() => expect(assign).toHaveBeenCalledTimes(1))
    expect(assign.mock.calls[0][0]).toMatchObject({
      path: { tournament_id: "t-1", match_id: "m-1" },
      body: { account_id: "r-2" },
    })
    expect(success).toHaveBeenCalledWith("已指派裁判", expect.anything())
    await waitFor(() => expect(list).toHaveBeenCalledTimes(2))
    await waitFor(() =>
      expect(
        within(tableArea()).getByRole("combobox", { name: "M1的裁判" }),
      ).toHaveTextContent("李裁判"),
    )
  })

  it("選「不指派」：收回，裁判欄回到主辦方登錄比分", async () => {
    const user = userEvent.setup()
    const success = vi.spyOn(toast, "success")
    const list = mockList(
      [match({ referee_account_id: "r-1" })],
      [match({ referee_account_id: null })],
    )
    mockReferees()
    const unassign = vi
      .spyOn(CompetitionService, "unassignReferee")
      .mockResolvedValue({ data: {} } as never)
    open()

    await rowOf("M1")
    expect(
      within(tableArea()).getByRole("combobox", { name: "M1的裁判" }),
    ).toHaveTextContent("王裁判")
    await user.click(
      within(tableArea()).getByRole("combobox", { name: "M1的裁判" }),
    )
    await user.click(screen.getByRole("option", { name: NO_REFEREE_TEXT }))

    await waitFor(() => expect(unassign).toHaveBeenCalledTimes(1))
    expect(unassign.mock.calls[0][0]).toMatchObject({
      path: { tournament_id: "t-1", match_id: "m-1" },
    })
    expect(success).toHaveBeenCalledWith("已收回裁判", expect.anything())
    await waitFor(() => expect(list).toHaveBeenCalledTimes(2))
    await waitFor(() =>
      expect(
        within(tableArea()).getByRole("combobox", { name: "M1的裁判" }),
      ).toHaveTextContent(NO_REFEREE_TEXT),
    )
  })

  it("409：顯示後端訊息並重抓", async () => {
    const user = userEvent.setup()
    const error = vi.spyOn(toast, "error")
    const list = mockList([SEMI_1])
    mockReferees()
    vi.spyOn(CompetitionService, "assignReferee").mockRejectedValue(
      httpError(409, {
        detail: {
          code: "REFEREE_IS_TEAM_MEMBER",
          message: "裁判是這場隊伍的隊員",
        },
      }),
    )
    open()

    await rowOf("M1")
    await user.click(
      within(tableArea()).getByRole("combobox", { name: "M1的裁判" }),
    )
    await user.click(screen.getByRole("option", { name: "王裁判" }))

    await waitFor(() =>
      expect(error).toHaveBeenCalledWith(
        "裁判是這場隊伍的隊員",
        expect.anything(),
      ),
    )
    await waitFor(() => expect(list).toHaveBeenCalledTimes(2))
  })

  it("目前裁判不在可指派名單內：仍顯示為已選", async () => {
    mockList([
      match({ referee_account_id: "r-1", assignable_referee_ids: ["r-2"] }),
    ])
    mockReferees()
    open()

    await rowOf("M1")
    expect(
      within(tableArea()).getByRole("combobox", { name: "M1的裁判" }),
    ).toHaveTextContent("王裁判")
  })

  it("不能指派：只顯示目前裁判文字，沒有選單", async () => {
    mockList([
      match({
        id: "m-1",
        code: "M1",
        referee_account_id: "r-1",
        can_assign_referee: false,
      }),
      match({ id: "m-2", code: "M2", slot_no: 2, can_assign_referee: false }),
    ])
    mockReferees()
    open()

    const row = await rowOf("M1")
    expect(within(row).getByText("王裁判")).toBeInTheDocument()
    expect(within(tableArea()).queryByRole("combobox")).toBeNull()
    const second = await rowOf("M2")
    expect(within(second).getByText(ORGANIZER_SCORES_TEXT)).toBeInTheDocument()
  })

  it("沒有裁判：選單只有「不指派」，下方寫說明", async () => {
    const user = userEvent.setup()
    mockList([match({ assignable_referee_ids: [] })])
    mockReferees([])
    open()

    await rowOf("M1")
    expect(within(tableArea()).getByText(NO_REFEREES_TEXT)).toBeInTheDocument()
    await user.click(
      within(tableArea()).getByRole("combobox", { name: "M1的裁判" }),
    )
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual([
      NO_REFEREE_TEXT,
    ])
  })
})
