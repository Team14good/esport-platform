import { useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { toast } from "sonner"

import type { RegistrationStatus, TournamentStatus } from "@/client"
import { Button } from "@/components/ui/button"
import { useIsSignedIn } from "@/features/identity/auth"
import {
  myTeamsQueryOptions,
  teamQueryOptions,
} from "@/features/registration/queries"
import { reportableTeamsQueryOptions } from "./queries"
import { ReportTeamDialog } from "./ReportTeamDialog"
import { useFileReport } from "./useFileReport"

export const REPORT_ENTRY_TEXT = "檢舉隊伍"
export const REPORT_FILED_TOAST = "已送出檢舉"

/** 可提出檢舉的報名狀態：待分配、正取、候補、已參賽。 */
const REPORTER_STATUSES: readonly RegistrationStatus[] = [
  "pending",
  "accepted",
  "waitlisted",
  "drawn",
]

const ENDED_STATUSES: readonly TournamentStatus[] = ["finished", "cancelled"]

type ReportTeamEntryProps = {
  tournamentId: string
  tournamentStatus: TournamentStatus
}

/**
 * S2 總覽的「檢舉隊伍」（Story 6.4）。依序判斷，任一步不符或查詢未完成就不顯示：
 * 賽事未結束、已登入 → 我的隊伍裡有此賽事且報名已送出（四種狀態）→ 是隊長
 * （S17 的 `my_role`）→ 可檢舉的隊伍不為空。隊員不會呼叫 `reportable-teams`。
 */
export function ReportTeamEntry({
  tournamentId,
  tournamentStatus,
}: ReportTeamEntryProps) {
  const [open, setOpen] = useState(false)
  const signedIn = useIsSignedIn()
  const ended = ENDED_STATUSES.includes(tournamentStatus)
  const myTeams = useQuery({
    ...myTeamsQueryOptions(),
    enabled: signedIn && !ended,
  })
  const myTeam = myTeams.data?.find(
    (card) =>
      card.tournament_id === tournamentId &&
      REPORTER_STATUSES.includes(card.registration_status),
  )
  const team = useQuery({
    ...teamQueryOptions(myTeam?.team_id ?? ""),
    enabled: signedIn && !ended && myTeam !== undefined,
  })
  const isCaptain = myTeam !== undefined && team.data?.my_role === "captain"
  const reportable = useQuery({
    ...reportableTeamsQueryOptions(tournamentId),
    enabled: signedIn && !ended && isCaptain,
  })
  const { fileReport, uploadProgress } = useFileReport(tournamentId)

  const eligible =
    signedIn &&
    !ended &&
    isCaptain &&
    reportable.data !== undefined &&
    reportable.data.length > 0
  // 對話框開著時，送出被拒後重新取得的資料可能讓入口不再符合條件；仍保留對話框
  // （錯誤與輸入不會消失），使用者關閉後入口才隱藏
  if (!eligible && !open) return null

  return (
    <div className="flex flex-col items-start">
      {eligible && (
        <Button variant="outline" onClick={() => setOpen(true)}>
          {REPORT_ENTRY_TEXT}
        </Button>
      )}
      <ReportTeamDialog
        open={open}
        onOpenChange={setOpen}
        teams={reportable.data ?? []}
        uploadProgress={uploadProgress}
        onSubmit={async (values) => {
          await fileReport(values)
          setOpen(false)
          toast.success(REPORT_FILED_TOAST)
        }}
      />
    </div>
  )
}
