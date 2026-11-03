import { useId } from "react"

import type { PublicTournament } from "@/client"
import { Countdown, type CountdownVariant } from "@/components/common/Countdown"
import { Button } from "@/components/ui/button"
import { formatMatchDateTime } from "@/features/competition/match-time"
import { useIsSignedIn } from "@/features/identity/auth"
import { CreateTeamEntry } from "@/features/registration/CreateTeamEntry"
import {
  formatInterval,
  formatRegistrationPeriod,
  TOURNAMENT_STATUS_LABEL,
} from "./status"

export const DRAW_PENDING_TEXT = "抽籤準備中"
/** 報名開始倒數歸零後、狀態轉為開放報名前的文字 */
export const REGISTRATION_OPENING_TEXT = "報名開放中 · 系統處理中"

const LAST_DAY_MS = 24 * 60 * 60 * 1000

/** 報名截止倒數：最後 24 小時改用 appeal（EXPERIENCE.md〈倒數與時間〉）。 */
export function registrationEndVariant(remainingMs: number): CountdownVariant {
  return remainingMs <= LAST_DAY_MS ? "appeal" : "muted"
}

type TournamentOverviewProps = {
  tournament: PublicTournament
  /** 倒數歸零後每 5 秒呼叫一次（最多 2 分鐘），用來重抓賽事 */
  onCountdownExpire: () => void
}

/** 尚未開放時登入者看到的「建立隊伍」：停用，寫開放報名時間。 */
function CreateTeamNotYetOpen({ opensAt }: { opensAt: string }) {
  const descriptionId = useId()
  return (
    <div className="flex flex-col items-start gap-1.5">
      <Button disabled aria-describedby={descriptionId}>
        建立隊伍
      </Button>
      <p id={descriptionId} className="text-caption text-muted-foreground">
        {formatMatchDateTime(opensAt)} 開放報名
      </p>
    </div>
  )
}

/** 依賽事狀態顯示的倒數與動作。 */
function StatusPanel({
  tournament,
  onCountdownExpire,
}: TournamentOverviewProps) {
  const signedIn = useIsSignedIn()

  switch (tournament.status) {
    case "upcoming":
      return (
        <div className="flex flex-col gap-4">
          <Countdown
            key={`upcoming-${tournament.registration_start}`}
            label="報名開始"
            deadline={tournament.registration_start}
            variant="muted"
            suffix="開放報名"
            expiredText={REGISTRATION_OPENING_TEXT}
            onExpire={onCountdownExpire}
          />
          {signedIn ? (
            <CreateTeamNotYetOpen opensAt={tournament.registration_start} />
          ) : null}
        </div>
      )
    case "open":
      return (
        <div className="flex flex-col gap-4">
          <Countdown
            key={`open-${tournament.registration_end}`}
            label="報名截止"
            deadline={tournament.registration_end}
            variant={registrationEndVariant}
            onExpire={onCountdownExpire}
          />
          <CreateTeamEntry tournamentId={tournament.id} />
        </div>
      )
    case "closed":
      return (
        <p className="text-body text-muted-foreground">{DRAW_PENDING_TEXT}</p>
      )
    default:
      return null
  }
}

function Field({ term, children }: { term: string; children: string }) {
  return (
    <div className="grid min-w-0 grid-cols-[5.5rem_minmax(0,1fr)] gap-2">
      <dt className="text-muted-foreground">{term}</dt>
      <dd className="min-w-0 break-words">{children}</dd>
    </div>
  )
}

/** S2「總覽」分頁：依狀態的倒數與動作＋賽事資訊。 */
export function TournamentOverview({
  tournament,
  onCountdownExpire,
}: TournamentOverviewProps) {
  return (
    <div className="flex flex-col gap-6">
      <StatusPanel
        tournament={tournament}
        onCountdownExpire={onCountdownExpire}
      />
      <dl className="flex flex-col gap-2 rounded-lg border bg-card p-4 text-body">
        <Field term="狀態">{TOURNAMENT_STATUS_LABEL[tournament.status]}</Field>
        <Field term="遊戲">{tournament.game_name}</Field>
        <Field term="名額">{`${tournament.capacity} 隊`}</Field>
        <Field term="報名期間">{formatRegistrationPeriod(tournament)}</Field>
        <Field term="開賽時間">
          {formatMatchDateTime(tournament.start_at)}
        </Field>
        <Field term="每輪間隔">
          {formatInterval(tournament.round_interval_minutes)}
        </Field>
      </dl>
    </div>
  )
}
