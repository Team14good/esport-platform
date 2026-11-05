import { useQuery } from "@tanstack/react-query"
import { RefreshCwIcon } from "lucide-react"

import type { RefereeInvitationRead, RefereeRead } from "@/client"
import { ConfirmDialog } from "@/components/common/ConfirmDialog"
import { EmptyState } from "@/components/common/EmptyState"
import { Button } from "@/components/ui/button"
import { LoadingButton } from "@/components/ui/loading-button"
import { Skeleton } from "@/components/ui/skeleton"
import { formatMatchDateTime } from "@/features/competition/match-time"
import { InviteLinkField } from "@/features/registration/InviteLinkField"
import { getErrorMessage, parseApiError } from "@/lib/api-error"
import { notifyError } from "@/lib/feedback"
import { myTournamentQueryOptions } from "./organizer-queries"
import {
  NOT_ACCEPTING_TEXT,
  refereeInvitationQueryOptions,
  refereeInviteUrl,
  refereesQueryOptions,
  useCreateRefereeInvitation,
} from "./referee-queries"

export const REFEREE_LINK_LABEL = "裁判邀請連結"
export const LINK_EXPIRED_TITLE = "連結已過期"
export const LINK_EXPIRED_REASON = "產生新連結後再傳給裁判。"
export const NO_INVITATION_TEXT =
  "產生邀請連結後傳給裁判；裁判開啟連結、登入並完成 Email 驗證後即可接受。連結 7 天有效。"
export const NO_REFEREES_TITLE = "還沒有裁判接受邀請。"
export const NO_REFEREES_DESCRIPTION = "複製邀請連結傳給裁判。"
export const REGENERATE_TITLE = "產生新連結"
export const REGENERATE_DESCRIPTION =
  "舊的邀請連結會立即失效，已收到舊連結的人要改用新連結。已接受的裁判不受影響。"

const CLOSED_STATUSES = new Set(["finished", "cancelled"])

function LoadError({
  error,
  onRetry,
}: {
  error: unknown
  onRetry: () => void
}) {
  return (
    <div className="flex flex-col items-start gap-3">
      <p className="text-body text-destructive">
        {getErrorMessage(parseApiError(error))}
      </p>
      <Button variant="outline" onClick={onRetry}>
        重新載入
      </Button>
    </div>
  )
}

function Loading({ className }: { className: string }) {
  return (
    <div role="status" aria-busy="true">
      <Skeleton aria-hidden className={className} />
      <span className="sr-only">載入中</span>
    </div>
  )
}

/** 「產生新連結」：舊連結仍有效時先確認；已過期直接產生；賽事已結束／已取消時停用。 */
function RegenerateButton({
  tournamentId,
  invitation,
}: {
  tournamentId: string
  invitation: RefereeInvitationRead
}) {
  const create = useCreateRefereeInvitation(tournamentId)
  const className = "w-full sm:w-auto sm:self-start"
  const label = (
    <>
      <RefreshCwIcon aria-hidden="true" />
      產生新連結
    </>
  )
  if (!invitation.accepting || invitation.expired) {
    return (
      <LoadingButton
        type="button"
        variant="outline"
        loading={create.isPending}
        disabled={!invitation.accepting}
        onClick={() => create.mutate(undefined, { onError: notifyError })}
        className={className}
      >
        {label}
      </LoadingButton>
    )
  }
  // 送出中與失敗訊息由 ConfirmDialog 顯示
  return (
    <ConfirmDialog
      title={REGENERATE_TITLE}
      description={REGENERATE_DESCRIPTION}
      confirmLabel="產生新連結"
      onConfirm={() => create.mutateAsync()}
      trigger={
        <Button type="button" variant="outline" className={className}>
          {label}
        </Button>
      }
    />
  )
}

function InvitationSection({ tournamentId }: { tournamentId: string }) {
  const invitation = useQuery(refereeInvitationQueryOptions(tournamentId))
  // 版面已載入賽事；從未產生過邀請時以賽事狀態判斷能否產生
  const tournament = useQuery(myTournamentQueryOptions(tournamentId))
  const create = useCreateRefereeInvitation(tournamentId)

  if (invitation.isPending) return <Loading className="h-24 w-full" />
  if (invitation.isError) {
    return (
      <LoadError
        error={invitation.error}
        onRetry={() => invitation.refetch()}
      />
    )
  }

  const data = invitation.data
  if (data === null) {
    // 賽事還沒載入（或載入失敗）時不知道能否產生：先停用
    const closed =
      tournament.data !== undefined &&
      CLOSED_STATUSES.has(tournament.data.status)
    return (
      <div className="flex flex-col items-start gap-3">
        <p className="text-body text-muted-foreground">
          {closed ? NOT_ACCEPTING_TEXT : NO_INVITATION_TEXT}
        </p>
        <LoadingButton
          type="button"
          loading={create.isPending}
          disabled={closed || tournament.data === undefined}
          onClick={() => create.mutate(undefined, { onError: notifyError })}
          className="w-full sm:w-auto"
        >
          產生邀請連結
        </LoadingButton>
      </div>
    )
  }

  const invalid = !data.accepting
    ? { reason: NOT_ACCEPTING_TEXT }
    : data.expired
      ? { title: LINK_EXPIRED_TITLE, reason: LINK_EXPIRED_REASON }
      : null
  return (
    <InviteLinkField
      label={REFEREE_LINK_LABEL}
      url={refereeInviteUrl(data.token)}
      invalid={invalid}
      note={
        invalid ? undefined : `${formatMatchDateTime(data.expires_at)} 到期`
      }
      action={
        <RegenerateButton tournamentId={tournamentId} invitation={data} />
      }
    />
  )
}

function RefereeList({ referees }: { referees: RefereeRead[] }) {
  // 後端已依接受時間排序；這裡再以時間值排一次（sort 是穩定排序，同時間維持後端順序）
  const sorted = [...referees].sort(
    (a, b) => Date.parse(a.accepted_at) - Date.parse(b.accepted_at),
  )
  return (
    <ul aria-label="裁判名單" className="flex flex-col gap-2">
      {sorted.map((referee) => (
        <li
          key={referee.account_id}
          className="flex min-w-0 flex-col gap-1 rounded-lg border bg-card p-4 sm:flex-row sm:items-center sm:justify-between sm:gap-4"
        >
          <span className="min-w-0 break-words font-semibold text-body">
            {referee.display_name}
          </span>
          <span className="shrink-0 text-caption text-muted-foreground">
            {formatMatchDateTime(referee.accepted_at)} 接受
          </span>
        </li>
      ))}
    </ul>
  )
}

function RefereesSection({ tournamentId }: { tournamentId: string }) {
  const referees = useQuery(refereesQueryOptions(tournamentId))

  if (referees.isPending) return <Loading className="h-16 w-full" />
  if (referees.isError) {
    return (
      <LoadError error={referees.error} onRetry={() => referees.refetch()} />
    )
  }
  if (referees.data.length === 0) {
    return (
      <EmptyState
        title={NO_REFEREES_TITLE}
        description={NO_REFEREES_DESCRIPTION}
        className="rounded-lg border"
      />
    )
  }
  return <RefereeList referees={referees.data} />
}

/** S31 裁判管理（主辦方賽事後台）：裁判邀請連結與已接受的裁判名單。權限由版面處理。 */
export function RefereesPage({ tournamentId }: { tournamentId: string }) {
  return (
    <div className="flex min-w-0 flex-col gap-8">
      <h1 className="text-heading-lg">裁判</h1>
      <section
        aria-labelledby="referee-invitation-heading"
        className="flex min-w-0 flex-col gap-3"
      >
        <h2 id="referee-invitation-heading" className="text-heading-md">
          邀請裁判
        </h2>
        <InvitationSection tournamentId={tournamentId} />
      </section>
      <section
        aria-labelledby="referee-list-heading"
        className="flex min-w-0 flex-col gap-3"
      >
        <h2 id="referee-list-heading" className="text-heading-md">
          已接受的裁判
        </h2>
        <RefereesSection tournamentId={tournamentId} />
      </section>
    </div>
  )
}
