import { useQuery } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import { type ReactNode, useEffect, useMemo } from "react"

import type { ManagedMatch } from "@/client"
import { DataTable, type DataTableColumn } from "@/components/common/DataTable"
import { EmptyState } from "@/components/common/EmptyState"
import { StatusBadge } from "@/components/common/StatusBadge"
import { ErrorPage } from "@/components/layout/ErrorPage"
import { Button } from "@/components/ui/button"
import { getErrorMessage, parseApiError } from "@/lib/api-error"
import {
  MATCH_STATUS_BADGES,
  matchLabel,
  THIRD_PLACE_LABEL,
} from "./match-status"
import { formatMatchDateTime } from "./match-time"
import {
  isBracketNotFound,
  managedMatchesQueryOptions,
  tournamentRefereesQueryOptions,
} from "./organizer-matches-queries"
import { RefereeSelect } from "./RefereeSelect"
import { RescheduleDialog } from "./RescheduleDialog"
import { roundName } from "./round-name"

export const ORGANIZER_MATCHES_PAGE_SIZE = 20
export const NO_BRACKET_TEXT = "還沒有對戰表，抽籤後就能在這裡管理場次。"
const PENDING_SIDE_TEXT = "—"

/** 依輪次排序，同輪的季軍賽排在決賽之後。 */
export function sortMatches(matches: ManagedMatch[]): ManagedMatch[] {
  return [...matches].sort(
    (a, b) =>
      a.round_no - b.round_no ||
      Number(a.is_third_place) - Number(b.is_third_place) ||
      a.slot_no - b.slot_no,
  )
}

function sideText(
  team: ManagedMatch["team_a"],
  source: ManagedMatch["source_a"],
): string {
  return team?.name ?? source ?? PENDING_SIDE_TEXT
}

function buildColumns(
  tournamentId: string,
  rounds: number,
  names: ReadonlyMap<string, string> | null,
  hasReferees: boolean,
): DataTableColumn<ManagedMatch>[] {
  return [
    {
      key: "match",
      header: "場次",
      cell: (row) => <span className="font-medium">{matchLabel(row)}</span>,
    },
    {
      key: "round",
      header: "輪次",
      cell: (row) =>
        row.is_third_place
          ? THIRD_PLACE_LABEL
          : roundName(row.round_no, rounds),
    },
    {
      key: "teams",
      header: "對戰",
      cell: (row) => (
        <span className="break-words">
          {sideText(row.team_a, row.source_a)} vs{" "}
          {sideText(row.team_b, row.source_b)}
        </span>
      ),
    },
    {
      key: "time",
      header: "時間",
      cell: (row) => (
        <time dateTime={row.scheduled_at} className="whitespace-nowrap">
          {formatMatchDateTime(row.scheduled_at)}
        </time>
      ),
    },
    {
      key: "status",
      header: "狀態",
      cell: (row) => {
        const badge = MATCH_STATUS_BADGES[row.status]
        return (
          <StatusBadge tone={badge.tone} pulse={badge.pulse}>
            {badge.label}
          </StatusBadge>
        )
      },
    },
    {
      key: "referee",
      header: "裁判",
      cell: (row) => (
        <RefereeSelect
          tournamentId={tournamentId}
          match={row}
          names={names}
          hasReferees={hasReferees}
        />
      ),
    },
    {
      key: "actions",
      header: "操作",
      cell: (row) => (
        <div className="flex flex-col items-start gap-2">
          <RescheduleDialog tournamentId={tournamentId} match={row} />
          <Link
            to="/tournaments/$tournamentId/matches/$matchId"
            params={{ tournamentId, matchId: row.id }}
            className="text-body text-primary underline-offset-4 hover:underline"
          >
            查看場次
          </Link>
        </div>
      ),
    },
  ]
}

type OrganizerMatchesPageProps = {
  tournamentId: string
  /** 目前頁碼（從 1 開始，寫在網址 `?page=`） */
  page: number
  /** 換頁：寫入網址；`replace` 用於頁碼超出時修正 */
  onPageChange: (page: number, replace?: boolean) => void
}

/** S30 場次管理：Data table 列出全部場次（前端分頁，每頁 20 筆），可修改時間與指派裁判。 */
export function OrganizerMatchesPage({
  tournamentId,
  page,
  onPageChange,
}: OrganizerMatchesPageProps) {
  const matches = useQuery(managedMatchesQueryOptions(tournamentId))
  const referees = useQuery(tournamentRefereesQueryOptions(tournamentId))

  const sorted = useMemo(
    () => (matches.data ? sortMatches(matches.data) : undefined),
    [matches.data],
  )
  const rounds = useMemo(
    () => Math.max(1, ...(sorted ?? []).map((match) => match.round_no)),
    [sorted],
  )
  // 裁判清單載入失敗時為 null：不能把它當成「沒有裁判」
  const names = useMemo(
    () =>
      referees.data
        ? new Map(
            referees.data.map((referee) => [
              referee.account_id,
              referee.display_name,
            ]),
          )
        : null,
    [referees.data],
  )
  const columns = useMemo(
    () => buildColumns(tournamentId, rounds, names, (names?.size ?? 0) > 0),
    [tournamentId, rounds, names],
  )

  const total = sorted?.length ?? 0
  const lastPage = Math.max(1, Math.ceil(total / ORGANIZER_MATCHES_PAGE_SIZE))

  // 頁碼超出（網址手動輸入）：換到最後一頁
  useEffect(() => {
    if (sorted && page > lastPage) onPageChange(lastPage, true)
  }, [sorted, page, lastPage, onPageChange])

  const current = Math.min(page, lastPage)
  const start = (current - 1) * ORGANIZER_MATCHES_PAGE_SIZE
  // 裁判清單載入前先不顯示列，避免裁判欄先閃出「未知的裁判」
  const rows = referees.isPending
    ? undefined
    : sorted?.slice(start, start + ORGANIZER_MATCHES_PAGE_SIZE)

  let body: ReactNode
  if (matches.isError && !matches.data) {
    if (parseApiError(matches.error).kind === "forbidden") {
      return <ErrorPage status={403} />
    }
    body = isBracketNotFound(matches.error) ? (
      <EmptyState title={NO_BRACKET_TEXT} />
    ) : (
      <div className="flex flex-col items-start gap-3">
        <p className="text-body text-destructive">
          {getErrorMessage(parseApiError(matches.error))}
        </p>
        <Button variant="outline" onClick={() => matches.refetch()}>
          重新載入
        </Button>
      </div>
    )
  } else {
    body = (
      <DataTable
        label="場次管理"
        columns={columns}
        rows={rows}
        getRowId={(row) => row.id}
        page={current}
        pageSize={ORGANIZER_MATCHES_PAGE_SIZE}
        total={total}
        onPageChange={(next) => onPageChange(next)}
        empty={<EmptyState title={NO_BRACKET_TEXT} />}
      />
    )
  }

  return (
    <section className="flex min-w-0 flex-col gap-6">
      <h1 className="text-heading-lg">場次管理</h1>
      {referees.isError && (
        <div className="flex flex-wrap items-center gap-3">
          <p role="alert" className="text-body text-destructive">
            裁判清單載入失敗：{getErrorMessage(parseApiError(referees.error))}
          </p>
          <Button variant="outline" onClick={() => referees.refetch()}>
            重新載入
          </Button>
        </div>
      )}
      {body}
    </section>
  )
}
