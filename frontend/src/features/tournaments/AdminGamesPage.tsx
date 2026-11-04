import { Link, useNavigate } from "@tanstack/react-router"
import { ArrowLeftIcon, PlusIcon } from "lucide-react"
import { type ReactNode, useEffect, useState } from "react"

import type { GameRead } from "@/client"
import { DataTable, type DataTableColumn } from "@/components/common/DataTable"
import { EmptyState } from "@/components/common/EmptyState"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { getErrorMessage, parseApiError } from "@/lib/api-error"
import {
  SCORE_TYPE_LABELS,
  useAdminGame,
  useAdminGames,
  useCreateGame,
  useUpdateGame,
} from "./admin-games"
import { EMPTY_GAME_FORM, GameForm, gameToFormInput } from "./GameForm"

export const GAMES_EMPTY_TEXT = "還沒有遊戲。"
export const GAME_NOT_FOUND_TEXT = "找不到這款遊戲"
export const BACK_TO_GAMES_TEXT = "回遊戲列表"
export const GAMES_PAGE_SIZE = 20
const GAME_NOT_FOUND = "GAME_NOT_FOUND"

const COLUMNS: DataTableColumn<GameRead>[] = [
  {
    key: "name",
    header: "名稱",
    // 點名稱也能進編輯頁
    cell: (row) => (
      <Link
        to="/admin/games/$gameId"
        params={{ gameId: row.id }}
        className="font-medium break-words hover:underline"
      >
        {row.name}
      </Link>
    ),
  },
  {
    key: "players",
    header: "先發／替補",
    cell: (row) => `${row.starters}／${row.substitutes}`,
  },
  {
    key: "default_bo",
    header: "預設 BO",
    cell: (row) => `BO${row.default_bo}`,
  },
  {
    key: "game_minutes",
    header: "每局時間",
    cell: (row) => `${row.game_minutes} 分鐘`,
  },
  {
    key: "score_type",
    header: "比分型態",
    cell: (row) => SCORE_TYPE_LABELS[row.score_type],
  },
  {
    key: "actions",
    header: "操作",
    cell: (row) => (
      <Button asChild variant="outline" size="sm">
        {/* 每一列的無障礙名稱帶上遊戲名稱，讀螢幕軟體才分得出是哪一筆 */}
        <Link
          to="/admin/games/$gameId"
          params={{ gameId: row.id }}
          aria-label={`編輯「${row.name}」`}
        >
          編輯
        </Link>
      </Button>
    ),
  },
]

function NewGameButton() {
  return (
    <Button asChild>
      <Link to="/admin/games/new">
        <PlusIcon aria-hidden="true" />
        新增遊戲
      </Link>
    </Button>
  )
}

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

/** S36 遊戲設定：列出所有遊戲（前端每頁 20 筆），可新增或進入編輯。 */
export function AdminGamesPage() {
  const games = useAdminGames()
  const [page, setPage] = useState(1)
  const rows = games.data
  const totalPages = Math.max(
    1,
    Math.ceil((rows?.length ?? 0) / GAMES_PAGE_SIZE),
  )

  // 資料變少（例如重新抓取）時頁碼不超出最後一頁
  useEffect(() => {
    if (page > totalPages) setPage(totalPages)
  }, [page, totalPages])

  return (
    <section className="flex min-w-0 flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-heading-lg">遊戲設定</h1>
        {/* 清單是空的時，按鈕在 Empty state 裡 */}
        {rows?.length !== 0 && <NewGameButton />}
      </div>
      {games.isError && !rows ? (
        <LoadError error={games.error} onRetry={() => games.refetch()} />
      ) : (
        <DataTable
          label="遊戲"
          columns={COLUMNS}
          rows={rows?.slice(
            (page - 1) * GAMES_PAGE_SIZE,
            page * GAMES_PAGE_SIZE,
          )}
          getRowId={(row) => row.id}
          page={page}
          pageSize={GAMES_PAGE_SIZE}
          total={rows?.length ?? 0}
          onPageChange={setPage}
          empty={
            <EmptyState title={GAMES_EMPTY_TEXT} action={<NewGameButton />} />
          }
        />
      )}
    </section>
  )
}

function BackToGamesLink() {
  return (
    <Button asChild variant="ghost" className="self-start px-2">
      <Link to="/admin/games">
        <ArrowLeftIcon aria-hidden="true" />
        {BACK_TO_GAMES_TEXT}
      </Link>
    </Button>
  )
}

/** S36 新增遊戲：成功後回到列表。 */
export function NewGamePage() {
  const navigate = useNavigate()
  const create = useCreateGame()
  return (
    <section className="flex min-w-0 max-w-2xl flex-col gap-6">
      <BackToGamesLink />
      <h1 className="text-heading-lg">新增遊戲</h1>
      <GameForm
        defaultValues={EMPTY_GAME_FORM}
        submitLabel="新增遊戲"
        pending={create.isPending}
        onSubmit={async (values) => {
          await create.mutateAsync(values)
          await navigate({ to: "/admin/games" })
        }}
      />
    </section>
  )
}

/** S36 編輯遊戲：預填現值，整份替換（含段位表）；遊戲不存在時顯示「找不到這款遊戲」。 */
export function EditGamePage({ gameId }: { gameId: string }) {
  const game = useAdminGame(gameId)
  const update = useUpdateGame(gameId)

  // 網址的 gameId 不是 UUID 時後端回 422（game_id 欄位錯誤），一樣當成找不到
  const notFound =
    !game.data &&
    game.isError &&
    (() => {
      const parsed = parseApiError(game.error)
      return (
        (parsed.kind === "business" && parsed.code === GAME_NOT_FOUND) ||
        (parsed.kind === "validation" && "game_id" in parsed.fields)
      )
    })()

  let content: ReactNode
  if (game.data) {
    // 已有資料時背景重抓失敗也保留表單，不讓使用者的編輯消失
    content = (
      <>
        <h1 className="break-words text-heading-lg">
          編輯「{game.data.name}」
        </h1>
        <GameForm
          key={game.data.id}
          defaultValues={gameToFormInput(game.data)}
          submitLabel="儲存變更"
          pending={update.isPending}
          onSubmit={(values) => update.mutateAsync(values)}
        />
      </>
    )
  } else if (game.isPending) {
    content = (
      <div role="status" aria-busy="true" className="flex flex-col gap-5">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-14 w-full" />
        <Skeleton className="h-14 w-full" />
        <span className="sr-only">載入中</span>
      </div>
    )
  } else if (notFound) {
    content = (
      <div className="flex flex-col items-start gap-3">
        <h1 className="text-heading-lg">{GAME_NOT_FOUND_TEXT}</h1>
        <Button asChild variant="outline">
          <Link to="/admin/games">{BACK_TO_GAMES_TEXT}</Link>
        </Button>
      </div>
    )
  } else {
    content = (
      <>
        <h1 className="text-heading-lg">編輯遊戲</h1>
        <LoadError error={game.error} onRetry={() => game.refetch()} />
      </>
    )
  }

  return (
    <section className="flex min-w-0 max-w-2xl flex-col gap-6">
      {/* 找不到遊戲時，回列表的連結就在訊息下方 */}
      {!notFound && <BackToGamesLink />}
      {content}
    </section>
  )
}
