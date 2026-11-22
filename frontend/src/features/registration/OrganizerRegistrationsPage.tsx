import { useQuery } from "@tanstack/react-query"
import { type ReactNode, useEffect, useId, useState } from "react"
import { toast } from "sonner"

import type { OrganizerRegistration } from "@/client"
import { ConfirmDialog } from "@/components/common/ConfirmDialog"
import { DataTable, type DataTableColumn } from "@/components/common/DataTable"
import { EmptyState } from "@/components/common/EmptyState"
import { ErrorPage } from "@/components/layout/ErrorPage"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { myTournamentQueryOptions } from "@/features/tournaments/organizer-queries"
import { getErrorMessage, parseApiError } from "@/lib/api-error"
import { formatDateTime } from "@/lib/datetime"
import { notifySuccess } from "@/lib/feedback"
import { COPIED_TEXT, COPY_FAILED_TEXT } from "./InviteLinkField"
import {
  COPY_TOURNAMENT_LINK_TEXT,
  DEFAULT_REGISTRATION_FILTER,
  FILTERED_EMPTY_TEXT,
  NO_REGISTRATIONS_TEXT,
  ORGANIZER_REGISTRATIONS_TITLE,
  type OrganizerRegistrationsSearch,
  RANK_SCREENSHOT_TEXT,
  REGISTRATION_FILTERS,
  REJECT_REASON_LABEL,
  REJECT_REASON_MAX_LENGTH,
  REJECT_TEXT,
  type RegistrationFilter,
  rejectDescription,
  tournamentPageUrl,
  useOrganizerRegistrations,
  useRejectRegistration,
} from "./organizer-registrations"
import { RankScreenshotViewer } from "./RankScreenshotViewer"
import {
  REJECT_REASON_PREFIX,
  RegistrationStatusBadge,
  WaitlistDetails,
} from "./registration-status"

const PAGE_SIZE = 20

/** 「本校代表隊已退出，由本校遞補」等候補說明與退回原因放在狀態徽章下方。 */
function StatusCell({ row }: { row: OrganizerRegistration }) {
  return (
    <span className="flex min-w-0 flex-col items-start gap-1">
      <RegistrationStatusBadge
        status={row.status}
        waitlist={row}
        backfilled={row.backfilled}
      />
      <WaitlistDetails status={row.status} waitlist={row} />
      {row.reject_reason && (
        <span
          data-slot="reject-reason"
          className="line-clamp-2 break-words text-caption text-muted-foreground"
        >
          {REJECT_REASON_PREFIX}
          {row.reject_reason}
        </span>
      )}
    </span>
  )
}

function buildColumns(
  onViewScreenshots: (row: OrganizerRegistration) => void,
  onReject: (row: OrganizerRegistration) => void,
): DataTableColumn<OrganizerRegistration>[] {
  return [
    {
      key: "team",
      header: "隊伍",
      cell: (row) => <span className="break-words">{row.team_name}</span>,
    },
    {
      key: "status",
      header: "狀態",
      cell: (row) => <StatusCell row={row} />,
    },
    {
      key: "submitted_at",
      header: "送出時間",
      cell: (row) => (
        <time dateTime={row.submitted_at} className="whitespace-nowrap">
          {formatDateTime(row.submitted_at)}
        </time>
      ),
    },
    {
      key: "avg_rank_score",
      header: "平均段位積分",
      cell: (row) => (
        <span className="font-mono">{row.avg_rank_score.toFixed(2)}</span>
      ),
    },
    {
      key: "actions",
      header: "操作",
      cell: (row) => (
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => onViewScreenshots(row)}
          >
            {RANK_SCREENSHOT_TEXT}
          </Button>
          {row.rejectable && (
            <Button
              variant="outline"
              size="sm"
              className="text-destructive"
              onClick={() => onReject(row)}
            >
              {REJECT_TEXT}
            </Button>
          )}
        </div>
      ),
    },
  ]
}

function CopyTournamentLinkButton({ tournamentId }: { tournamentId: string }) {
  async function copy() {
    try {
      await navigator.clipboard.writeText(tournamentPageUrl(tournamentId))
      notifySuccess(COPIED_TEXT)
    } catch {
      toast.error(COPY_FAILED_TEXT, { id: COPY_FAILED_TEXT })
    }
  }
  return (
    <Button variant="outline" onClick={copy}>
      {COPY_TOURNAMENT_LINK_TEXT}
    </Button>
  )
}

type OrganizerRegistrationsPageProps = {
  tournamentId: string
  filter: RegistrationFilter
  page: number
  /** 篩選或換頁：寫入網址（換篩選時回到第 1 頁）；`replace` 用於頁碼超出時修正網址 */
  onSearchChange: (
    search: OrganizerRegistrationsSearch,
    replace?: boolean,
  ) => void
}

/**
 * S29 報名清單（主辦方賽事後台）：Data table 列出送出過的報名，依分配結果分組排序、可依
 * 狀態篩選；每隊可開段位截圖檢視器，可退回的報名可「退回報名」（必填原因）。
 * 檢視器與確認對話框是兩個受控的 open state：從檢視器按「退回報名」先關閉檢視器再開確認框。
 */
export function OrganizerRegistrationsPage({
  tournamentId,
  filter,
  page,
  onSearchChange,
}: OrganizerRegistrationsPageProps) {
  const filterId = useId()
  const registrations = useOrganizerRegistrations(tournamentId, filter, page)
  const tournament = useQuery(myTournamentQueryOptions(tournamentId))
  const reject = useRejectRegistration(tournamentId)
  const [viewing, setViewing] = useState<OrganizerRegistration | null>(null)
  const [viewerOpen, setViewerOpen] = useState(false)
  // 每次開啟檢視器都重新掛載：預設顯示第一位隊員
  const [viewerSession, setViewerSession] = useState(0)
  const [rejecting, setRejecting] = useState<OrganizerRegistration | null>(null)
  const [rejectOpen, setRejectOpen] = useState(false)
  const data = registrations.data
  const settled = data && !registrations.isPlaceholderData ? data : undefined

  const searchOf = (next: number): OrganizerRegistrationsSearch => ({
    status: filter === DEFAULT_REGISTRATION_FILTER ? undefined : filter,
    page: next > 1 ? next : undefined,
  })

  // 頁碼超出（網址手動輸入，或最後一頁的報名被篩掉）：換到最後一頁
  useEffect(() => {
    if (!settled || settled.items.length > 0 || page <= 1) return
    const lastPage = Math.max(1, Math.ceil(settled.total / settled.page_size))
    if (page > lastPage) {
      onSearchChange(
        {
          status: filter === DEFAULT_REGISTRATION_FILTER ? undefined : filter,
          page: lastPage > 1 ? lastPage : undefined,
        },
        true,
      )
    }
  }, [settled, page, filter, onSearchChange])

  const openViewer = (row: OrganizerRegistration) => {
    setViewing(row)
    setViewerSession((n) => n + 1)
    setViewerOpen(true)
  }
  const openReject = (row: OrganizerRegistration) => {
    setViewerOpen(false)
    setRejecting(row)
    setRejectOpen(true)
  }

  if (registrations.isError && !data) {
    if (parseApiError(registrations.error).kind === "forbidden") {
      return <ErrorPage status={403} />
    }
  }

  const toolbar = (
    <div className="flex items-center gap-3">
      <Label htmlFor={filterId}>狀態</Label>
      <Select
        value={filter}
        onValueChange={(value) =>
          onSearchChange({
            status:
              value === DEFAULT_REGISTRATION_FILTER
                ? undefined
                : (value as RegistrationFilter),
            page: undefined,
          })
        }
      >
        <SelectTrigger id={filterId} className="w-40">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {REGISTRATION_FILTERS.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )

  let body: ReactNode
  if (registrations.isError && !data) {
    body = (
      <div className="flex flex-col items-start gap-3">
        <p className="text-body text-destructive">
          {getErrorMessage(parseApiError(registrations.error))}
        </p>
        <Button variant="outline" onClick={() => registrations.refetch()}>
          重新載入
        </Button>
      </div>
    )
  } else {
    body = (
      <DataTable
        label={ORGANIZER_REGISTRATIONS_TITLE}
        columns={buildColumns(openViewer, openReject)}
        // 頁碼超出、正在導回最後一頁時先顯示 Skeleton，不顯示空狀態
        rows={
          data && data.items.length === 0 && data.total > 0
            ? undefined
            : data?.items
        }
        getRowId={(row) => row.registration_id}
        page={page}
        pageSize={data?.page_size ?? PAGE_SIZE}
        total={data?.total ?? 0}
        onPageChange={(next) => onSearchChange(searchOf(next))}
        toolbar={toolbar}
        empty={
          filter === DEFAULT_REGISTRATION_FILTER ? (
            <EmptyState
              title={NO_REGISTRATIONS_TEXT}
              action={<CopyTournamentLinkButton tournamentId={tournamentId} />}
            />
          ) : (
            <EmptyState title={FILTERED_EMPTY_TEXT} />
          )
        }
      />
    )
  }

  return (
    <section className="flex min-w-0 flex-col gap-6">
      <h1 className="text-heading-lg">{ORGANIZER_REGISTRATIONS_TITLE}</h1>
      {body}
      {viewing && (
        <RankScreenshotViewer
          key={viewerSession}
          tournamentId={tournamentId}
          registration={viewing}
          open={viewerOpen}
          onOpenChange={setViewerOpen}
          onReject={() => openReject(viewing)}
        />
      )}
      {rejecting && (
        <ConfirmDialog
          title={REJECT_TEXT}
          description={rejectDescription(tournament.data)}
          confirmLabel={REJECT_TEXT}
          destructive
          reason={{
            label: REJECT_REASON_LABEL,
            maxLength: REJECT_REASON_MAX_LENGTH,
          }}
          open={rejectOpen}
          onOpenChange={setRejectOpen}
          onConfirm={(reason) =>
            reject.mutateAsync({
              registrationId: rejecting.registration_id,
              reason: reason ?? "",
            })
          }
        />
      )}
    </section>
  )
}
