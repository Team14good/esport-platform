import { useQuery, useQueryClient } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import { ChevronRightIcon } from "lucide-react"
import { useState } from "react"

import type { MyTeamCard, NextMatch } from "@/client"
import { Countdown } from "@/components/common/Countdown"
import { checkInCountdownPhase } from "./MatchCheckIn"
import { formatMatchDateTime } from "./match-time"
import {
  nextMatchesQueryKey,
  nextMatchesQueryOptions,
} from "./next-match-queries"

export const NEXT_MATCH_TEXT = "下一場"
export const PENDING_OPPONENT_TEXT = "待定"
export const LIVE_TEXT = "比賽進行中"
export const AWAITING_RESULT_TEXT = "等待結果確認"

/** 「8 強 · M3」；季軍賽只寫「季軍賽」（與 S4 Match header 相同）。 */
function roundText(match: NextMatch): string {
  return match.is_third_place
    ? match.round_name
    : `${match.round_name} · ${match.code}`
}

/** 對手那一方：本隊在 a 方時對手是 b 方，反之亦然。 */
function opponentOf(match: NextMatch, teamId: string) {
  const mineIsA = match.team_a?.id === teamId
  return {
    team: mineIsA ? match.team_b : match.team_a,
    source: mineIsA ? match.source_b : match.source_a,
  }
}

/**
 * 右側的狀態：待開打顯示報到倒數（對手未定時只有「報到開放」）；
 * 進行中「比賽進行中」；申訴期、申訴中「等待結果確認」。
 */
function NextMatchStatus({
  match,
  opponentPending,
}: {
  match: NextMatch
  opponentPending: boolean
}) {
  // 倒數歸零時重新 render，讓階段換到下一段（同 S4 Check-in panel），並重抓下一場
  const [, setExpiredCount] = useState(0)
  const queryClient = useQueryClient()
  if (match.status === "live") {
    return <span className="text-label text-status-live">{LIVE_TEXT}</span>
  }
  if (match.status === "appeal_window" || match.status === "appealed") {
    return (
      <span className="text-label text-muted-foreground">
        {AWAITING_RESULT_TEXT}
      </span>
    )
  }
  if (match.status !== "scheduled") return null
  const phase = checkInCountdownPhase({
    opensAt: match.check_in_opens_at,
    scheduledAt: match.scheduled_at,
    forfeitDeadline: match.forfeit_deadline ?? null,
    now: Date.now(),
  })
  // 對手未定時還不能報到，只倒數到報到開放
  if (phase === null || (opponentPending && phase.variant !== "muted")) {
    return null
  }
  return (
    <Countdown
      label={phase.label}
      deadline={phase.deadline}
      variant={phase.variant}
      suffix={phase.suffix}
      onExpire={() => {
        setExpiredCount((count) => count + 1)
        void queryClient.invalidateQueries({ queryKey: nextMatchesQueryKey })
      }}
      className="w-full sm:w-56"
    />
  )
}

/**
 * S12 一支已參賽隊伍的下一場（UX-DR37）：對手、時間與報到倒數，整列連到該場 S4。
 * 放在 Registration status card 下方（同一個 `<li>`），不巢狀在卡片的連結裡。
 */
export function NextMatchRow({
  tournamentId,
  teamId,
  match,
}: {
  tournamentId: string
  teamId: string
  match: NextMatch
}) {
  const opponent = opponentOf(match, teamId)
  const opponentPending = opponent.team === null || opponent.team === undefined
  return (
    <Link
      to="/tournaments/$tournamentId/matches/$matchId"
      params={{ tournamentId, matchId: match.id }}
      className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border bg-card px-4 py-3 outline-none transition-colors hover:bg-accent focus-visible:ring-[3px] focus-visible:ring-ring/50"
    >
      <span className="flex min-w-0 flex-1 flex-col gap-1">
        <span className="text-caption text-muted-foreground">
          {roundText(match)}
        </span>
        <span className="break-words text-body">
          {NEXT_MATCH_TEXT} vs{" "}
          <span className="font-semibold">
            {opponent.team?.name ?? PENDING_OPPONENT_TEXT}
          </span>{" "}
          ·{" "}
          <time dateTime={match.scheduled_at} className="whitespace-nowrap">
            {formatMatchDateTime(match.scheduled_at)}
          </time>
        </span>
        {opponentPending && opponent.source ? (
          <span className="text-caption text-muted-foreground">
            對手：{opponent.source}
          </span>
        ) : null}
      </span>
      <NextMatchStatus match={match} opponentPending={opponentPending} />
      <ChevronRightIcon
        aria-hidden="true"
        className="size-4 shrink-0 text-muted-foreground"
      />
    </Link>
  )
}

/**
 * S12 卡片下方的插槽內容：只有已參賽的隊伍查詢下一場（所有卡片共用同一個查詢）。
 * 查詢失敗或沒有下一場（已淘汰、賽事已結束）時不顯示，不影響卡片。
 */
export function MyTeamNextMatch({ card }: { card: MyTeamCard }) {
  const drawn = card.registration_status === "drawn"
  const nextMatches = useQuery({ ...nextMatchesQueryOptions(), enabled: drawn })
  if (!drawn || !nextMatches.data) return null
  const match = nextMatches.data.find((m) => m.team_id === card.team_id)
  if (!match) return null
  return (
    <NextMatchRow
      tournamentId={card.tournament_id}
      teamId={card.team_id}
      match={match}
    />
  )
}
