import { configure, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import {
  type AuditLogEntry,
  type AuditLogPage,
  type TournamentRead,
  TournamentsService,
} from "@/client"
import {
  AUDIT_LOG_EMPTY_TEXT,
  auditActionLabel,
  auditChanges,
  formatAuditTime,
  formatAuditValue,
  SYSTEM_ACTOR_TEXT,
} from "@/features/tournaments/audit-log"
import { FORBIDDEN_FALLBACK_MESSAGE } from "@/lib/api-error"
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
const URL = "/organizer/tournaments/t-1/audit-log"

const TOURNAMENT = {
  id: "t-1",
  organizer_id: ORGANIZER.id,
  name: "臺大秋季盃",
  status: "open",
  mode: "campus",
  game_name: "特戰英豪",
  capacity: 8,
  registration_start: "2026-10-01T00:00:00Z",
  registration_end: "2026-10-10T00:00:00Z",
  priority_end: "2026-10-05T00:00:00Z",
  start_at: "2026-10-26T11:00:00Z",
  round_interval_minutes: 180,
  bo: 3,
  starters: 5,
  substitutes: 2,
  forfeit_minutes: 15,
  appeal_minutes: 30,
  livestream_url: null,
} as unknown as TournamentRead

function entry(overrides: Partial<AuditLogEntry> = {}): AuditLogEntry {
  return {
    id: "a-1",
    at: "2026-11-21T06:05:09Z",
    actor_id: ORGANIZER.id,
    actor_display_name: "主辦小明",
    action: "tournament.created",
    entity_type: "tournament",
    entity_id: "t-1",
    before: null,
    after: { name: "臺大秋季盃", capacity: 8 },
    ...overrides,
  }
}

const STATUS_CHANGED = entry({
  id: "a-2",
  at: "2026-11-21T06:06:00Z",
  actor_id: null,
  actor_display_name: null,
  action: "tournament.status_changed",
  before: { status: "upcoming" },
  after: { status: "open" },
})

type ListResult = Awaited<
  ReturnType<typeof TournamentsService.listTournamentAuditLog>
>
type ReadResult = Awaited<
  ReturnType<typeof TournamentsService.readMyTournament>
>

function page(
  items: AuditLogEntry[],
  overrides: Partial<AuditLogPage> = {},
): ListResult {
  return {
    data: { items, total: items.length, page: 1, page_size: 20, ...overrides },
  } as ListResult
}

function open(url = URL) {
  vi.spyOn(TournamentsService, "readMyTournament").mockResolvedValue({
    data: TOURNAMENT,
  } as ReadResult)
  signInAs({ account: ORGANIZER })
  return renderApp(url)
}

function tableRows() {
  const table = within(
    document.querySelector("[data-slot=data-table]") as HTMLElement,
  ).getByRole("table", { name: "操作紀錄" })
  return within(table).getAllByRole("row").slice(1)
}

describe("S34 操作紀錄：畫面", () => {
  it("由新到舊列出操作者、時間、動作與變更內容；system 為「系統自動」，沒有編輯按鈕", async () => {
    const list = vi
      .spyOn(TournamentsService, "listTournamentAuditLog")
      .mockResolvedValue(page([STATUS_CHANGED, entry()]))
    open()

    await screen.findByRole("table", { name: "操作紀錄" })
    expect(list).toHaveBeenCalledWith({
      path: { tournament_id: "t-1" },
      query: { page: 1 },
    })
    const [system, created] = tableRows()
    expect(within(system).getByText(SYSTEM_ACTOR_TEXT)).toBeInTheDocument()
    expect(within(system).getByText("賽事狀態變更")).toBeInTheDocument()
    expect(system).toHaveTextContent("status：upcoming → open")
    expect(within(system).getByText("2026/11/21 14:06:00")).toBeInTheDocument()

    expect(within(created).getByText("主辦小明")).toBeInTheDocument()
    expect(within(created).getByText("建立賽事")).toBeInTheDocument()
    expect(created).toHaveTextContent("name：臺大秋季盃")
    expect(created).toHaveTextContent("capacity：8")

    const main = screen.getByRole("heading", { name: "操作紀錄" })
      .parentElement as HTMLElement
    expect(
      within(main).queryByRole("button", { name: /新增|修改|刪除|編輯/ }),
    ).toBeNull()
  })

  it("側欄「操作紀錄」為目前頁面", async () => {
    vi.spyOn(TournamentsService, "listTournamentAuditLog").mockResolvedValue(
      page([entry()]),
    )
    open()

    const link = await screen.findByRole("link", { name: "操作紀錄" })
    expect(link).toHaveAttribute("href", URL)
    await waitFor(() => expect(link).toHaveAttribute("data-status", "active"))
  })

  it("未知動作顯示原始代碼", async () => {
    vi.spyOn(TournamentsService, "listTournamentAuditLog").mockResolvedValue(
      page([entry({ action: "future.thing" })]),
    )
    open()

    await screen.findByRole("table", { name: "操作紀錄" })
    expect(within(tableRows()[0]).getByText("future.thing")).toBeInTheDocument()
  })

  it("沒有紀錄：空狀態", async () => {
    vi.spyOn(TournamentsService, "listTournamentAuditLog").mockResolvedValue(
      page([]),
    )
    open()

    expect(await screen.findByText(AUDIT_LOG_EMPTY_TEXT)).toBeInTheDocument()
  })

  it("換頁時頁碼寫在網址", async () => {
    const user = userEvent.setup()
    const many = Array.from({ length: 20 }, (_, i) =>
      entry({ id: `a-${i}`, action: `x.${i}` }),
    )
    vi.spyOn(TournamentsService, "listTournamentAuditLog").mockImplementation(
      (async (options: { query?: { page?: number } }) =>
        options.query?.page === 2
          ? page([entry({ id: "last", action: "x.last" })], {
              total: 21,
              page: 2,
            })
          : page(many, { total: 21 })) as never,
    )
    const router = open()

    await screen.findAllByText("x.19")
    expect(tableRows()).toHaveLength(20)
    await user.click(screen.getByRole("button", { name: "下一頁" }))
    await screen.findAllByText("x.last")
    expect(router.state.location.search).toEqual({ page: 2 })
  })

  it("網址頁碼超出：以 replace 導回最後一頁", async () => {
    vi.spyOn(TournamentsService, "listTournamentAuditLog").mockImplementation(
      (async (options: { query?: { page?: number } }) =>
        options.query?.page === 99
          ? page([], { total: 21, page: 99 })
          : page([entry({ id: "last", action: "x.last" })], {
              total: 21,
              page: 2,
            })) as never,
    )
    const router = open(`${URL}?page=99`)

    await waitFor(() =>
      expect(router.state.location.search).toEqual({ page: 2 }),
    )
    expect(await screen.findAllByText("x.last")).not.toHaveLength(0)
    expect(screen.queryByText(AUDIT_LOG_EMPTY_TEXT)).toBeNull()
    // replace：歷史紀錄裡沒有留下 page=99
    expect(router.history.length).toBe(1)
  })

  it("載入失敗：顯示錯誤，按重新載入會重抓", async () => {
    const user = userEvent.setup()
    const list = vi
      .spyOn(TournamentsService, "listTournamentAuditLog")
      .mockRejectedValueOnce(
        httpError(400, { detail: { code: "X", message: "壞掉了" } }),
      )
      .mockResolvedValue(page([entry()]))
    open()

    expect(await screen.findByText("壞掉了")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "重新載入" }))
    await screen.findAllByText("主辦小明")
    expect(list).toHaveBeenCalledTimes(2)
  })

  it("別人的賽事（403）：顯示無權限畫面", async () => {
    vi.spyOn(TournamentsService, "listTournamentAuditLog").mockRejectedValue(
      httpError(403, {
        detail: { code: "TOURNAMENT_OWNER_REQUIRED", message: "不是你的賽事" },
      }),
    )
    open()

    expect(
      await screen.findByRole("heading", { name: FORBIDDEN_FALLBACK_MESSAGE }),
    ).toBeInTheDocument()
  })
})

describe("S34 操作紀錄：差異計算與格式", () => {
  it("新增類列出 after 的全部欄位", () => {
    expect(auditChanges(null, { a: 1, b: "x" })).toEqual([
      { field: "a", after: 1 },
      { field: "b", after: "x" },
    ])
  })

  it("刪除類列出 before 的全部欄位", () => {
    expect(auditChanges({ a: 1 }, null)).toEqual([{ field: "a", before: 1 }])
  })

  it("修改類只列出值不同的欄位，物件鍵順序不影響比較", () => {
    expect(
      auditChanges(
        { status: "upcoming", same: 1, nested: { x: 1, y: 2 }, gone: true },
        { status: "open", same: 1, nested: { y: 2, x: 1 }, added: [1] },
      ),
    ).toEqual([
      { field: "status", before: "upcoming", after: "open" },
      { field: "added", after: [1] },
      { field: "gone", before: true },
    ])
  })

  it("兩邊都沒有：空陣列", () => {
    expect(auditChanges(null, null)).toEqual([])
  })

  it("值的格式：字串原文，其他以 JSON，缺少以「—」", () => {
    expect(formatAuditValue("abc")).toBe("abc")
    expect(formatAuditValue(null)).toBe("null")
    expect(formatAuditValue({ a: [1, 2] })).toBe('{"a":[1,2]}')
    expect(formatAuditValue(undefined)).toBe("—")
  })

  it("時間以台北時間顯示到秒；格式錯誤回空字串", () => {
    expect(formatAuditTime("2026-11-21T06:05:09Z")).toBe("2026/11/21 14:05:09")
    expect(formatAuditTime("2026-12-31T16:00:00Z")).toBe("2027/01/01 00:00:00")
    expect(formatAuditTime("bad")).toBe("")
  })

  it("動作對照表；未知代碼與原型鏈上的名稱顯示原文", () => {
    expect(auditActionLabel("tournament.created")).toBe("建立賽事")
    expect(auditActionLabel("tournament.status_changed")).toBe("賽事狀態變更")
    expect(auditActionLabel("unknown.action")).toBe("unknown.action")
    expect(auditActionLabel("toString")).toBe("toString")
  })
})
