import { useQuery } from "@tanstack/react-query"
import { type ReactNode, useState } from "react"
import { toast } from "sonner"

import { type AppealGroup, type AppealItem, DisputesService } from "@/client"
import { DataTable, type DataTableColumn } from "@/components/common/DataTable"
import { EmptyState } from "@/components/common/EmptyState"
import { StatusBadge } from "@/components/common/StatusBadge"
import { ErrorPage } from "@/components/layout/ErrorPage"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { matchLabel } from "@/features/competition/match-status"
import { formatMatchDateTime } from "@/features/competition/match-time"
import { getErrorMessage, parseApiError } from "@/lib/api-error"
import { notifyError } from "@/lib/feedback"
import { DECISION_LABEL } from "./decision-label"
import { tournamentAppealsQueryOptions } from "./organizer-queries"
import {
  CorrectAppealDialog,
  canCorrect,
  canReplay,
  RematchAppealDialog,
  UpholdAppealDialog,
} from "./ResolveAppealDialogs"

export const APPEALS_PAGE_SIZE = 20
export const NO_OPEN_APPEALS_TEXT = "目前沒有待處理的申訴。"
export const VIEW_DESCRIPTION_TEXT = "查看說明"
export const VIEW_ATTACHMENT_TEXT = "查看附件"
export const OPEN_STATUS_TEXT = "待處理"
export const POPUP_BLOCKED_TEXT =
  "瀏覽器擋下了新分頁，請允許這個網站開啟彈出式視窗後再查看附件。"

// 附件的物件網址在新分頁開啟後保留一段時間再釋放
const ATTACHMENT_URL_TTL_MS = 60_000

/**
 * 以登入者的權杖下載附件，於新分頁開啟；失敗時關閉分頁並以錯誤 Toast 顯示。
 * 分頁要在點擊當下（`await` 之前）開啟，Firefox、Safari 才不會當成彈出式視窗擋下；
 * 下載完成後再把分頁導到附件。
 */
async function openAttachment(appealId: string) {
  const tab = window.open("", "_blank")
  if (!tab) {
    toast.error(POPUP_BLOCKED_TEXT, {
      id: POPUP_BLOCKED_TEXT,
      duration: Number.POSITIVE_INFINITY,
      closeButton: true,
    })
    return
  }
  // 新分頁不能反過來操作本頁（等同 noopener）
  tab.opener = null
  try {
    const { data } = await DisputesService.downloadAppealAttachment({
      path: { appeal_id: appealId },
    })
    const url = URL.createObjectURL(data as Blob)
    tab.location.href = url
    setTimeout(() => URL.revokeObjectURL(url), ATTACHMENT_URL_TTL_MS)
  } catch (error) {
    tab.close()
    notifyError(error)
  }
}

function Stack({ children }: { children: ReactNode }) {
  return <div className="flex flex-col gap-1">{children}</div>
}

function AppealDetailsDialog({ group }: { group: AppealGroup }) {
  const label = matchLabel({
    code: group.match_code,
    is_third_place: group.is_third_place,
  })
  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="link" size="sm" className="h-auto px-0">
          {VIEW_DESCRIPTION_TEXT}
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[90dvh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{label} 的申訴</DialogTitle>
          <DialogDescription>申訴內容只有主辦方看得到。</DialogDescription>
        </DialogHeader>
        <ul className="flex flex-col gap-4">
          {group.appeals.map((appeal) => (
            <AppealDetail key={appeal.id} appeal={appeal} />
          ))}
        </ul>
      </DialogContent>
    </Dialog>
  )
}

function AppealDetail({ appeal }: { appeal: AppealItem }) {
  return (
    <li className="flex flex-col gap-2 rounded-md border p-3">
      <p className="text-label">
        {appeal.team_name}・{formatMatchDateTime(appeal.filed_at)}
      </p>
      <p className="whitespace-pre-wrap break-words text-body">
        {appeal.description}
      </p>
      {appeal.has_attachment && (
        <Button
          variant="outline"
          size="sm"
          className="self-start"
          onClick={() => void openAttachment(appeal.id)}
        >
          {VIEW_ATTACHMENT_TEXT}
        </Button>
      )}
      {appeal.reason && (
        <p className="whitespace-pre-wrap break-words text-caption text-muted-foreground">
          處理理由：{appeal.reason}
        </p>
      )}
    </li>
  )
}

function StatusCell({ group }: { group: AppealGroup }) {
  if (group.has_open) {
    return (
      <StatusBadge tone="appeal" pulse>
        {OPEN_STATUS_TEXT}
      </StatusBadge>
    )
  }
  const decision = group.appeals.find((a) => a.decision)?.decision
  return (
    <StatusBadge tone="confirmed">
      {decision ? DECISION_LABEL[decision] : "已結案"}
    </StatusBadge>
  )
}

function Actions({
  tournamentId,
  group,
}: {
  tournamentId: string
  group: AppealGroup
}) {
  if (!group.has_open) return <span className="text-muted-foreground">—</span>
  return (
    <div className="flex flex-col items-start gap-2">
      <UpholdAppealDialog tournamentId={tournamentId} group={group} />
      {canCorrect(group) && (
        <CorrectAppealDialog tournamentId={tournamentId} group={group} />
      )}
      {canReplay(group) && (
        <RematchAppealDialog tournamentId={tournamentId} group={group} />
      )}
    </div>
  )
}

function buildColumns(tournamentId: string): DataTableColumn<AppealGroup>[] {
  return [
    {
      key: "match",
      header: "場次",
      cell: (group) => (
        <Stack>
          <span className="font-medium">
            {matchLabel({
              code: group.match_code,
              is_third_place: group.is_third_place,
            })}
          </span>
          {!group.is_third_place && (
            <span className="text-caption text-muted-foreground">
              {group.round_name}
            </span>
          )}
        </Stack>
      ),
    },
    {
      key: "teams",
      header: "提出隊伍",
      cell: (group) => (
        <Stack>
          {group.appeals.map((appeal) => (
            <span key={appeal.id} className="break-words">
              {appeal.team_name}
            </span>
          ))}
        </Stack>
      ),
    },
    {
      key: "filed_at",
      header: "提出時間",
      cell: (group) => (
        <Stack>
          {group.appeals.map((appeal) => (
            <time
              key={appeal.id}
              dateTime={appeal.filed_at}
              className="whitespace-nowrap"
            >
              {formatMatchDateTime(appeal.filed_at)}
            </time>
          ))}
        </Stack>
      ),
    },
    {
      key: "status",
      header: "狀態與決定",
      cell: (group) => <StatusCell group={group} />,
    },
    {
      key: "content",
      header: "說明與附件",
      cell: (group) => <AppealDetailsDialog group={group} />,
    },
    {
      key: "actions",
      header: "操作",
      cell: (group) => <Actions tournamentId={tournamentId} group={group} />,
    },
  ]
}

/**
 * S32 申訴（主辦方賽事後台）：Data table 依場次列出申訴，可查看說明與附件；
 * 未結案的場次可「維持原結果」「更正結果」「重新比賽」（只有棄權的場次）。
 */
export function AppealsPage({ tournamentId }: { tournamentId: string }) {
  const appeals = useQuery(tournamentAppealsQueryOptions(tournamentId))
  const [page, setPage] = useState(1)

  if (appeals.isError && !appeals.data) {
    if (parseApiError(appeals.error).kind === "forbidden") {
      return <ErrorPage status={403} />
    }
  }

  const groups = appeals.data
  const total = groups?.length ?? 0
  const lastPage = Math.max(1, Math.ceil(total / APPEALS_PAGE_SIZE))
  const current = Math.min(page, lastPage)
  const start = (current - 1) * APPEALS_PAGE_SIZE
  const rows = groups?.slice(start, start + APPEALS_PAGE_SIZE)
  const hasOpen = groups?.some((group) => group.has_open) ?? false

  let body: ReactNode
  if (appeals.isError && !groups) {
    body = (
      <div className="flex flex-col items-start gap-3">
        <p className="text-body text-destructive">
          {getErrorMessage(parseApiError(appeals.error))}
        </p>
        <Button variant="outline" onClick={() => appeals.refetch()}>
          重新載入
        </Button>
      </div>
    )
  } else {
    body = (
      <>
        {groups && groups.length > 0 && !hasOpen && (
          <p className="text-body text-muted-foreground">
            {NO_OPEN_APPEALS_TEXT}
          </p>
        )}
        <DataTable
          label="申訴"
          columns={buildColumns(tournamentId)}
          rows={rows}
          getRowId={(group) => group.match_id}
          page={current}
          pageSize={APPEALS_PAGE_SIZE}
          total={total}
          onPageChange={setPage}
          empty={<EmptyState title={NO_OPEN_APPEALS_TEXT} />}
        />
      </>
    )
  }

  return (
    <section className="flex min-w-0 flex-col gap-6">
      <h1 className="text-heading-lg">申訴</h1>
      {body}
    </section>
  )
}
