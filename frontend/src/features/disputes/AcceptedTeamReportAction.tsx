import { useQuery } from "@tanstack/react-query"
import { useMemo, useState } from "react"
import { toast } from "sonner"

import type {
  RegistrationStatus,
  ReportableTeam,
  TournamentStatus,
} from "@/client"
import { Button } from "@/components/ui/button"
import { useIsSignedIn } from "@/features/identity/auth"
import {
  myTeamsQueryOptions,
  teamQueryOptions,
} from "@/features/registration/queries"
import { reportableTeamsQueryOptions } from "./queries"
import { ReportTeamDialog } from "./ReportTeamDialog"
import { REPORT_FILED_TOAST } from "./ReportTeamEntry"
import { useFileReport } from "./useFileReport"

// S2「正取隊伍」分頁每列的「檢舉」（Story 3.9）。資格判斷與 6.4 的 `ReportTeamEntry`
// 相同；不改 6.4 的檔案，所以查詢鏈在這裡重寫一份（query key 相同，快取共用）。

export const ROW_REPORT_TEXT = "檢舉"
export const ROW_REPORTED_TEXT = "已檢舉・處理中"

/** 可提出檢舉的報名狀態：待分配、正取、候補、已參賽（與 6.4 相同）。 */
const REPORTER_STATUSES: readonly RegistrationStatus[] = [
  "pending",
  "accepted",
  "waitlisted",
  "drawn",
]

const ENDED_STATUSES: readonly TournamentStatus[] = ["finished", "cancelled"]

const NO_TEAMS: ReadonlyMap<string, ReportableTeam> = new Map()

/**
 * 登入者在此賽事可檢舉的隊伍（以隊伍 id 查）。依序判斷，任一步不符或查詢未完成就回空的
 * Map：賽事未結束、已登入 → 我的隊伍裡有此賽事且報名已送出（四種狀態）→ 是隊長 →
 * `reportable-teams`。隊員不會呼叫 `reportable-teams`。
 */
export function useReportableTeamsById(
  tournamentId: string,
  tournamentStatus: TournamentStatus,
): ReadonlyMap<string, ReportableTeam> {
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
  const enabled = signedIn && !ended && isCaptain
  const reportable = useQuery({
    ...reportableTeamsQueryOptions(tournamentId),
    enabled,
  })
  const data = enabled ? reportable.data : undefined
  return useMemo(
    () =>
      data ? new Map(data.map((item) => [item.id, item] as const)) : NO_TEAMS,
    [data],
  )
}

type AcceptedTeamReportActionProps = {
  tournamentId: string
  /** 該列隊伍在 `reportable-teams` 裡的項目；不在（含自己的隊伍、不符資格）時為 undefined */
  team: ReportableTeam | undefined
}

/**
 * 一列的「檢舉」：該列不能檢舉時不顯示；已有處理中的檢舉時顯示「已檢舉・處理中」。
 * 按下開 S20，檢舉對象只有這一隊。
 */
export function AcceptedTeamReportAction({
  tournamentId,
  team,
}: AcceptedTeamReportActionProps) {
  const [open, setOpen] = useState(false)
  // 開啟時的隊伍：對話框開著時，送出後重新取得的資料可能讓這列不再可檢舉；仍保留對話框
  // （錯誤與輸入不會消失），使用者關閉後才依最新資料顯示
  const [dialogTeam, setDialogTeam] = useState<ReportableTeam | null>(null)
  const { fileReport, uploadProgress } = useFileReport(tournamentId)

  return (
    <>
      {team?.has_open_report ? (
        <span className="shrink-0 text-caption text-muted-foreground">
          {ROW_REPORTED_TEXT}
        </span>
      ) : team ? (
        <Button
          variant="outline"
          size="sm"
          className="shrink-0"
          onClick={() => {
            setDialogTeam(team)
            setOpen(true)
          }}
        >
          {ROW_REPORT_TEXT}
        </Button>
      ) : null}
      {dialogTeam ? (
        <ReportTeamDialog
          open={open}
          onOpenChange={setOpen}
          teams={[team ?? dialogTeam]}
          uploadProgress={uploadProgress}
          onSubmit={async (values) => {
            await fileReport(values)
            setOpen(false)
            toast.success(REPORT_FILED_TOAST)
          }}
        />
      ) : null}
    </>
  )
}
