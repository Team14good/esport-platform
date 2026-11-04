import { useQuery } from "@tanstack/react-query"
import { useState } from "react"

import { CompetitionService, type PublicMatchDetail } from "@/client"
import { Countdown, type CountdownVariant } from "@/components/common/Countdown"
import { useIsSignedIn } from "@/features/identity/auth"
import { CheckInPanel } from "./CheckInPanel"
import { matchQueryKey, matchVersion, samePlaceholder } from "./match-source"

/** 本機已過開放時間、伺服器仍回 too_early 時的重抓間隔 */
export const TOO_EARLY_RETRY_MS = 5000

/**
 * 報到狀態查詢的重抓間隔：本機時間已過 `opens_at`、伺服器仍回 `too_early`
 * （裝置時鐘比伺服器快）時每 5 秒重抓，直到伺服器放行；其他情況不定時重抓。
 */
export function tooEarlyRetryInterval(
  data: { reason?: string | null; opens_at: string } | undefined,
  now: number,
): number | false {
  return data?.reason === "too_early" && now >= Date.parse(data.opens_at)
    ? TOO_EARLY_RETRY_MS
    : false
}

/** 報到開放時間＝預定開始前 30 分鐘（contracts/competition.md `CheckInStatus.opens_at`）；未登入時沒有狀態查詢，用這個推算 */
export const CHECK_IN_LEAD_MS = 30 * 60 * 1000

export type CheckInCountdownPhase = {
  label: string
  deadline: string
  variant: CountdownVariant
  suffix: string
}

/**
 * 報到倒數的階段（EXPERIENCE.md〈倒數與時間〉）：
 * - 開放前：「報到開放」→ 開放時間（muted）
 * - 開放後：「距預定開始」→ 預定時間（live）
 * - 過預定時間：「棄權期限」→ 棄權期限（appeal）；沒有棄權期限時不顯示倒數
 */
export function checkInCountdownPhase({
  opensAt,
  scheduledAt,
  forfeitDeadline,
  now,
}: {
  opensAt: string
  scheduledAt: string
  forfeitDeadline: string | null
  now: number
}): CheckInCountdownPhase | null {
  if (now < Date.parse(opensAt)) {
    return {
      label: "報到開放",
      deadline: opensAt,
      variant: "muted",
      suffix: "起可報到",
    }
  }
  if (now < Date.parse(scheduledAt)) {
    return {
      label: "距預定開始",
      deadline: scheduledAt,
      variant: "live",
      suffix: "預定開始",
    }
  }
  if (forfeitDeadline !== null && now < Date.parse(forfeitDeadline)) {
    return {
      label: "棄權期限",
      deadline: forfeitDeadline,
      variant: "appeal",
      suffix: "截止",
    }
  }
  return null
}

/**
 * 報到面板的去留：待開打一律顯示（隊伍未定時面板自己停用並說明）；
 * 離開待開打後只在兩隊都有隊伍時留下報到時間。已取消的季軍賽、輪空直接確認的場次沒有報到可看。
 */
export function showsCheckIn(detail: PublicMatchDetail): boolean {
  if (detail.status === "scheduled") return true
  return detail.team_a !== null && detail.team_b !== null
}

type MatchCheckInProps = {
  detail: PublicMatchDetail
  /** 重抓這一場的所有資料（公開單場與面板狀態），完成後才 resolve */
  refresh: () => Promise<unknown>
}

/**
 * S4 Check-in panel 的資料轉接：所有人都看得到兩隊報到狀態（公開單場的 `check_in_*_at`）；
 * 只有登入者才查詢自己的報到狀態（`side`、`reason`、`opens_at`），未登入不呼叫需登入的 API。
 */
export function MatchCheckIn({ detail, refresh }: MatchCheckInProps) {
  const signedIn = useIsSignedIn()
  const tournamentId = detail.tournament.id
  const matchId = detail.id
  const status = useQuery({
    // 帶場次版本（updated_at＋兩隊報到時間）：場次有變動（報到、改期、對手確定）就重抓
    queryKey: [
      ...matchQueryKey(tournamentId, matchId),
      "check-in",
      ...matchVersion(detail),
    ],
    queryFn: async () =>
      (
        await CompetitionService.readCheckInStatus({
          path: { tournament_id: tournamentId, match_id: matchId },
        })
      ).data,
    enabled: signedIn,
    placeholderData: samePlaceholder(matchId),
    retry: false,
    // 裝置時鐘比伺服器快時，「報到開放」倒數歸零那次重抓仍可能拿到 too_early；
    // 本機時間已過開放時間卻還是 too_early 時，每 5 秒重抓直到伺服器放行
    refetchInterval: (query) =>
      tooEarlyRetryInterval(query.state.data, Date.now()),
  })
  const checkIn = signedIn ? status.data : undefined
  // 倒數歸零時重新 render，讓階段換到下一段；階段依每次 render 當下的時間決定，
  // 不會因為頁面開了很久才湊齊兩隊而用到舊時間（歸零前不需要每秒重新 render）
  const [, setExpiredCount] = useState(0)
  const now = Date.now()

  const teamsPending = detail.team_a === null || detail.team_b === null
  const isScheduled = detail.status === "scheduled"
  const opensAt =
    checkIn?.opens_at ??
    new Date(Date.parse(detail.scheduled_at) - CHECK_IN_LEAD_MS).toISOString()
  // 過了預定時間改倒數棄權期限（公開單場的 `forfeit_deadline`，只在待開打時有值）；沒有值就不顯示倒數
  const phase =
    isScheduled && !teamsPending
      ? checkInCountdownPhase({
          opensAt,
          scheduledAt: detail.scheduled_at,
          forfeitDeadline: detail.forfeit_deadline ?? null,
          now,
        })
      : null

  async function handleCheckIn() {
    await CompetitionService.checkIn({
      path: { tournament_id: tournamentId, match_id: matchId },
    })
    await refresh()
  }

  return (
    <CheckInPanel
      teams={{
        a: detail.team_a
          ? { ...detail.team_a, checkedInAt: detail.check_in_a_at ?? null }
          : null,
        b: detail.team_b
          ? { ...detail.team_b, checkedInAt: detail.check_in_b_at ?? null }
          : null,
      }}
      ownSide={checkIn?.side ?? null}
      isScheduled={isScheduled}
      teamsPending={teamsPending}
      reason={checkIn?.reason ?? null}
      opensAt={opensAt}
      countdown={
        phase ? (
          <Countdown
            label={phase.label}
            deadline={phase.deadline}
            variant={phase.variant}
            suffix={phase.suffix}
            onExpire={() => {
              setExpiredCount((count) => count + 1)
              void refresh()
            }}
          />
        ) : undefined
      }
      onCheckIn={handleCheckIn}
    />
  )
}
