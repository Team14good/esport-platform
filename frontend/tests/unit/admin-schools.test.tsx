import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  act,
  renderHook,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { ReactNode } from "react"
import { toast } from "sonner"
import { describe, expect, it, vi } from "vitest"

import { IdentityService, type PublicSchool } from "@/client"
import {
  filterSchools,
  SCHOOLS_EMPTY_TEXT,
  SCHOOLS_FILTERED_EMPTY_TEXT,
} from "@/features/identity/AdminSchoolsPage"
import {
  SCHOOL_CREATED_TOAST_TEXT,
  SCHOOL_RENAMED_TOAST_TEXT,
  SCHOOLS_QUERY_KEY,
} from "@/features/identity/admin-schools"
import { useSchools } from "@/features/identity/schools"
import { FORBIDDEN_FALLBACK_MESSAGE } from "@/lib/api-error"
import { ACCOUNT, renderApp, signInAs } from "./auth-fixtures"
import { httpError } from "./helpers"

vi.mock("@tanstack/react-router-devtools", () => ({
  TanStackRouterDevtools: () => null,
}))
vi.mock("@tanstack/react-query-devtools", () => ({
  ReactQueryDevtools: () => null,
}))

type ListResult = Awaited<ReturnType<typeof IdentityService.listSchools>>
type CreateResult = Awaited<ReturnType<typeof IdentityService.createSchool>>
type RenameResult = Awaited<ReturnType<typeof IdentityService.renameSchool>>

const ADMIN = { ...ACCOUNT, is_platform_admin: true }

const NTU: PublicSchool = { id: "school-ntu", name: "國立臺灣大學" }
const NTHU: PublicSchool = { id: "school-nthu", name: "國立清華大學" }
const NCKU: PublicSchool = { id: "school-ncku", name: "國立成功大學" }

function listResult(schools: PublicSchool[]): ListResult {
  return { data: schools } as ListResult
}

function mockList(schools: PublicSchool[] = [NCKU, NTHU, NTU]) {
  return vi
    .spyOn(IdentityService, "listSchools")
    .mockResolvedValue(listResult(schools))
}

function tableArea(): HTMLElement {
  return document.querySelector("[data-slot=data-table]") as HTMLElement
}

function cardArea(): HTMLElement {
  return document.querySelector("[data-slot=data-table-cards]") as HTMLElement
}

describe("S36 學校清單", () => {
  it("篩選：去除前後空白、不分大小寫的部分比對", () => {
    const schools = [NTU, { id: "s-x", name: "Example University" }]
    expect(filterSchools(schools, "  ")).toEqual(schools)
    expect(filterSchools(schools, " 臺灣 ")).toEqual([NTU])
    expect(filterSchools(schools, "example")).toEqual([schools[1]])
  })

  it("不是平台管理員：顯示 S38 的 403", async () => {
    mockList()
    signInAs()
    renderApp("/admin/schools")

    expect(
      await screen.findByRole("heading", { name: FORBIDDEN_FALLBACK_MESSAGE }),
    ).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "新增學校" })).toBeNull()
  })

  it("依名稱列出（沿用後端排序），每列有「修正名稱」；< md 改成卡片", async () => {
    mockList()
    signInAs({ account: ADMIN })
    renderApp("/admin/schools")

    const table = await screen.findByRole("table", { name: "學校" })
    expect(
      within(table)
        .getAllByRole("columnheader")
        .map((header) => header.textContent),
    ).toEqual(["學校名稱", "操作"])
    const rows = within(table).getAllByRole("row").slice(1)
    expect(
      rows.map((row) => within(row).getAllByRole("cell")[0].textContent),
    ).toEqual(["國立成功大學", "國立清華大學", "國立臺灣大學"])
    expect(
      within(rows[0]).getByRole("button", { name: "修正名稱" }),
    ).toBeInTheDocument()
    // jsdom 不排版：卡片清單只在 < md（375 px）顯示
    expect(tableArea()).toHaveClass("hidden", "md:block")
    expect(cardArea()).toHaveClass("md:hidden")
    expect(within(cardArea()).getAllByRole("listitem")).toHaveLength(3)
  })

  it("關鍵字篩選；沒有符合的學校顯示 Empty state", async () => {
    const user = userEvent.setup()
    mockList()
    signInAs({ account: ADMIN })
    renderApp("/admin/schools")

    const table = await screen.findByRole("table", { name: "學校" })
    await user.type(screen.getByLabelText("搜尋學校"), "清華")
    expect(within(table).getAllByRole("row")).toHaveLength(2)
    expect(within(table).getByText("國立清華大學")).toBeInTheDocument()

    await user.clear(screen.getByLabelText("搜尋學校"))
    await user.type(screen.getByLabelText("搜尋學校"), "不存在")
    expect(
      await screen.findByText(SCHOOLS_FILTERED_EMPTY_TEXT),
    ).toBeInTheDocument()
  })

  it("每頁 20 筆；換頁後再篩選回到第 1 頁", async () => {
    const user = userEvent.setup()
    const schools = Array.from({ length: 25 }, (_, index) => ({
      id: `s-${index}`,
      name: `學校 ${String(index).padStart(2, "0")}`,
    }))
    mockList(schools)
    signInAs({ account: ADMIN })
    renderApp("/admin/schools")

    const table = await screen.findByRole("table", { name: "學校" })
    expect(within(table).getAllByRole("row")).toHaveLength(21)
    await user.click(screen.getByRole("button", { name: "下一頁" }))
    await waitFor(() =>
      expect(within(table).getAllByRole("row")).toHaveLength(6),
    )

    await user.type(screen.getByLabelText("搜尋學校"), "學校 0")
    await waitFor(() =>
      expect(within(table).getAllByRole("row")).toHaveLength(11),
    )
    expect(screen.queryByRole("navigation", { name: "分頁" })).toBeNull()
  })

  it("沒有學校：Empty state", async () => {
    mockList([])
    signInAs({ account: ADMIN })
    renderApp("/admin/schools")

    expect(await screen.findByText(SCHOOLS_EMPTY_TEXT)).toBeInTheDocument()
  })

  it("讀取失敗：顯示錯誤與「重新載入」", async () => {
    const user = userEvent.setup()
    const list = vi
      .spyOn(IdentityService, "listSchools")
      .mockRejectedValueOnce(httpError(500, {}))
      .mockResolvedValue(listResult([NTU]))
    signInAs({ account: ADMIN })
    renderApp("/admin/schools")

    expect(await screen.findByText("伺服器發生錯誤（500）")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "重新載入" }))

    expect(
      await screen.findByRole("table", { name: "學校" }),
    ).toBeInTheDocument()
    expect(list).toHaveBeenCalledTimes(2)
  })

  it("新增學校：Dialog 送出去除前後空白的名稱，Toast 後重抓學校清單（學校選單共用同一個查詢）", async () => {
    const user = userEvent.setup()
    const success = vi.spyOn(toast, "success")
    const NCCU: PublicSchool = { id: "school-nccu", name: "國立政治大學" }
    const list = vi
      .spyOn(IdentityService, "listSchools")
      .mockResolvedValueOnce(listResult([NTU]))
      .mockResolvedValue(listResult([NCCU, NTU]))
    const create = vi
      .spyOn(IdentityService, "createSchool")
      .mockResolvedValue({ data: NCCU } as CreateResult)
    signInAs({ account: ADMIN })
    renderApp("/admin/schools")

    const table = await screen.findByRole("table", { name: "學校" })
    await user.click(screen.getByRole("button", { name: "新增學校" }))
    const dialog = await screen.findByRole("dialog", { name: "新增學校" })
    await user.type(
      within(dialog).getByLabelText("學校名稱"),
      "  國立政治大學 ",
    )
    await user.click(within(dialog).getByRole("button", { name: "新增學校" }))

    expect(create).toHaveBeenCalledWith({ body: { name: "國立政治大學" } })
    await waitFor(() =>
      expect(success).toHaveBeenCalledWith(SCHOOL_CREATED_TOAST_TEXT, {
        duration: 3000,
      }),
    )
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull())
    expect(await within(table).findByText("國立政治大學")).toBeInTheDocument()
    expect(list).toHaveBeenCalledTimes(2)
  })

  it("新增學校：空白名稱不送出；名稱重複（409）顯示在欄位下方，Dialog 不關", async () => {
    const user = userEvent.setup()
    mockList()
    const create = vi.spyOn(IdentityService, "createSchool").mockRejectedValue(
      httpError(409, {
        detail: { code: "SCHOOL_NAME_TAKEN", message: "學校名稱已存在。" },
      }),
    )
    signInAs({ account: ADMIN })
    renderApp("/admin/schools")

    await screen.findByRole("table", { name: "學校" })
    await user.click(screen.getByRole("button", { name: "新增學校" }))
    const dialog = await screen.findByRole("dialog", { name: "新增學校" })
    await user.click(within(dialog).getByRole("button", { name: "新增學校" }))
    expect(
      await within(dialog).findByText("請輸入學校名稱"),
    ).toBeInTheDocument()
    expect(create).not.toHaveBeenCalled()

    await user.type(within(dialog).getByLabelText("學校名稱"), "國立臺灣大學")
    await user.click(within(dialog).getByRole("button", { name: "新增學校" }))

    const input = within(dialog).getByLabelText("學校名稱")
    expect(await within(dialog).findByText("學校名稱已存在。")).toHaveAttribute(
      "id",
      input.getAttribute("aria-describedby")?.split(" ")[1],
    )
    expect(input).toHaveValue("國立臺灣大學")
    expect(screen.getByRole("dialog")).toBeInTheDocument()
  })

  it("修正名稱：Dialog 預填原名，送出後 Toast 並重抓學校清單", async () => {
    const user = userEvent.setup()
    const success = vi.spyOn(toast, "success")
    const list = vi
      .spyOn(IdentityService, "listSchools")
      .mockResolvedValueOnce(listResult([NTU]))
      .mockResolvedValue(
        listResult([{ ...NTU, name: "國立臺灣大學（總校區）" }]),
      )
    const rename = vi.spyOn(IdentityService, "renameSchool").mockResolvedValue({
      data: { ...NTU, name: "國立臺灣大學（總校區）" },
    } as RenameResult)
    signInAs({ account: ADMIN })
    renderApp("/admin/schools")

    const table = await screen.findByRole("table", { name: "學校" })
    await user.click(within(table).getByRole("button", { name: "修正名稱" }))
    const dialog = await screen.findByRole("dialog", { name: "修正學校名稱" })
    const input = within(dialog).getByLabelText("學校名稱")
    expect(input).toHaveValue("國立臺灣大學")
    await user.type(input, "（總校區）")
    await user.click(within(dialog).getByRole("button", { name: "修正名稱" }))

    expect(rename).toHaveBeenCalledWith({
      path: { school_id: "school-ntu" },
      body: { name: "國立臺灣大學（總校區）" },
    })
    await waitFor(() =>
      expect(success).toHaveBeenCalledWith(SCHOOL_RENAMED_TOAST_TEXT, {
        duration: 3000,
      }),
    )
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull())
    expect(
      await within(table).findByText("國立臺灣大學（總校區）"),
    ).toBeInTheDocument()
    expect(list).toHaveBeenCalledTimes(2)
  })

  it("修正名稱：名稱重複（409）顯示在欄位下方", async () => {
    const user = userEvent.setup()
    mockList()
    vi.spyOn(IdentityService, "renameSchool").mockRejectedValue(
      httpError(409, {
        detail: { code: "SCHOOL_NAME_TAKEN", message: "學校名稱已存在。" },
      }),
    )
    signInAs({ account: ADMIN })
    renderApp("/admin/schools")

    const table = await screen.findByRole("table", { name: "學校" })
    await user.click(
      within(table).getAllByRole("button", { name: "修正名稱" })[0],
    )
    const dialog = await screen.findByRole("dialog", { name: "修正學校名稱" })
    const input = within(dialog).getByLabelText("學校名稱")
    await user.clear(input)
    await user.type(input, "國立臺灣大學")
    await user.click(within(dialog).getByRole("button", { name: "修正名稱" }))

    expect(
      await within(dialog).findByText("學校名稱已存在。"),
    ).toBeInTheDocument()
    expect(within(dialog).queryByRole("alert")).toBeNull()
  })
})

describe("S36 學校清單：錯誤與快取", () => {
  it("新增學校的其他錯誤（500）：Dialog 內顯示錯誤，Dialog 不關", async () => {
    const user = userEvent.setup()
    mockList()
    vi.spyOn(IdentityService, "createSchool").mockRejectedValue(
      httpError(500, {}),
    )
    signInAs({ account: ADMIN })
    renderApp("/admin/schools")

    await screen.findByRole("table", { name: "學校" })
    await user.click(screen.getByRole("button", { name: "新增學校" }))
    const dialog = await screen.findByRole("dialog", { name: "新增學校" })
    await user.type(within(dialog).getByLabelText("學校名稱"), "國立政治大學")
    await user.click(within(dialog).getByRole("button", { name: "新增學校" }))

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "伺服器發生錯誤（500）",
    )
    expect(screen.getByRole("dialog")).toBeInTheDocument()
  })

  it("SCHOOLS_QUERY_KEY 與 useSchools() 的 key 相同：失效後學校選單會重抓", async () => {
    const list = mockList()
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    const { result } = renderHook(() => useSchools(), {
      wrapper: ({ children }: { children: ReactNode }) => (
        <QueryClientProvider client={queryClient}>
          {children}
        </QueryClientProvider>
      ),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(list).toHaveBeenCalledTimes(1)
    await act(() =>
      queryClient.invalidateQueries({ queryKey: SCHOOLS_QUERY_KEY }),
    )
    expect(list).toHaveBeenCalledTimes(2)
  })
})
