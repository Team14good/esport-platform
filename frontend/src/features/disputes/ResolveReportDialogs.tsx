import type { ReportRead, ReportResolveIn } from "@/client"
import { ConfirmDialog } from "@/components/common/ConfirmDialog"
import { Button } from "@/components/ui/button"
import { notifySuccess } from "@/lib/feedback"
import { resolveReport, useRefetchReports } from "./organizer-queries"

export const DISMISS_TEXT = "駁回檢舉"
export const DISQUALIFY_TEXT = "取消資格"
export const RECORD_SUBSTANTIATED_TEXT = "記錄屬實"
export const REPORT_REASON_LABEL = "處理理由"
export const REPORT_REASON_MAX_LENGTH = 1000
export const REPORT_RESOLVED_TOAST = "已處理檢舉。"

const REASON = {
  label: REPORT_REASON_LABEL,
  maxLength: REPORT_REASON_MAX_LENGTH,
}

/** 送出處理；成功時 Toast 並重抓，失敗時重抓後拋出（對話框顯示伺服器訊息）。 */
function useResolveReport(tournamentId: string, reportId: string) {
  const refetch = useRefetchReports(tournamentId)
  return async (body: ReportResolveIn) => {
    try {
      await resolveReport({ reportId, body })
    } catch (error) {
      void refetch()
      throw error
    }
    notifySuccess(REPORT_RESOLVED_TOAST)
    await refetch()
  }
}

type DialogProps = { tournamentId: string; report: ReportRead }

/** 駁回檢舉：只結案，被檢舉隊伍的報名與對戰表不變。 */
export function DismissReportDialog({ tournamentId, report }: DialogProps) {
  const resolve = useResolveReport(tournamentId, report.id)
  return (
    <ConfirmDialog
      title={DISMISS_TEXT}
      description={`駁回後這筆檢舉結案，${report.reported_team_name} 的報名與對戰表都不變。`}
      confirmLabel={DISMISS_TEXT}
      reason={REASON}
      onConfirm={(reason) =>
        resolve({ substantiated: false, reason: reason ?? "" })
      }
      trigger={
        <Button variant="outline" size="sm">
          {DISMISS_TEXT}
        </Button>
      }
    />
  )
}

/**
 * 檢舉屬實：賽事未結束時「取消資格」（destructive，改報名與對戰表）；
 * 賽事已結束或已取消時「記錄屬實」，只記錄、不改對戰表與名次。
 */
export function SubstantiateReportDialog({
  tournamentId,
  report,
  tournamentEnded,
}: DialogProps & {
  /** 賽事是否已結束或已取消；賽事狀態尚未載入或載入失敗時為 null，按鈕停用 */
  tournamentEnded: boolean | null
}) {
  const resolve = useResolveReport(tournamentId, report.id)
  const name = report.reported_team_name
  const label = tournamentEnded ? RECORD_SUBSTANTIATED_TEXT : DISQUALIFY_TEXT
  const description = tournamentEnded
    ? `賽事已結束或已取消，只記錄這筆檢舉屬實，不改對戰表與名次，${name} 的報名也不變。`
    : `${name} 的報名改為取消資格，對戰表依規則調整：進行中、申訴期或申訴中的場次直接判對手獲勝；待開打的場次可能由最近一場輸給 ${name} 的隊伍頂替，否則判對手獲勝。受影響場次的未結案申訴會一併結案。對 ${name} 的其他未結案檢舉也會一起結案為屬實。取消資格後無法復原。`
  return (
    <ConfirmDialog
      title={
        tournamentEnded ? RECORD_SUBSTANTIATED_TEXT : `取消 ${name} 的資格`
      }
      description={description}
      confirmLabel={label}
      destructive={!tournamentEnded}
      reason={REASON}
      onConfirm={(reason) =>
        resolve({ substantiated: true, reason: reason ?? "" })
      }
      trigger={
        <Button
          variant={tournamentEnded ? "outline" : "destructive"}
          size="sm"
          disabled={tournamentEnded === null}
        >
          {label}
        </Button>
      }
    />
  )
}
