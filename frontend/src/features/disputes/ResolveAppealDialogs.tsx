import {
  type UseQueryResult,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import { CircleAlertIcon } from "lucide-react"
import { type ReactNode, useId, useState } from "react"

import type {
  AppealGroup,
  AppealResolveIn,
  GameScoreIn,
  RescheduleInfo,
} from "@/client"
import { ConfirmDialog } from "@/components/common/ConfirmDialog"
import { Alert, AlertDescription } from "@/components/ui/alert"
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { LoadingButton } from "@/components/ui/loading-button"
import { Textarea } from "@/components/ui/textarea"
import { matchLabel } from "@/features/competition/match-status"
import { formatMatchDateTime } from "@/features/competition/match-time"
import { type ApiError, getErrorMessage, parseApiError } from "@/lib/api-error"
import { isoToTaipeiLocal, taipeiLocalToIso } from "@/lib/datetime"
import { notifyError, notifySuccess } from "@/lib/feedback"
import { DECISION_LABEL } from "./decision-label"
import {
  replayWindowQueryOptions,
  resolveAppeals,
  useRefetchAppeals,
} from "./organizer-queries"

export const UPHOLD_TEXT = DECISION_LABEL.upheld
export const CORRECT_TEXT = DECISION_LABEL.corrected
export const REMATCH_TEXT = DECISION_LABEL.rematch
export const REASON_LABEL = "處理理由"
export const REASON_MAX_LENGTH = 1000
export const RESOLVED_TOAST = "已處理申訴。"
export const GO_TO_MATCHES_TEXT = "前往場次管理"
export const NO_VALID_TIME_TEXT =
  "這場目前沒有可選的時間。請先到場次管理把下一場改晚，再回來選擇重新比賽的時間。"
export const ADD_GAME_TEXT = "新增一局"
export const REMOVE_GAME_TEXT = "刪除最後一局"
const RESCHEDULE_NO_VALID_TIME = "RESCHEDULE_NO_VALID_TIME"
const NO_OPEN_APPEALS = "NO_OPEN_APPEALS"

/** 重賽時間範圍回傳這些原因時不能重新比賽：顯示說明、確認鈕停用。 */
export const REPLAY_BLOCKED_TEXT: Partial<
  Record<NonNullable<RescheduleInfo["reason"]>, string>
> = {
  match_not_reschedulable:
    "這場已不是判棄權的申訴中場次（可能已在其他分頁處理），不能重新比賽。請重新整理頁面查看最新狀態。",
  tournament_not_reschedulable: "賽事目前的狀態不能重新比賽。",
}

/** 重新比賽只用於判棄權（一方或雙方）的場次。 */
export function canReplay(group: Pick<AppealGroup, "outcome">): boolean {
  return group.outcome === "forfeit" || group.outcome === "double_forfeit"
}

/** 更正結果只用於正常完賽的場次。 */
export function canCorrect(group: Pick<AppealGroup, "outcome">): boolean {
  return group.outcome === "played"
}

function teamName(group: AppealGroup, side: "a" | "b"): string {
  const team = side === "a" ? group.team_a : group.team_b
  return team?.name ?? (side === "a" ? "A 隊" : "B 隊")
}

function appealCountText(group: AppealGroup): string {
  const open = group.appeals.filter((a) => a.status === "open").length
  return `這場的 ${open} 筆申訴會以相同的決定與理由一起結案。`
}

/** 目前的結果（比分、勝隊或棄權方），讓主辦方處理前先看清楚要維持或改掉的是什麼。 */
export function currentResultText(group: AppealGroup): string {
  const nameA = teamName(group, "a")
  const nameB = teamName(group, "b")
  const winner =
    group.winner_id === null
      ? null
      : group.winner_id === group.team_a?.id
        ? nameA
        : group.winner_id === group.team_b?.id
          ? nameB
          : null
  const won = winner ? `，${winner} 勝` : ""
  switch (group.outcome) {
    case "played":
      return `目前結果：${nameA} ${group.wins_a}：${group.wins_b} ${nameB}${won}。`
    case "forfeit": {
      const loser = winner === nameA ? nameB : winner === nameB ? nameA : null
      return loser ? `目前結果：${loser} 棄權${won}。` : "目前結果：一方棄權。"
    }
    case "double_forfeit":
      return "目前結果：雙方棄權。"
    default:
      return winner ? `目前結果：${winner} 勝。` : "目前結果：尚未登錄。"
  }
}

/** 對話框內文：先列目前結果，再寫這個動作的後果。 */
function describe(group: AppealGroup, consequence: string): ReactNode {
  return (
    <>
      <span data-slot="appeal-current-result" className="block font-medium">
        {currentResultText(group)}
      </span>
      <span className="block">{consequence}</span>
    </>
  )
}

/**
 * 送出處理；成功時 Toast 並重抓，失敗時重抓後拋出（對話框顯示伺服器訊息）。
 * `NO_OPEN_APPEALS`（例如另一個分頁已處理）時重抓後這一列不再有操作、對話框跟著卸載，
 * 所以另外以錯誤 Toast 顯示伺服器訊息，不會無聲消失。
 */
function useResolve(tournamentId: string, matchId: string) {
  const refetch = useRefetchAppeals(tournamentId)
  return async (body: AppealResolveIn) => {
    try {
      await resolveAppeals({ tournamentId, matchId, body })
    } catch (error) {
      const parsed = parseApiError(error)
      if (parsed.kind === "business" && parsed.code === NO_OPEN_APPEALS) {
        notifyError(error)
      }
      void refetch()
      throw error
    }
    notifySuccess(RESOLVED_TOAST)
    await refetch()
  }
}

type ResolveDialogProps = {
  title: string
  description: ReactNode
  /** 確認鈕重複動作名 */
  confirmLabel: string
  trigger: ReactNode
  open: boolean
  onOpenChange: (open: boolean) => void
  /** 理由以外的欄位（各局、時間） */
  children?: ReactNode
  /** 理由以外的欄位是否完整；不完整時確認鈕停用 */
  ready?: boolean
  onConfirm: (reason: string) => Promise<unknown>
  /** 錯誤訊息下方的額外內容（例如「前往場次管理」） */
  errorExtra?: (error: ApiError) => ReactNode
}

/**
 * 更正結果、重新比賽的確認對話框：與 `ConfirmDialog` 相同的寫法（標題寫動作、確認鈕
 * 重複動作名、理由必填），另外放入各局或時間欄位。送出中不能關閉；失敗時留在對話框。
 */
function ResolveDialog({
  title,
  description,
  confirmLabel,
  trigger,
  open,
  onOpenChange,
  children,
  ready = true,
  onConfirm,
  errorExtra,
}: ResolveDialogProps) {
  const reasonId = useId()
  const [reason, setReason] = useState("")
  const [error, setError] = useState<ApiError | null>(null)
  const [pending, setPending] = useState(false)

  const setOpen = (next: boolean) => {
    if (!next) {
      setReason("")
      setError(null)
    }
    onOpenChange(next)
  }

  const trimmed = reason.trim()
  const confirm = async () => {
    setError(null)
    setPending(true)
    try {
      await onConfirm(trimmed)
      setPending(false)
      setOpen(false)
    } catch (caught) {
      setPending(false)
      setError(parseApiError(caught))
    }
  }

  return (
    <AlertDialog
      open={open}
      onOpenChange={(next) => {
        if (!pending) setOpen(next)
      }}
    >
      <AlertDialogTrigger asChild>{trigger}</AlertDialogTrigger>
      <AlertDialogContent className="max-h-[90dvh] overflow-y-auto">
        <AlertDialogHeader>
          <AlertDialogTitle className="text-heading-md">
            {title}
          </AlertDialogTitle>
          <AlertDialogDescription className="text-body">
            {description}
          </AlertDialogDescription>
        </AlertDialogHeader>
        {error && (
          <Alert variant="destructive" className="rounded-md">
            <CircleAlertIcon />
            <AlertDescription className="flex flex-col items-start gap-1 text-destructive">
              <span>{getErrorMessage(error)}</span>
              {errorExtra?.(error)}
            </AlertDescription>
          </Alert>
        )}
        {children}
        <div className="flex flex-col gap-2">
          <Label htmlFor={reasonId}>{REASON_LABEL}</Label>
          <Textarea
            id={reasonId}
            value={reason}
            maxLength={REASON_MAX_LENGTH}
            disabled={pending}
            onChange={(event) => setReason(event.target.value)}
            className="min-h-24 break-words"
          />
          <p className="self-end text-caption text-muted-foreground">
            {reason.length}／{REASON_MAX_LENGTH}
          </p>
        </div>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={pending}>取消</AlertDialogCancel>
          <LoadingButton
            loading={pending}
            disabled={trimmed.length === 0 || !ready}
            onClick={confirm}
          >
            {confirmLabel}
          </LoadingButton>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

type DialogProps = { tournamentId: string; group: AppealGroup }

/** 維持原結果後的晉級：雙方棄權沒有勝隊，兩隊都不晉級。 */
export function upholdConsequenceText(
  group: Pick<AppealGroup, "outcome">,
): string {
  return group.outcome === "double_forfeit"
    ? "場次轉為已確認，雙方都不晉級。"
    : "場次轉為已確認，勝隊晉級。"
}

/** 「維持原結果」：沿用原結果確認並晉級。 */
export function UpholdAppealDialog({ tournamentId, group }: DialogProps) {
  const resolve = useResolve(tournamentId, group.match_id)
  return (
    <ConfirmDialog
      title={UPHOLD_TEXT}
      description={describe(
        group,
        `${matchLabel({ code: group.match_code, is_third_place: group.is_third_place })} 維持原本的結果，${upholdConsequenceText(group)}${appealCountText(group)}`,
      )}
      confirmLabel={UPHOLD_TEXT}
      reason={{ label: REASON_LABEL, maxLength: REASON_MAX_LENGTH }}
      onConfirm={(reason) =>
        resolve({ decision: "upheld", reason: reason ?? "" })
      }
      trigger={
        <Button variant="outline" size="sm">
          {UPHOLD_TEXT}
        </Button>
      }
    />
  )
}

// ---------------------------------------------------------------- 更正結果

/** 一局的草稿：win_loss 只有勝方；rounds 是兩個輸入框的文字。 */
type GameDraft = { winner: "a" | "b" | null; scoreA: string; scoreB: string }

const ROUND_PATTERN = /^\d{1,2}$/

function toDrafts(group: AppealGroup): GameDraft[] {
  return group.games.map((game) => ({
    winner: game.winner_side,
    scoreA: game.score_a?.toString() ?? "",
    scoreB: game.score_b?.toString() ?? "",
  }))
}

/** 草稿轉成 API 的各局；有任何一局不完整時回傳 null。 */
export function draftsToGames(
  scoreType: AppealGroup["score_type"],
  drafts: GameDraft[],
): GameScoreIn[] | null {
  if (drafts.length === 0) return null
  const games: GameScoreIn[] = []
  for (const draft of drafts) {
    if (scoreType === "win_loss") {
      if (draft.winner === null) return null
      games.push({ winner_side: draft.winner })
    } else {
      if (
        !ROUND_PATTERN.test(draft.scoreA) ||
        !ROUND_PATTERN.test(draft.scoreB)
      )
        return null
      games.push({
        score_a: Number(draft.scoreA),
        score_b: Number(draft.scoreB),
      })
    }
  }
  return games
}

function GamesEditor({
  group,
  drafts,
  onChange,
}: {
  group: AppealGroup
  drafts: GameDraft[]
  onChange: (drafts: GameDraft[]) => void
}) {
  const nameA = teamName(group, "a")
  const nameB = teamName(group, "b")
  const update = (index: number, patch: Partial<GameDraft>) =>
    onChange(drafts.map((d, i) => (i === index ? { ...d, ...patch } : d)))
  return (
    <fieldset className="flex flex-col gap-3">
      <legend className="mb-2 text-label">
        更正後的各局（BO{group.best_of}）
      </legend>
      {drafts.map((draft, index) => {
        const no = index + 1
        return (
          <div
            key={index}
            data-slot="correction-game"
            className="flex flex-wrap items-center gap-2"
          >
            <span className="w-14 shrink-0 text-body">第 {no} 局</span>
            {group.score_type === "win_loss" ? (
              (["a", "b"] as const).map((side) => (
                <Button
                  key={side}
                  type="button"
                  size="sm"
                  variant={draft.winner === side ? "default" : "outline"}
                  aria-pressed={draft.winner === side}
                  aria-label={`第 ${no} 局 ${side === "a" ? nameA : nameB} 勝`}
                  onClick={() => update(index, { winner: side })}
                  className="max-w-40 truncate"
                >
                  {side === "a" ? nameA : nameB} 勝
                </Button>
              ))
            ) : (
              <>
                <Input
                  type="number"
                  inputMode="numeric"
                  min={0}
                  max={99}
                  value={draft.scoreA}
                  aria-label={`第 ${no} 局 ${nameA} 回合數`}
                  onChange={(event) =>
                    update(index, { scoreA: event.target.value })
                  }
                  className="w-20"
                />
                <span aria-hidden>：</span>
                <Input
                  type="number"
                  inputMode="numeric"
                  min={0}
                  max={99}
                  value={draft.scoreB}
                  aria-label={`第 ${no} 局 ${nameB} 回合數`}
                  onChange={(event) =>
                    update(index, { scoreB: event.target.value })
                  }
                  className="w-20"
                />
              </>
            )}
          </div>
        )
      })}
      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={drafts.length >= group.best_of}
          onClick={() =>
            onChange([...drafts, { winner: null, scoreA: "", scoreB: "" }])
          }
        >
          {ADD_GAME_TEXT}
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={drafts.length === 0}
          onClick={() => onChange(drafts.slice(0, -1))}
        >
          {REMOVE_GAME_TEXT}
        </Button>
      </div>
    </fieldset>
  )
}

/** 「更正結果」：依比分型態重新輸入整組各局，系統重算勝隊後確認並晉級。 */
export function CorrectAppealDialog({ tournamentId, group }: DialogProps) {
  const [open, setOpen] = useState(false)
  const [drafts, setDrafts] = useState<GameDraft[]>(() => toDrafts(group))
  const resolve = useResolve(tournamentId, group.match_id)
  const games = draftsToGames(group.score_type, drafts)
  return (
    <ResolveDialog
      title={CORRECT_TEXT}
      description={describe(
        group,
        `重新輸入 ${matchLabel({ code: group.match_code, is_third_place: group.is_third_place })} 的各局，系統重算勝隊後場次轉為已確認並晉級。${appealCountText(group)}`,
      )}
      confirmLabel={CORRECT_TEXT}
      open={open}
      onOpenChange={(next) => {
        // 每次開啟都從目前的各局開始
        if (next) setDrafts(toDrafts(group))
        setOpen(next)
      }}
      ready={games !== null}
      onConfirm={(reason) =>
        resolve({ decision: "corrected", reason, games: games ?? [] })
      }
      trigger={
        <Button variant="outline" size="sm">
          {CORRECT_TEXT}
        </Button>
      }
    >
      <GamesEditor group={group} drafts={drafts} onChange={setDrafts} />
    </ResolveDialog>
  )
}

// ---------------------------------------------------------------- 重新比賽

function GoToMatches({ tournamentId }: { tournamentId: string }) {
  return (
    <Link
      to="/organizer/tournaments/$tournamentId/matches"
      params={{ tournamentId }}
      className="text-body text-primary underline-offset-4 hover:underline"
    >
      {GO_TO_MATCHES_TEXT}
    </Link>
  )
}

function ReplayTimeField({
  tournamentId,
  replayWindow,
  value,
  onChange,
}: {
  tournamentId: string
  replayWindow: UseQueryResult<RescheduleInfo, unknown>
  value: string
  onChange: (value: string) => void
}) {
  const inputId = useId()
  const info = replayWindow.data
  const earliest = info?.earliest ?? null
  const latest = info?.latest ?? null
  if (replayWindow.isError) {
    return (
      <p role="alert" className="text-body text-destructive">
        {getErrorMessage(parseApiError(replayWindow.error))}
      </p>
    )
  }
  const blocked = info?.reason ? REPLAY_BLOCKED_TEXT[info.reason] : undefined
  if (blocked) {
    return (
      <p role="alert" className="text-body text-destructive">
        {blocked}
      </p>
    )
  }
  return (
    <div className="flex flex-col gap-2">
      <Label htmlFor={inputId}>重新比賽的時間（台北時間）</Label>
      <Input
        id={inputId}
        type="datetime-local"
        value={value}
        min={earliest ? isoToTaipeiLocal(earliest) : undefined}
        max={latest ? isoToTaipeiLocal(latest) : undefined}
        onChange={(event) => onChange(event.target.value)}
      />
      {info?.reason === "no_valid_time" ? (
        <div className="flex flex-col items-start gap-1">
          <p role="alert" className="text-body text-destructive">
            {NO_VALID_TIME_TEXT}
          </p>
          <GoToMatches tournamentId={tournamentId} />
        </div>
      ) : earliest ? (
        <p className="text-caption text-muted-foreground">
          {latest
            ? `可選 ${formatMatchDateTime(earliest)}～${formatMatchDateTime(latest)}`
            : `${formatMatchDateTime(earliest)} 以後`}
        </p>
      ) : null}
    </div>
  )
}

/** 「重新比賽」：只出現在判棄權的場次；選新時間後場次回到待開打、重新報到與起算棄權。 */
export function RematchAppealDialog({ tournamentId, group }: DialogProps) {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [value, setValue] = useState("")
  const resolve = useResolve(tournamentId, group.match_id)
  // 對話框開啟時才查詢；每次開啟都取最新值（staleTime 0）
  const replayWindow = useQuery({
    ...replayWindowQueryOptions(tournamentId, group.match_id),
    enabled: open,
  })
  const reason = replayWindow.data?.reason
  const blocked = reason ? REPLAY_BLOCKED_TEXT[reason] !== undefined : false
  const iso = taipeiLocalToIso(value)
  return (
    <ResolveDialog
      title={REMATCH_TEXT}
      description={describe(
        group,
        `${matchLabel({ code: group.match_code, is_third_place: group.is_third_place })} 清除棄權結果與報到紀錄，回到待開打，兩隊依新時間重新報到。${appealCountText(group)}`,
      )}
      confirmLabel={REMATCH_TEXT}
      open={open}
      onOpenChange={(next) => {
        if (next) setValue("")
        setOpen(next)
      }}
      ready={iso !== null && !blocked}
      onConfirm={async (reason) => {
        try {
          await resolve({ decision: "rematch", reason, replay_at: iso })
        } catch (error) {
          // 範圍會隨時間與相鄰場次改變：任一 RESCHEDULE_* 409 後重抓範圍
          const parsed = parseApiError(error)
          if (
            parsed.kind === "business" &&
            parsed.code.startsWith("RESCHEDULE_")
          ) {
            void queryClient.invalidateQueries({
              queryKey: replayWindowQueryOptions(tournamentId, group.match_id)
                .queryKey,
            })
          }
          throw error
        }
      }}
      errorExtra={(error) =>
        error.kind === "business" && error.code === RESCHEDULE_NO_VALID_TIME ? (
          <GoToMatches tournamentId={tournamentId} />
        ) : null
      }
      trigger={
        <Button variant="outline" size="sm">
          {REMATCH_TEXT}
        </Button>
      }
    >
      {open && (
        <ReplayTimeField
          tournamentId={tournamentId}
          replayWindow={replayWindow}
          value={value}
          onChange={setValue}
        />
      )}
    </ResolveDialog>
  )
}
