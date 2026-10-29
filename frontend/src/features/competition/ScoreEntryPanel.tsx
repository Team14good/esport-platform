import { useEffect, useRef, useState } from "react"

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { LoadingButton } from "@/components/ui/loading-button"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { cn } from "@/lib/utils"
import { formatMatchDateTime } from "./match-time"

// 型別與原因代碼對應後端 competition/scoring.py；系列結果由伺服器計算後經 props 傳入
export type ScoreType = "win_loss" | "rounds"
export type Side = "a" | "b"
export type ScoreReason =
  | "tie"
  | "invalid_score"
  | "invalid_game_no"
  | "series_decided"
  | "redundant_games"
  | "not_last_game"
  | "not_decided"

/** 已登錄的一局；`win_loss` 型態沒有數字比分。 */
export type SavedGame = {
  winner: Side
  scoreA?: number | null
  scoreB?: number | null
}

export type GameInput = { winner: Side } | { scoreA: number; scoreB: number }

export type SeriesSummary = {
  winsA: number
  winsB: number
  winner: Side | null
  canSubmit: boolean
  winsNeeded: number
}

export type Submission = { submittedBy: string; submittedAt: string }

/**
 * callback 的約定：
 * - 成功：先重新取得 `games`、`series`（與 `submission`）並更新 props，再 resolve `null`。
 * - 伺服器拒絕：resolve 原因代碼，面板在該列（或送出鈕下方）顯示對應中文。
 * - 只有非預期的錯誤（連線中斷等）才 reject，且呼叫端要先自行顯示 Toast；面板只恢復成可再操作。
 */
export type ScoreOutcome = Promise<ScoreReason | null>

export type ScoreEntryPanelProps = {
  teamA: string
  teamB: string
  scoreType: ScoreType
  bothCheckedIn: boolean
  /** 已登錄的各局，依局號排列（索引 0 為第 1 局）。 */
  games: SavedGame[]
  series: SeriesSummary
  submission: Submission | null
  /** 登錄或覆寫第 `gameNo` 局；約定見 `ScoreOutcome`。 */
  onRecord: (gameNo: number, input: GameInput) => ScoreOutcome
  /** 刪除第 `gameNo` 局（只會是最後一局）；約定見 `ScoreOutcome`。 */
  onDelete: (gameNo: number) => ScoreOutcome
  /** 送出系列結果（已經過 AlertDialog 確認）；約定見 `ScoreOutcome`。 */
  onSubmit: () => ScoreOutcome
}

const REASON_TEXT: Partial<Record<ScoreReason, string>> = {
  tie: "不能平手",
  invalid_score: "比分格式不正確",
  series_decided: "已有隊伍達到勝局門檻",
  redundant_games: "這樣修改後，後面的局就不需要打了。請先刪除後面的局再修改",
  invalid_game_no: "這一局無法修改，請重新整理頁面",
  not_last_game: "這一局無法修改，請重新整理頁面",
}

const ROW_FALLBACK_TEXT = "操作失敗，請重新整理頁面"
const SUBMIT_FAILED_TEXT = "送出失敗，請重新整理頁面"
const EDITING_HINT = "請先登錄或取消正在編輯的局"

// run() 的兩種非回應結果：被防重複送出擋下、callback 被 reject
const DROPPED = Symbol("dropped")
const FAILED = Symbol("failed")
type RunResult = ScoreReason | null | typeof DROPPED | typeof FAILED

function winsNeededText(winsNeeded: number) {
  return `任一隊拿到 ${winsNeeded} 勝後才能送出`
}

type Editing = { gameNo: number; isNew: boolean }
type RowError = { gameNo: number; text: string }

/** S24 Score entry panel：逐局登錄比分並送出系列結果。只吃 props，不呼叫 API。 */
export function ScoreEntryPanel({
  teamA,
  teamB,
  scoreType,
  bothCheckedIn,
  games,
  series,
  submission,
  onRecord,
  onDelete,
  onSubmit,
}: ScoreEntryPanelProps) {
  const [editing, setEditing] = useState<Editing | null>(null)
  const [pending, setPending] = useState<number | "submit" | null>(null)
  const [rowError, setRowError] = useState<RowError | null>(null)
  const [submitError, setSubmitError] = useState<string | null>(null)
  // state 要等下一次 render 才會停用按鈕；同一個 tick 內的第二次點擊靠 ref 擋下
  const busy = useRef(false)

  // 送出後只剩唯讀，離開編輯狀態
  useEffect(() => {
    if (submission) setEditing(null)
  }, [submission])

  // 局或系列結果更新後，舊的錯誤訊息已不適用
  // biome-ignore lint/correctness/useExhaustiveDependencies: 依 props 變化清除
  useEffect(() => {
    setRowError(null)
    setSubmitError(null)
  }, [games, series])

  const readOnly = submission !== null
  const nextGameNo = games.length + 1
  // 沒有任何一局時直接給第 1 局的輸入列；之後要按「新增一局」才出現
  const showNewRow =
    !readOnly &&
    series.winner === null &&
    (games.length === 0 ||
      (editing?.isNew === true && editing.gameNo === nextGameNo))
  const editingSaved =
    !readOnly && editing && !editing.isNew && editing.gameNo <= games.length
      ? editing.gameNo
      : null
  const editOpen = showNewRow || editingSaved !== null
  const locked = editOpen || pending !== null

  async function run(
    key: number | "submit",
    action: () => ScoreOutcome,
  ): Promise<RunResult> {
    if (busy.current) return DROPPED
    busy.current = true
    setPending(key)
    try {
      return await action()
    } catch {
      // 非業務錯誤（連線中斷等）由呼叫端顯示 Toast；這裡只恢復成可再操作
      return FAILED
    } finally {
      busy.current = false
      setPending(null)
    }
  }

  function showRowError(gameNo: number, result: RunResult) {
    if (result === null || result === DROPPED) return
    // callback 被 reject 時呼叫端已顯示 Toast，列內不再重複
    setRowError(
      result === FAILED
        ? null
        : { gameNo, text: REASON_TEXT[result] ?? ROW_FALLBACK_TEXT },
    )
  }

  async function record(gameNo: number, input: GameInput) {
    if (busy.current) return
    setRowError(null)
    const result = await run(gameNo, () => onRecord(gameNo, input))
    if (result === null) setEditing(null)
    else showRowError(gameNo, result)
  }

  async function remove(gameNo: number) {
    if (busy.current) return
    setRowError(null)
    const result = await run(gameNo, () => onDelete(gameNo))
    showRowError(gameNo, result)
  }

  async function submit() {
    if (busy.current) return
    setSubmitError(null)
    const result = await run("submit", onSubmit)
    if (result === null || result === DROPPED || result === FAILED) return
    setSubmitError(
      result === "not_decided"
        ? winsNeededText(series.winsNeeded)
        : SUBMIT_FAILED_TEXT,
    )
  }

  function startEdit(next: Editing) {
    setRowError(null)
    setEditing(next)
  }

  function cancelEdit() {
    setRowError(null)
    setEditing(null)
  }

  const rowProps = {
    teamA,
    teamB,
    scoreType,
    onRecord: record,
    onCancel: cancelEdit,
  }

  return (
    <Card className="gap-4">
      <CardHeader className="gap-1">
        <div className="flex items-center gap-2.5">
          <h2 className="text-heading-md">比分登錄</h2>
          {bothCheckedIn && games.length === 0 && !readOnly && (
            <Badge
              variant="outline"
              className="border-status-live/40 bg-status-live/15 text-label text-status-live"
            >
              可開始
            </Badge>
          )}
        </div>
        {!bothCheckedIn && !readOnly && (
          <p className="text-caption text-muted-foreground">等待雙方報到</p>
        )}
      </CardHeader>
      <CardContent>
        {/* 兩隊報到前整個面板停用；min-w-0 讓窄螢幕時表格能橫向捲動 */}
        <fieldset
          disabled={!bothCheckedIn && !readOnly}
          className="flex min-w-0 flex-col gap-3"
        >
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="text-overline">局</TableHead>
                <TableHead className="text-center text-overline normal-case">
                  {teamA}
                </TableHead>
                <TableHead aria-hidden="true" />
                <TableHead className="text-center text-overline normal-case">
                  {teamB}
                </TableHead>
                <TableHead>
                  <span className="sr-only">動作</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {games.map((game, index) => {
                const gameNo = index + 1
                const error =
                  rowError?.gameNo === gameNo ? rowError.text : undefined
                if (editingSaved === gameNo) {
                  return (
                    <EntryRow
                      key={gameNo}
                      {...rowProps}
                      gameNo={gameNo}
                      initial={game}
                      pending={pending === gameNo}
                      error={error}
                      canCancel
                    />
                  )
                }
                return (
                  <SavedRow
                    key={gameNo}
                    gameNo={gameNo}
                    game={game}
                    teamA={teamA}
                    teamB={teamB}
                    scoreType={scoreType}
                    readOnly={readOnly}
                    locked={locked}
                    pending={pending === gameNo}
                    error={error}
                    canDelete={gameNo === games.length}
                    onEdit={() => startEdit({ gameNo, isNew: false })}
                    onDelete={() => remove(gameNo)}
                  />
                )
              })}
              {showNewRow && (
                <EntryRow
                  key={nextGameNo}
                  {...rowProps}
                  gameNo={nextGameNo}
                  initial={null}
                  pending={pending === nextGameNo}
                  error={
                    rowError?.gameNo === nextGameNo ? rowError.text : undefined
                  }
                  canCancel={games.length > 0}
                />
              )}
            </TableBody>
          </Table>
          {!readOnly && series.winner === null && (
            <div>
              <Button
                variant="outline"
                size="sm"
                disabled={locked}
                onClick={() => startEdit({ gameNo: nextGameNo, isNew: true })}
              >
                新增一局
              </Button>
            </div>
          )}
          <SeriesFooter
            teamA={teamA}
            teamB={teamB}
            series={series}
            submission={submission}
            submitting={pending === "submit"}
            submitDisabled={!series.canSubmit || locked}
            editOpen={editOpen}
            submitError={submitError}
            onSubmit={submit}
          />
        </fieldset>
      </CardContent>
    </Card>
  )
}

type RowBase = {
  gameNo: number
  teamA: string
  teamB: string
  scoreType: ScoreType
}

function SavedRow({
  gameNo,
  game,
  teamA,
  teamB,
  scoreType,
  readOnly,
  locked,
  pending,
  error,
  canDelete,
  onEdit,
  onDelete,
}: RowBase & {
  game: SavedGame
  readOnly: boolean
  locked: boolean
  pending: boolean
  error?: string
  canDelete: boolean
  onEdit: () => void
  onDelete: () => void
}) {
  return (
    <>
      <TableRow>
        <TableCell>第 {gameNo} 局</TableCell>
        {scoreType === "rounds" ? (
          <>
            <TableCell className="text-center font-mono text-body-lg font-bold">
              {game.scoreA}
            </TableCell>
            <TableCell className="px-0 text-center font-mono text-muted-foreground">
              :
            </TableCell>
            <TableCell className="text-center font-mono text-body-lg font-bold">
              {game.scoreB}
            </TableCell>
          </>
        ) : (
          <TableCell colSpan={3} className="text-center font-mono font-bold">
            {game.winner === "a" ? teamA : teamB} 勝
          </TableCell>
        )}
        <TableCell>
          {!readOnly && (
            <div className="flex items-center justify-end gap-1">
              <span className="mr-1 text-caption text-muted-foreground">
                已登錄
              </span>
              <Button
                variant="ghost"
                size="sm"
                disabled={locked}
                onClick={onEdit}
              >
                修改
              </Button>
              {canDelete && (
                <LoadingButton
                  variant="ghost"
                  size="sm"
                  loading={pending}
                  disabled={locked}
                  onClick={onDelete}
                >
                  刪除
                </LoadingButton>
              )}
            </div>
          )}
        </TableCell>
      </TableRow>
      {error && <RowMessage text={error} alert />}
    </>
  )
}

function EntryRow({
  gameNo,
  teamA,
  teamB,
  scoreType,
  initial,
  pending,
  error,
  canCancel,
  onRecord,
  onCancel,
}: RowBase & {
  initial: SavedGame | null
  pending: boolean
  error?: string
  canCancel: boolean
  onRecord: (gameNo: number, input: GameInput) => void
  onCancel: () => void
}) {
  // 修改中按「取消」會卸載這一列，下次再編輯時從已存的值重新開始
  const [winner, setWinner] = useState<Side | null>(initial?.winner ?? null)
  const [scoreA, setScoreA] = useState(initial?.scoreA?.toString() ?? "")
  const [scoreB, setScoreB] = useState(initial?.scoreB?.toString() ?? "")

  const complete = scoreA !== "" && scoreB !== ""
  const tie =
    scoreType === "rounds" && complete && Number(scoreA) === Number(scoreB)
  const ready = scoreType === "rounds" ? complete && !tie : winner !== null

  function submit() {
    if (!ready || pending) return
    onRecord(
      gameNo,
      scoreType === "rounds"
        ? { scoreA: Number(scoreA), scoreB: Number(scoreB) }
        : { winner: winner as Side },
    )
  }

  const pick = (side: Side, name: string) => (
    <Button
      type="button"
      variant={winner === side ? "default" : "outline"}
      size="sm"
      aria-pressed={winner === side}
      disabled={pending}
      onClick={() => setWinner(side)}
      className="w-full max-w-40"
    >
      {name}
    </Button>
  )

  const score = (value: string, set: (v: string) => void, team: string) => (
    <Input
      inputMode="numeric"
      autoComplete="off"
      maxLength={3}
      aria-label={`第 ${gameNo} 局 ${team} 分數`}
      value={value}
      disabled={pending}
      onChange={(event) => set(normalizeScore(event.target.value))}
      onKeyDown={(event) => {
        if (event.key === "Enter") submit()
      }}
      className="mx-auto w-20 text-center font-mono text-body-lg font-bold"
    />
  )

  return (
    <>
      <TableRow>
        <TableCell>第 {gameNo} 局</TableCell>
        {scoreType === "rounds" ? (
          <>
            <TableCell className="text-center">
              {score(scoreA, setScoreA, teamA)}
            </TableCell>
            <TableCell className="px-0 text-center font-mono text-muted-foreground">
              :
            </TableCell>
            <TableCell className="text-center">
              {score(scoreB, setScoreB, teamB)}
            </TableCell>
          </>
        ) : (
          <>
            <TableCell className="text-center">{pick("a", teamA)}</TableCell>
            <TableCell />
            <TableCell className="text-center">{pick("b", teamB)}</TableCell>
          </>
        )}
        <TableCell>
          <div className="flex items-center justify-end gap-1">
            <LoadingButton
              variant="outline"
              size="sm"
              loading={pending}
              disabled={!ready}
              onClick={submit}
            >
              登錄
            </LoadingButton>
            {canCancel && (
              <Button
                variant="ghost"
                size="sm"
                disabled={pending}
                onClick={onCancel}
              >
                取消
              </Button>
            )}
          </div>
        </TableCell>
      </TableRow>
      {error ? (
        <RowMessage text={error} alert />
      ) : (
        tie && <RowMessage text={REASON_TEXT.tie ?? ""} />
      )}
    </>
  )
}

/** 只留非負整數：全形數字轉半形、濾掉其他字元、去掉開頭多餘的 0、最多 3 位。 */
function normalizeScore(raw: string) {
  return raw
    .replace(/[０-９]/g, (digit) =>
      String.fromCharCode(digit.charCodeAt(0) - 0xfee0),
    )
    .replace(/\D/g, "")
    .replace(/^0+(?=\d)/, "")
    .slice(0, 3)
}

function RowMessage({
  text,
  alert = false,
}: {
  text: string
  alert?: boolean
}) {
  return (
    <TableRow className="border-b-0 hover:bg-transparent">
      <TableCell colSpan={5} className="pt-0 whitespace-normal">
        <p
          role={alert ? "alert" : undefined}
          className="text-caption text-destructive"
        >
          {text}
        </p>
      </TableCell>
    </TableRow>
  )
}

function SeriesFooter({
  teamA,
  teamB,
  series,
  submission,
  submitting,
  submitDisabled,
  editOpen,
  submitError,
  onSubmit,
}: {
  teamA: string
  teamB: string
  series: SeriesSummary
  submission: Submission | null
  submitting: boolean
  submitDisabled: boolean
  editOpen: boolean
  submitError: string | null
  onSubmit: () => void
}) {
  const nameClass = (side: Side) =>
    cn(
      "text-body",
      series.winner === side && "font-bold",
      series.winner && series.winner !== side && "text-status-eliminated",
    )

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-3 border-t pt-4">
      <div className="flex flex-col gap-1">
        <span className="text-caption text-muted-foreground">
          {submission ? "系列結果" : "系列結果預覽"}
        </span>
        <div className="flex flex-wrap items-center gap-3">
          <span className={nameClass("a")}>{teamA}</span>
          <span className="whitespace-nowrap font-mono text-score">
            <span className={nameClass("a")}>{series.winsA}</span>
            <span className="mx-1.5 text-muted-foreground">:</span>
            <span className={nameClass("b")}>{series.winsB}</span>
          </span>
          <span className={nameClass("b")}>{teamB}</span>
        </div>
        {submission && (
          <span className="text-caption text-muted-foreground">
            {submission.submittedBy} 送出 ·{" "}
            {formatMatchDateTime(submission.submittedAt)}
          </span>
        )}
      </div>
      {!submission && (
        <div className="ml-auto flex flex-col items-end gap-1">
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <LoadingButton loading={submitting} disabled={submitDisabled}>
                送出系列結果
              </LoadingButton>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>送出系列結果</AlertDialogTitle>
                <p className="font-semibold">
                  {teamA} {series.winsA} : {series.winsB} {teamB}
                </p>
                <AlertDialogDescription>
                  送出後無法再修改，只能經由申訴更正。
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>取消</AlertDialogCancel>
                <AlertDialogAction onClick={onSubmit}>
                  送出系列結果
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
          {series.winner === null ? (
            <span className="text-caption text-muted-foreground">
              {winsNeededText(series.winsNeeded)}
            </span>
          ) : (
            series.canSubmit &&
            editOpen && (
              <span className="text-caption text-muted-foreground">
                {EDITING_HINT}
              </span>
            )
          )}
          {submitError && (
            <p role="alert" className="text-caption text-destructive">
              {submitError}
            </p>
          )}
        </div>
      )}
    </div>
  )
}
