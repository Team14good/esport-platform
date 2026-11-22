import { type ReactNode, useEffect } from "react"

import type { AuditLogEntry } from "@/client"
import { DataTable, type DataTableColumn } from "@/components/common/DataTable"
import { EmptyState } from "@/components/common/EmptyState"
import { ErrorPage } from "@/components/layout/ErrorPage"
import { Button } from "@/components/ui/button"
import { getErrorMessage, parseApiError } from "@/lib/api-error"
import {
  AUDIT_LOG_EMPTY_TEXT,
  auditActionLabel,
  auditActorLabel,
  auditChanges,
  formatAuditTime,
  formatAuditValue,
  useAuditLog,
} from "./audit-log"

export const AUDIT_LOG_TITLE = "操作紀錄"
const PAGE_SIZE = 20

/** 變更內容：欄位名稱照原始資料（等寬字）；修改類寫「欄位：前 → 後」。 */
function ChangesCell({ entry }: { entry: AuditLogEntry }) {
  const changes = auditChanges(entry.before, entry.after)
  if (changes.length === 0) {
    return <span className="text-muted-foreground">—</span>
  }
  const both = Boolean(entry.before) && Boolean(entry.after)
  return (
    <ul className="flex min-w-0 flex-col gap-1 text-caption">
      {changes.map((change) => (
        <li key={change.field} className="break-all">
          <span className="font-mono">{change.field}</span>：
          {both ? (
            <>
              <span className="font-mono">
                {formatAuditValue(change.before)}
              </span>
              {" → "}
              <span className="font-mono">
                {formatAuditValue(change.after)}
              </span>
            </>
          ) : (
            <span className="font-mono">
              {formatAuditValue(
                "after" in change ? change.after : change.before,
              )}
            </span>
          )}
        </li>
      ))}
    </ul>
  )
}

const COLUMNS: DataTableColumn<AuditLogEntry>[] = [
  {
    key: "at",
    header: "時間",
    cell: (entry) => (
      <time dateTime={entry.at} className="whitespace-nowrap font-mono">
        {formatAuditTime(entry.at)}
      </time>
    ),
  },
  {
    key: "actor",
    header: "操作者",
    cell: (entry) => (
      <span
        className={
          entry.actor_id ? "break-words" : "break-words text-muted-foreground"
        }
      >
        {auditActorLabel(entry)}
      </span>
    ),
  },
  {
    key: "action",
    header: "動作",
    cell: (entry) => (
      <span className="font-medium sm:whitespace-nowrap">
        {auditActionLabel(entry.action)}
      </span>
    ),
  },
  {
    key: "changes",
    header: "變更內容",
    cell: (entry) => <ChangesCell entry={entry} />,
  },
]

type AuditLogPageProps = {
  tournamentId: string
  page: number
  /** 換頁：寫入網址；`replace` 用於頁碼超出時修正網址 */
  onPageChange: (page: number, replace?: boolean) => void
}

/** S34 操作紀錄（主辦方賽事後台，唯讀）：由新到舊列出操作者、時間、動作與變更內容。 */
export function AuditLogPage({
  tournamentId,
  page,
  onPageChange,
}: AuditLogPageProps) {
  const log = useAuditLog(tournamentId, page)
  const data = log.data
  // 換頁期間（keepPreviousData）的資料是上一頁的，不能拿來判斷頁碼是否超出
  const settled = data && !log.isPlaceholderData ? data : undefined

  // 頁碼超出（網址手動輸入）：換到最後一頁
  useEffect(() => {
    if (!settled || settled.items.length > 0 || page <= 1) return
    const lastPage = Math.max(1, Math.ceil(settled.total / settled.page_size))
    if (page > lastPage) onPageChange(lastPage, true)
  }, [settled, page, onPageChange])

  let body: ReactNode
  if (log.isError && !data) {
    if (parseApiError(log.error).kind === "forbidden") {
      return <ErrorPage status={403} />
    }
    body = (
      <div className="flex flex-col items-start gap-3">
        <p className="text-body text-destructive">
          {getErrorMessage(parseApiError(log.error))}
        </p>
        <Button variant="outline" onClick={() => log.refetch()}>
          重新載入
        </Button>
      </div>
    )
  } else {
    body = (
      <DataTable
        label={AUDIT_LOG_TITLE}
        columns={COLUMNS}
        // 頁碼超出、正在導回最後一頁時先顯示 Skeleton，不顯示空狀態
        rows={
          data && data.items.length === 0 && data.total > 0
            ? undefined
            : data?.items
        }
        getRowId={(entry) => entry.id}
        page={page}
        pageSize={data?.page_size ?? PAGE_SIZE}
        total={data?.total ?? 0}
        onPageChange={(next) => onPageChange(next)}
        empty={<EmptyState title={AUDIT_LOG_EMPTY_TEXT} />}
      />
    )
  }

  return (
    <section className="flex min-w-0 flex-col gap-6">
      <h1 className="text-heading-lg">{AUDIT_LOG_TITLE}</h1>
      {body}
    </section>
  )
}
