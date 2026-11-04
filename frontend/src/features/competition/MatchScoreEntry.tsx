import { useQuery } from "@tanstack/react-query"
import type { ReactNode } from "react"

import {
  CompetitionService,
  type GameScoreIn,
  type PublicMatchDetail,
  type ScoreEntryState,
} from "@/client"
import { useIsSignedIn } from "@/features/identity/auth"
import { parseApiError } from "@/lib/api-error"
import { notifyError } from "@/lib/feedback"
import { matchQueryKey, matchVersion, samePlaceholder } from "./match-source"
import {
  type GameInput,
  ScoreEntryPanel,
  type ScoreReason,
} from "./ScoreEntryPanel"

/** 寫入 API 的比分規則錯誤碼 → Score entry panel 的原因代碼（contracts/competition.md 5.3、5.4） */
export const SCORE_ERROR_REASONS: Readonly<Record<string, ScoreReason>> = {
  SCORE_TIE: "tie",
  SCORE_INVALID: "invalid_score",
  SERIES_DECIDED: "series_decided",
  REDUNDANT_GAMES: "redundant_games",
  INVALID_GAME_NO: "invalid_game_no",
  NOT_LAST_GAME: "not_last_game",
  SERIES_NOT_DECIDED: "not_decided",
}

/** 比分規則錯誤回傳原因代碼；其他錯誤回傳 null */
export function scoreErrorReason(error: unknown): ScoreReason | null {
  const apiError = parseApiError(error)
  if (apiError.kind !== "business") return null
  return SCORE_ERROR_REASONS[apiError.code] ?? null
}

/**
 * 記分者看得到面板的情況：可以登錄、等待報到或兩隊確定、已送出（唯讀）。
 * 判棄權（沒有送出者）、場次已取消、賽事不再接受比分且沒有送出紀錄時不顯示，左欄照常是公開各局列表。
 */
function showsPanel(state: ScoreEntryState): boolean {
  if (!state.is_scorer || !state.series) return false
  if (state.submitted_by_name && state.submitted_at) return true
  return (
    state.reason == null ||
    state.reason === "check_in_incomplete" ||
    state.reason === "teams_pending"
  )
}

function gameBody(input: GameInput): GameScoreIn {
  return "winner" in input
    ? { winner_side: input.winner }
    : { score_a: input.scoreA, score_b: input.scoreB }
}

type UseMatchScoreEntryOptions = {
  detail: PublicMatchDetail
  /** 重抓這一場的所有資料（公開單場與面板狀態），完成後才 resolve */
  refresh: () => Promise<unknown>
}

/**
 * S4 Score entry panel 的資料轉接：登入者才查詢；`is_scorer` 為 true 時回傳面板，否則回傳 null
 * （此時左欄顯示公開各局列表）。寫入成功後重抓再 resolve；比分規則錯誤轉成面板的原因代碼；
 * 其他錯誤先顯示 Toast、重抓資料再 reject。
 */
export function useMatchScoreEntry({
  detail,
  refresh,
}: UseMatchScoreEntryOptions): ReactNode {
  const signedIn = useIsSignedIn()
  const path = { tournament_id: detail.tournament.id, match_id: detail.id }
  const query = useQuery({
    // 帶場次版本（updated_at＋兩隊報到時間）：場次有變動（報到、登錄、送出、指派裁判）就重抓
    queryKey: [
      ...matchQueryKey(detail.tournament.id, detail.id),
      "score-entry",
      ...matchVersion(detail),
    ],
    queryFn: async () =>
      (await CompetitionService.readScoreEntry({ path })).data,
    enabled: signedIn,
    placeholderData: samePlaceholder(detail.id),
    retry: false,
  })
  const state = signedIn ? query.data : undefined
  if (!state || !showsPanel(state) || !state.series) return null
  const series = state.series

  async function write(action: () => Promise<unknown>) {
    try {
      await action()
    } catch (error) {
      const reason = scoreErrorReason(error)
      if (reason !== null) return reason
      notifyError(error)
      // 例如已送出（RESULT_ALREADY_SUBMITTED）：畫面可能已過時，重抓後再讓面板恢復
      await refresh().catch(() => undefined)
      throw error
    }
    await refresh()
    return null
  }

  return (
    <ScoreEntryPanel
      teamA={detail.team_a?.name ?? detail.source_a ?? "待定"}
      teamB={detail.team_b?.name ?? detail.source_b ?? "待定"}
      scoreType={detail.score_type}
      bothCheckedIn={
        state.reason !== "check_in_incomplete" &&
        state.reason !== "teams_pending"
      }
      games={(state.games ?? []).map((game) => ({
        winner: game.winner_side,
        scoreA: game.score_a,
        scoreB: game.score_b,
      }))}
      series={{
        winsA: series.wins_a,
        winsB: series.wins_b,
        winner: series.winner,
        canSubmit: series.can_submit,
        winsNeeded: series.wins_needed,
      }}
      submission={
        state.submitted_by_name && state.submitted_at
          ? {
              submittedBy: state.submitted_by_name,
              submittedAt: state.submitted_at,
            }
          : null
      }
      onRecord={(gameNo, input) =>
        write(() =>
          CompetitionService.recordGame({
            path: { ...path, game_no: gameNo },
            body: gameBody(input),
          }),
        )
      }
      onDelete={(gameNo) =>
        write(() =>
          CompetitionService.deleteGame({ path: { ...path, game_no: gameNo } }),
        )
      }
      onSubmit={() => write(() => CompetitionService.submitResult({ path }))}
    />
  )
}
