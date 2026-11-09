import { useQuery } from "@tanstack/react-query"
import { type ReactNode, useState } from "react"

import { DisputesService, type ReportRead } from "@/client"
import { DataTable, type DataTableColumn } from "@/components/common/DataTable"
import { EmptyState } from "@/components/common/EmptyState"
import { StatusBadge, type StatusTone } from "@/components/common/StatusBadge"
import { ErrorPage } from "@/components/layout/ErrorPage"
import { Button } from "@/components/ui/button"
import { formatMatchDateTime } from "@/features/competition/match-time"
import { myTournamentQueryOptions } from "@/features/tournaments/organizer-queries"
import { getErrorMessage, parseApiError } from "@/lib/api-error"
import { openAttachment } from "./open-attachment"
import { tournamentReportsQueryOptions } from "./organizer-queries"
import {
  DismissReportDialog,
  SubstantiateReportDialog,
} from "./ResolveReportDialogs"

export const REPORTS_PAGE_SIZE = 20
export const NO_OPEN_REPORTS_TEXT = "目前沒有待處理的檢舉。"
export const VIEW_REPORT_ATTACHMENT_TEXT = "查看附件"

/** 檢舉狀態的徽章文字與色調。 */
export const REPORT_STATUS: Record<
  ReportRead["status"],
  { label: string; tone: StatusTone }
> = {
  open: { label: "待處理", tone: "appeal" },
  dismissed: { label: "已駁回", tone: "muted" },
  substantiated: { label: "屬實", tone: "destructive" },
}

// 賽事已結束或已取消時，屬實只記錄、不取消資格
const ENDED_STATUSES = new Set(["finished", "cancelled"])

/** 檢舉附件：以登入者的權杖下載後於新分頁開啟。 */
function openReportAttachment(reportId: string) {
  return openAttachment(() =>
    DisputesService.downloadReportAttachment({
      path: { report_id: reportId },
    }),
  )
}

function StatusCell({ report }: { report: ReportRead }) {
  const status = REPORT_STATUS[report.status]
  return (
    <div className="flex flex-col gap-1">
      <StatusBadge tone={status.tone} pulse={report.status === "open"}>
        {status.label}
      </StatusBadge>
      {report.reason && (
        <p className="whitespace-pre-wrap break-words text-caption text-muted-foreground">
          處理理由：{report.reason}
        </p>
      )}
    </div>
  )
}

function buildColumns(
  tournamentId: string,
  tournamentEnded: boolean | null,
): DataTableColumn<ReportRead>[] {
  return [
    {
      key: "reporter",
      header: "檢舉人隊伍",
      cell: (report) => (
        <span className="break-words">{report.reporter_team_name}</span>
      ),
    },
    {
      key: "reported",
      header: "被檢舉隊伍",
      cell: (report) => (
        <span className="break-words font-medium">
          {report.reported_team_name}
        </span>
      ),
    },
    {
      key: "description",
      header: "說明",
      cell: (report) => (
        <p className="whitespace-pre-wrap break-words">{report.description}</p>
      ),
    },
    {
      key: "attachment",
      header: "附件",
      cell: (report) =>
        report.has_attachment ? (
          <Button
            variant="outline"
            size="sm"
            onClick={() => void openReportAttachment(report.id)}
          >
            {VIEW_REPORT_ATTACHMENT_TEXT}
          </Button>
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
    },
    {
      key: "filed_at",
      header: "提出時間",
      cell: (report) => (
        <time dateTime={report.filed_at} className="whitespace-nowrap">
          {formatMatchDateTime(report.filed_at)}
        </time>
      ),
    },
    {
      key: "status",
      header: "狀態",
      cell: (report) => <StatusCell report={report} />,
    },
    {
      key: "actions",
      header: "操作",
      cell: (report) =>
        report.status === "open" ? (
          <div className="flex flex-col items-start gap-2">
            <DismissReportDialog tournamentId={tournamentId} report={report} />
            <SubstantiateReportDialog
              tournamentId={tournamentId}
              report={report}
              tournamentEnded={tournamentEnded}
            />
          </div>
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
    },
  ]
}

/**
 * S33 檢舉（主辦方賽事後台）：Data table 列出檢舉，可查看附件；未結案的檢舉可
 * 「駁回檢舉」或「取消資格」（賽事已結束或已取消時改為「記錄屬實」）。
 */
export function ReportsPage({ tournamentId }: { tournamentId: string }) {
  const reports = useQuery(tournamentReportsQueryOptions(tournamentId))
  // 與賽事後台版面同一個 query（已在快取），用來判斷賽事是否已結束
  const tournament = useQuery(myTournamentQueryOptions(tournamentId))
  const [page, setPage] = useState(1)

  if (reports.isError && !reports.data) {
    if (parseApiError(reports.error).kind === "forbidden") {
      return <ErrorPage status={403} />
    }
  }

  // 賽事狀態未知（載入中或失敗）時不能判斷要取消資格還是只記錄屬實：屬實按鈕停用
  const tournamentEnded = tournament.data
    ? ENDED_STATUSES.has(tournament.data.status)
    : null
  const list = reports.data
  const total = list?.length ?? 0
  const lastPage = Math.max(1, Math.ceil(total / REPORTS_PAGE_SIZE))
  const current = Math.min(page, lastPage)
  const start = (current - 1) * REPORTS_PAGE_SIZE
  const rows = list?.slice(start, start + REPORTS_PAGE_SIZE)
  const hasOpen = list?.some((report) => report.status === "open") ?? false

  let body: ReactNode
  if (reports.isError && !list) {
    body = (
      <div className="flex flex-col items-start gap-3">
        <p className="text-body text-destructive">
          {getErrorMessage(parseApiError(reports.error))}
        </p>
        <Button variant="outline" onClick={() => reports.refetch()}>
          重新載入
        </Button>
      </div>
    )
  } else {
    body = (
      <>
        {list && list.length > 0 && !hasOpen && (
          <p className="text-body text-muted-foreground">
            {NO_OPEN_REPORTS_TEXT}
          </p>
        )}
        <DataTable
          label="檢舉"
          columns={buildColumns(tournamentId, tournamentEnded)}
          rows={rows}
          getRowId={(report) => report.id}
          page={current}
          pageSize={REPORTS_PAGE_SIZE}
          total={total}
          onPageChange={setPage}
          empty={<EmptyState title={NO_OPEN_REPORTS_TEXT} />}
        />
      </>
    )
  }

  return (
    <section className="flex min-w-0 flex-col gap-6">
      <h1 className="text-heading-lg">檢舉</h1>
      {body}
    </section>
  )
}
