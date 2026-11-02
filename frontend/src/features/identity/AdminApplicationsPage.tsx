import { useEffect, useId } from "react"

import type { AdminOrganizerApplication } from "@/client"
import { ConfirmDialog } from "@/components/common/ConfirmDialog"
import { DataTable, type DataTableColumn } from "@/components/common/DataTable"
import { EmptyState } from "@/components/common/EmptyState"
import { StatusBadge } from "@/components/common/StatusBadge"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { getErrorMessage, parseApiError } from "@/lib/api-error"
import { formatDateTime } from "@/lib/datetime"
import {
  APPLICATION_FILTERS,
  type ApplicationFilter,
  type ApplicationsSearch,
  DEFAULT_FILTER,
  REJECT_REASON_MAX_LENGTH,
  useAdminApplications,
  useApproveApplication,
  useRefreshAdminApplications,
  useRejectApplication,
} from "./admin-applications"
import { APPLICATION_STATUS_BADGES } from "./organizer-application"

export const PENDING_EMPTY_TEXT = "目前沒有待審核的主辦方申請。"
export const FILTERED_EMPTY_TEXT = "沒有符合條件的主辦方申請。"
export const REJECT_DESCRIPTION_TEXT =
  "申請人會看到退回原因，並可以修改後重新申請。"

export function approveDescription(applicant: string): string {
  return `核准後，${applicant} 會立即取得主辦方權限。`
}

function ReviewActions({
  application,
}: {
  application: AdminOrganizerApplication
}) {
  const approve = useApproveApplication()
  const reject = useRejectApplication()
  const refresh = useRefreshAdminApplications()
  // 審核失敗（例如別人已經審核過）後關閉對話框時重新抓取，列表才不會停在舊狀態
  const refreshOnClose = (open: boolean) => {
    if (!open) void refresh()
  }

  return (
    <div className="flex flex-wrap gap-2">
      <ConfirmDialog
        title="核准主辦方申請"
        description={approveDescription(application.applicant_display_name)}
        confirmLabel="核准"
        onConfirm={() => approve.mutateAsync(application.id)}
        onOpenChange={refreshOnClose}
        trigger={
          <Button variant="outline" size="sm">
            核准
          </Button>
        }
      />
      <ConfirmDialog
        title="退回主辦方申請"
        description={REJECT_DESCRIPTION_TEXT}
        confirmLabel="退回申請"
        destructive
        reason={{ label: "退回原因", maxLength: REJECT_REASON_MAX_LENGTH }}
        onConfirm={(reason) =>
          reject.mutateAsync({
            applicationId: application.id,
            reason: reason ?? "",
          })
        }
        onOpenChange={refreshOnClose}
        trigger={
          <Button variant="outline" size="sm" className="text-destructive">
            退回申請
          </Button>
        }
      />
    </div>
  )
}

const COLUMNS: DataTableColumn<AdminOrganizerApplication>[] = [
  {
    key: "club_name",
    header: "社團名稱",
    cell: (row) => row.club_name,
  },
  {
    key: "school",
    header: "學校",
    cell: (row) => row.school_name,
  },
  {
    key: "applicant",
    header: "申請人",
    cell: (row) => (
      <div className="flex min-w-0 flex-col">
        <span>{row.applicant_display_name}</span>
        <span className="break-all text-caption text-muted-foreground">
          {row.applicant_email}
        </span>
      </div>
    ),
  },
  {
    key: "created_at",
    header: "送出時間",
    cell: (row) => (
      <time dateTime={row.created_at} className="whitespace-nowrap">
        {formatDateTime(row.created_at)}
      </time>
    ),
  },
  {
    key: "status",
    header: "狀態",
    cell: (row) => {
      const badge = APPLICATION_STATUS_BADGES[row.status]
      return <StatusBadge tone={badge.tone}>{badge.label}</StatusBadge>
    },
  },
  {
    key: "actions",
    header: "操作",
    // 只有待審核的申請可以審核
    cell: (row) =>
      row.status === "pending" ? <ReviewActions application={row} /> : null,
  },
]

type AdminApplicationsPageProps = {
  filter: ApplicationFilter
  page: number
  /** 篩選或換頁：寫入網址（換篩選時回到第 1 頁） */
  onSearchChange: (search: ApplicationsSearch, replace?: boolean) => void
}

/** S35 主辦方申請審核：Data table 列出申請，核准或退回（必填原因）都經確認對話框。 */
export function AdminApplicationsPage({
  filter,
  page,
  onSearchChange,
}: AdminApplicationsPageProps) {
  const filterId = useId()
  const applications = useAdminApplications(filter, page)
  const data = applications.data

  // 頁碼超出（例如最後一頁的申請都審核完了）：換到最後一頁
  useEffect(() => {
    if (!data || data.items.length > 0 || data.total === 0 || page <= 1) return
    const lastPage = Math.ceil(data.total / data.page_size)
    if (page > lastPage) {
      onSearchChange(
        {
          status: filter === DEFAULT_FILTER ? undefined : filter,
          page: lastPage > 1 ? lastPage : undefined,
        },
        true,
      )
    }
  }, [data, page, filter, onSearchChange])

  const toolbar = (
    <div className="flex items-center gap-3">
      <Label htmlFor={filterId}>狀態</Label>
      <Select
        value={filter}
        onValueChange={(value) =>
          onSearchChange({
            status:
              value === DEFAULT_FILTER
                ? undefined
                : (value as ApplicationFilter),
            page: undefined,
          })
        }
      >
        <SelectTrigger id={filterId} className="w-32">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {APPLICATION_FILTERS.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )

  return (
    <section className="flex min-w-0 flex-col gap-6">
      <h1 className="text-heading-lg">主辦方申請</h1>
      {applications.isError && !data ? (
        <div className="flex flex-col items-start gap-3">
          <p className="text-body text-destructive">
            {getErrorMessage(parseApiError(applications.error))}
          </p>
          <Button variant="outline" onClick={() => applications.refetch()}>
            重新載入
          </Button>
        </div>
      ) : (
        <DataTable
          label="主辦方申請"
          columns={COLUMNS}
          rows={data?.items}
          getRowId={(row) => row.id}
          page={page}
          pageSize={data?.page_size ?? 20}
          total={data?.total ?? 0}
          onPageChange={(next) =>
            onSearchChange({
              status: filter === DEFAULT_FILTER ? undefined : filter,
              page: next > 1 ? next : undefined,
            })
          }
          toolbar={toolbar}
          empty={
            <EmptyState
              title={
                filter === DEFAULT_FILTER
                  ? PENDING_EMPTY_TEXT
                  : FILTERED_EMPTY_TEXT
              }
            />
          }
        />
      )}
    </section>
  )
}
