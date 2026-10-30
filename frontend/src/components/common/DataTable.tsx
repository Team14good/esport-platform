import { ChevronLeftIcon, ChevronRightIcon } from "lucide-react"
import type { ReactNode } from "react"

import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import {
  Pagination,
  PaginationContent,
  PaginationItem,
} from "@/components/ui/pagination"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { cn } from "@/lib/utils"

export type DataTableColumn<Row> = {
  key: string
  /** 欄名；`< md` 的卡片清單也以它當每一項的標籤 */
  header: string
  cell: (row: Row) => ReactNode
  className?: string
}

type DataTableProps<Row> = {
  columns: DataTableColumn<Row>[]
  /** 目前這一頁的資料；首次載入（還沒有資料）時給 undefined，顯示 Skeleton */
  rows: Row[] | undefined
  getRowId: (row: Row) => string
  /** 目前頁碼（從 1 開始） */
  page: number
  pageSize: number
  total: number
  onPageChange: (page: number) => void
  /** 表格上方的工具列（篩選等） */
  toolbar?: ReactNode
  /** 沒有資料時顯示的 Empty state */
  empty: ReactNode
  /** 表格的無障礙名稱 */
  label?: string
}

const SKELETON_ROWS = 3
const PAGE_WINDOW = 1

/** 要顯示的頁碼：首頁、末頁與目前頁前後各一頁，中間以 null（省略號）連接。 */
export function pageNumbers(
  page: number,
  totalPages: number,
): (number | null)[] {
  const pages: (number | null)[] = []
  for (let n = 1; n <= totalPages; n++) {
    const nearCurrent = Math.abs(n - page) <= PAGE_WINDOW
    if (n === 1 || n === totalPages || nearCurrent) {
      pages.push(n)
    } else if (pages[pages.length - 1] !== null) {
      pages.push(null)
    }
  }
  return pages
}

function DataTablePagination({
  page,
  totalPages,
  onPageChange,
}: {
  page: number
  totalPages: number
  onPageChange: (page: number) => void
}) {
  return (
    <Pagination aria-label="分頁" className="justify-end">
      <PaginationContent>
        <PaginationItem>
          <Button
            variant="ghost"
            size="icon"
            aria-label="上一頁"
            disabled={page <= 1}
            onClick={() => onPageChange(page - 1)}
          >
            <ChevronLeftIcon aria-hidden="true" />
          </Button>
        </PaginationItem>
        {/* 375px 放不下整排頁碼：< sm 只寫「第 n／N 頁」 */}
        <PaginationItem className="px-2 text-body text-muted-foreground sm:hidden">
          第 {page}／{totalPages} 頁
        </PaginationItem>
        {pageNumbers(page, totalPages).map((n, index) =>
          n === null ? (
            <PaginationItem
              key={`gap-${index}`}
              aria-hidden="true"
              className="hidden w-9 text-center text-muted-foreground sm:block"
            >
              …
            </PaginationItem>
          ) : (
            <PaginationItem key={n} className="hidden sm:block">
              <Button
                variant={n === page ? "outline" : "ghost"}
                size="icon"
                aria-label={`第 ${n} 頁`}
                aria-current={n === page ? "page" : undefined}
                onClick={() => onPageChange(n)}
              >
                {n}
              </Button>
            </PaginationItem>
          ),
        )}
        <PaginationItem>
          <Button
            variant="ghost"
            size="icon"
            aria-label="下一頁"
            disabled={page >= totalPages}
            onClick={() => onPageChange(page + 1)}
          >
            <ChevronRightIcon aria-hidden="true" />
          </Button>
        </PaginationItem>
      </PaginationContent>
    </Pagination>
  )
}

/**
 * 全站共用的 Data table：每頁 `pageSize` 筆（分頁由呼叫端寫入 URL）；表頭 overline＋
 * muted-foreground；`< md` 每列改成一張卡片（欄名：值）；頁數超過 1 才顯示分頁；
 * 首次載入顯示 Skeleton。
 */
export function DataTable<Row>({
  columns,
  rows,
  getRowId,
  page,
  pageSize,
  total,
  onPageChange,
  toolbar,
  empty,
  label,
}: DataTableProps<Row>) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  let body: ReactNode
  if (rows === undefined) {
    body = (
      <div role="status" aria-busy="true" className="flex flex-col gap-3">
        {Array.from({ length: SKELETON_ROWS }, (_, index) => (
          <Skeleton key={index} className="h-14 w-full" />
        ))}
        <span className="sr-only">載入中</span>
      </div>
    )
  } else if (rows.length === 0) {
    body = empty
  } else {
    body = (
      <>
        <div
          data-slot="data-table"
          className="hidden overflow-hidden rounded-lg border md:block"
        >
          <Table aria-label={label}>
            <TableHeader>
              <TableRow>
                {columns.map((column) => (
                  <TableHead
                    key={column.key}
                    className={cn(
                      "text-overline tracking-normal text-muted-foreground",
                      column.className,
                    )}
                  >
                    {column.header}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={getRowId(row)}>
                  {columns.map((column) => (
                    <TableCell
                      key={column.key}
                      className={cn("whitespace-normal", column.className)}
                    >
                      {column.cell(row)}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
        <ul
          data-slot="data-table-cards"
          aria-label={label}
          className="flex flex-col gap-3 md:hidden"
        >
          {rows.map((row) => (
            <li key={getRowId(row)}>
              <Card className="gap-0 px-4 py-3">
                <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-2 text-body">
                  {columns.map((column) => (
                    <div key={column.key} className="contents">
                      <dt className="text-muted-foreground">{column.header}</dt>
                      <dd className="min-w-0 break-words">
                        {column.cell(row)}
                      </dd>
                    </div>
                  ))}
                </dl>
              </Card>
            </li>
          ))}
        </ul>
      </>
    )
  }

  return (
    <div className="flex min-w-0 flex-col gap-4">
      {toolbar}
      {body}
      {rows !== undefined && totalPages > 1 && (
        <DataTablePagination
          page={page}
          totalPages={totalPages}
          onPageChange={onPageChange}
        />
      )}
    </div>
  )
}
