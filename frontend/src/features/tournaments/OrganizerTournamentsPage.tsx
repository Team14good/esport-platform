import { useQuery } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import { PlusIcon } from "lucide-react"
import { useEffect } from "react"

import type { TournamentRead } from "@/client"
import { DataTable, type DataTableColumn } from "@/components/common/DataTable"
import { EmptyState } from "@/components/common/EmptyState"
import { Button } from "@/components/ui/button"
import { getErrorMessage, parseApiError } from "@/lib/api-error"
import { formatDateTime } from "@/lib/datetime"
import { myTournamentsQueryOptions } from "./organizer-queries"
import { TournamentStatusBadge } from "./TournamentStatusBadge"

export const NO_TOURNAMENTS_TEXT = "你還沒有建立賽事。"
export const CREATE_TOURNAMENT_TEXT = "建立賽事"
export const ORGANIZER_TOURNAMENTS_PAGE_SIZE = 20

function DateTimeCell({ value }: { value: string }) {
  return (
    <time dateTime={value} className="whitespace-nowrap">
      {formatDateTime(value)}
    </time>
  )
}

const COLUMNS: DataTableColumn<TournamentRead>[] = [
  {
    key: "name",
    header: "賽事名稱",
    cell: (row) => (
      <Link
        to="/organizer/tournaments/$tournamentId"
        params={{ tournamentId: row.id }}
        className="break-words font-medium text-primary underline-offset-4 hover:underline"
      >
        {row.name}
      </Link>
    ),
  },
  { key: "game", header: "遊戲", cell: (row) => row.game_name },
  {
    key: "status",
    header: "狀態",
    cell: (row) => <TournamentStatusBadge status={row.status} />,
  },
  {
    key: "registration_end",
    header: "報名截止",
    cell: (row) => <DateTimeCell value={row.registration_end} />,
  },
  {
    key: "start_at",
    header: "開賽時間",
    cell: (row) => <DateTimeCell value={row.start_at} />,
  },
]

function CreateTournamentButton() {
  return (
    <Button asChild>
      <Link to="/organizer/tournaments/new">
        <PlusIcon aria-hidden="true" />
        {CREATE_TOURNAMENT_TEXT}
      </Link>
    </Button>
  )
}

type OrganizerTournamentsPageProps = {
  /** 目前頁碼（從 1 開始，寫在網址 `?page=`） */
  page: number
  /** 換頁：寫入網址；`replace` 用於頁碼超出時修正 */
  onPageChange: (page: number, replace?: boolean) => void
}

/** S25 我的賽事：Data table 列出主辦方建立的賽事（前端分頁，每頁 20 筆）。 */
export function OrganizerTournamentsPage({
  page,
  onPageChange,
}: OrganizerTournamentsPageProps) {
  const tournaments = useQuery(myTournamentsQueryOptions())
  const all = tournaments.data
  const total = all?.length ?? 0
  const lastPage = Math.max(
    1,
    Math.ceil(total / ORGANIZER_TOURNAMENTS_PAGE_SIZE),
  )

  // 頁碼超出（網址手動輸入）：換到最後一頁
  useEffect(() => {
    if (all && page > lastPage) onPageChange(lastPage, true)
  }, [all, page, lastPage, onPageChange])

  const start = (Math.min(page, lastPage) - 1) * ORGANIZER_TOURNAMENTS_PAGE_SIZE
  const rows = all?.slice(start, start + ORGANIZER_TOURNAMENTS_PAGE_SIZE)

  return (
    <section className="flex min-w-0 flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-heading-lg">我的賽事</h1>
        <CreateTournamentButton />
      </div>
      {tournaments.isError && !all ? (
        <div className="flex flex-col items-start gap-3">
          <p className="text-body text-destructive">
            {getErrorMessage(parseApiError(tournaments.error))}
          </p>
          <Button variant="outline" onClick={() => tournaments.refetch()}>
            重新載入
          </Button>
        </div>
      ) : (
        <DataTable
          label="我的賽事"
          columns={COLUMNS}
          rows={rows}
          getRowId={(row) => row.id}
          page={Math.min(page, lastPage)}
          pageSize={ORGANIZER_TOURNAMENTS_PAGE_SIZE}
          total={total}
          onPageChange={(next) => onPageChange(next)}
          empty={
            <EmptyState
              title={NO_TOURNAMENTS_TEXT}
              action={<CreateTournamentButton />}
            />
          }
        />
      )}
    </section>
  )
}
