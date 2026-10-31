import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import {
  DataTable,
  type DataTableColumn,
  pageNumbers,
} from "@/components/common/DataTable"

type Row = { id: string; name: string; school: string }

const COLUMNS: DataTableColumn<Row>[] = [
  { key: "name", header: "社團名稱", cell: (row) => row.name },
  { key: "school", header: "學校", cell: (row) => row.school },
]

const ROWS: Row[] = [
  { id: "a", name: "臺大電競社", school: "國立臺灣大學" },
  { id: "b", name: "清大電競社", school: "國立清華大學" },
]

function renderTable(
  props: Partial<React.ComponentProps<typeof DataTable<Row>>> = {},
) {
  const onPageChange = vi.fn()
  const view = render(
    <DataTable<Row>
      label="主辦方申請"
      columns={COLUMNS}
      rows={ROWS}
      getRowId={(row) => row.id}
      page={1}
      pageSize={20}
      total={ROWS.length}
      onPageChange={onPageChange}
      toolbar={<div>工具列</div>}
      empty={<p>目前沒有資料。</p>}
      {...props}
    />,
  )
  return { ...view, onPageChange }
}

describe("pageNumbers", () => {
  it("頁數少時全部列出", () => {
    expect(pageNumbers(1, 3)).toEqual([1, 2, 3])
  })

  it("頁數多時保留首末頁與目前頁前後各一頁，中間以省略號連接", () => {
    expect(pageNumbers(5, 10)).toEqual([1, null, 4, 5, 6, null, 10])
    expect(pageNumbers(1, 10)).toEqual([1, 2, null, 10])
    expect(pageNumbers(10, 10)).toEqual([1, null, 9, 10])
  })
})

describe("DataTable", () => {
  it("表頭用 overline＋muted-foreground，每列一行", () => {
    const { container } = renderTable()

    const table = within(
      container.querySelector("[data-slot=data-table]") as HTMLElement,
    ).getByRole("table", { name: "主辦方申請" })
    const headers = within(table).getAllByRole("columnheader")
    expect(headers.map((header) => header.textContent)).toEqual([
      "社團名稱",
      "學校",
    ])
    for (const header of headers) {
      expect(header).toHaveClass("text-overline", "text-muted-foreground")
    }
    const rows = within(table).getAllByRole("row").slice(1)
    expect(rows.map((row) => row.textContent)).toEqual([
      "臺大電競社國立臺灣大學",
      "清大電競社國立清華大學",
    ])
    expect(screen.getByText("工具列")).toBeInTheDocument()
  })

  it("< md：每列改成一張卡片（欄名：值），表格只在 md 以上顯示", () => {
    const { container } = renderTable()

    expect(container.querySelector("[data-slot=data-table]")).toHaveClass(
      "hidden",
      "md:block",
    )
    const cards = container.querySelector(
      "[data-slot=data-table-cards]",
    ) as HTMLElement
    expect(cards).toHaveClass("md:hidden")
    const items = within(cards).getAllByRole("listitem")
    expect(items).toHaveLength(2)
    const terms = within(items[0])
      .getAllByRole("term")
      .map((term) => term.textContent)
    const values = within(items[0])
      .getAllByRole("definition")
      .map((value) => value.textContent)
    expect(terms).toEqual(["社團名稱", "學校"])
    expect(values).toEqual(["臺大電競社", "國立臺灣大學"])
  })

  it("首次載入（rows 為 undefined）：顯示 Skeleton，不顯示分頁", () => {
    renderTable({ rows: undefined, total: 100 })

    expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true")
    expect(screen.queryByRole("table")).toBeNull()
    expect(screen.queryByRole("navigation", { name: "分頁" })).toBeNull()
  })

  it("沒有資料：顯示 empty", () => {
    renderTable({ rows: [], total: 0 })

    expect(screen.getByText("目前沒有資料。")).toBeInTheDocument()
    expect(screen.queryByRole("table")).toBeNull()
  })

  it("只有一頁時不顯示分頁", () => {
    renderTable({ total: 20 })

    expect(screen.queryByRole("navigation", { name: "分頁" })).toBeNull()
  })

  it("超過一頁：顯示分頁，上一頁、下一頁、頁碼都呼叫 onPageChange", async () => {
    const user = userEvent.setup()
    const { onPageChange } = renderTable({ page: 2, total: 45 })

    const nav = screen.getByRole("navigation", { name: "分頁" })
    expect(within(nav).getByText("第 2／3 頁")).toHaveClass("sm:hidden")
    expect(
      within(nav).getByRole("button", { name: "第 2 頁" }),
    ).toHaveAttribute("aria-current", "page")

    await user.click(within(nav).getByRole("button", { name: "下一頁" }))
    await user.click(within(nav).getByRole("button", { name: "上一頁" }))
    await user.click(within(nav).getByRole("button", { name: "第 3 頁" }))

    expect(onPageChange.mock.calls).toEqual([[3], [1], [3]])
  })

  it("第一頁停用上一頁、最後一頁停用下一頁", () => {
    const { rerender } = renderTable({ page: 1, total: 45 })
    expect(screen.getByRole("button", { name: "上一頁" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "下一頁" })).toBeEnabled()

    rerender(
      <DataTable<Row>
        columns={COLUMNS}
        rows={ROWS}
        getRowId={(row) => row.id}
        page={3}
        pageSize={20}
        total={45}
        onPageChange={() => {}}
        empty={null}
      />,
    )
    expect(screen.getByRole("button", { name: "下一頁" })).toBeDisabled()
  })
})
