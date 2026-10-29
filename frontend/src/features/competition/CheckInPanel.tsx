import { type ReactNode, useId, useRef, useState } from "react"

import { FormErrorAlert } from "@/components/common/FormErrorAlert"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { LoadingButton } from "@/components/ui/loading-button"
import { type ApiError, parseApiError } from "@/lib/api-error"
import { cn } from "@/lib/utils"
import { formatClock, formatMatchDateTime } from "./match-time"

// 與後端 checkin.py 的 CheckInReason 一致；第二階段改用產生的 client 型別
export type CheckInReason =
  | "teams_pending"
  | "already_checked_in"
  | "too_early"
  | "closed"

export type CheckInSide = "a" | "b"

export type CheckInTeam = {
  id: string
  name: string
  /** 報到時間（ISO）；尚未報到為 null */
  checkedInAt: string | null
}

type CheckInPanelProps = {
  /** 兩隊；對手尚未確定的一側為 null（顯示「待定」） */
  teams: Record<CheckInSide, CheckInTeam | null>
  /** 目前使用者是哪一隊的隊長；觀眾、裁判等為 null（不顯示按鈕） */
  ownSide: CheckInSide | null
  /** 場次是否為「待開打」；不是時面板收起，只留兩隊報到時間 */
  isScheduled: boolean
  /** 兩隊是否尚未都確定；所有人都看到面板停用與說明（reason 只對本隊隊長） */
  teamsPending: boolean
  /** 伺服器判定本隊不能報到的原因；可報到為 null */
  reason: CheckInReason | null
  /** 報到開放時間（ISO），用於「{絕對時間} 起可報到」 */
  opensAt: string
  /** 倒數插槽（Countdown 屬於 Epic 2，由呼叫端傳入） */
  countdown?: ReactNode
  /**
   * 按下「報到」時呼叫；完成前按鈕停用。失敗時拋錯或回傳錯誤訊息。
   * 成功後按鈕的去留由新的 reason 或報到時間決定，所以呼叫端應在重新取得場次資料後才 resolve。
   */
  onCheckIn: () => Promise<string | undefined> | Promise<void>
}

const SIDES: CheckInSide[] = ["a", "b"]
const TEAMS_PENDING_TEXT = "對手確定後才能報到"
const UNKNOWN_REASON_TEXT = "目前無法報到，請重新整理頁面"

function reasonText(reason: CheckInReason, opensAt: string): string | null {
  switch (reason) {
    case "too_early":
      return `${formatMatchDateTime(opensAt)} 起可報到`
    case "closed":
      return "已截止"
    // 兩隊未確定的說明放在兩隊下方，所有人都看得到
    case "teams_pending":
    case "already_checked_in":
      return null
    default: {
      // 後端新增原因代碼而前端尚未跟上時：按鈕仍停用，至少給一句說明
      const unknown: never = reason
      void unknown
      return UNKNOWN_REASON_TEXT
    }
  }
}

/** S4 Check-in panel：兩隊報到狀態＋本隊的「報到」按鈕。能不能報到只照呼叫端傳入的 reason 顯示。 */
export function CheckInPanel({
  teams,
  ownSide,
  isScheduled,
  teamsPending,
  reason,
  opensAt,
  countdown,
  onCheckIn,
}: CheckInPanelProps) {
  const [pending, setPending] = useState(false)
  // 錯誤記下當時的狀態；重新取得資料後狀態變了，舊錯誤就不再顯示
  const stateKey = `${isScheduled}|${teamsPending}|${reason}`
  const [error, setError] = useState<{ key: string; error: ApiError } | null>(
    null,
  )
  // state 要等重新 render 才生效；用 ref 擋住同一個 tick 內的第二次點擊
  const pendingRef = useRef(false)
  const describedById = useId()

  async function handleCheckIn() {
    if (pendingRef.current) return
    pendingRef.current = true
    setPending(true)
    setError(null)
    try {
      const message = await onCheckIn()
      if (typeof message === "string" && message !== "") {
        setError({ key: stateKey, error: { kind: "unknown", message } })
      }
    } catch (err) {
      setError({ key: stateKey, error: parseApiError(err) })
    } finally {
      pendingRef.current = false
      setPending(false)
    }
  }

  const panelDisabled =
    isScheduled && (teamsPending || reason === "teams_pending")
  const ownTeam = ownSide ? teams[ownSide] : null
  // 報到時間已回來但 reason 還沒更新時，也視為已報到
  const ownCheckedIn =
    reason === "already_checked_in" || Boolean(ownTeam?.checkedInAt)
  const ownReasonText = reason ? reasonText(reason, opensAt) : null
  const hasDescription = panelDisabled || ownReasonText !== null

  const action =
    isScheduled && ownSide !== null && ownTeam !== null && !ownCheckedIn ? (
      <div className="flex flex-col gap-2">
        <LoadingButton
          size="lg"
          className="h-touch-target w-full"
          disabled={reason !== null || panelDisabled}
          loading={pending}
          aria-busy={pending}
          aria-describedby={hasDescription ? describedById : undefined}
          onClick={handleCheckIn}
        >
          報到
        </LoadingButton>
        {!panelDisabled && ownReasonText && (
          <p id={describedById} className="text-sm text-muted-foreground">
            {ownReasonText}
          </p>
        )}
        <FormErrorAlert error={error?.key === stateKey ? error.error : null} />
      </div>
    ) : null
  const countdownSlot = isScheduled ? countdown : null

  return (
    <Card className="gap-4">
      <CardHeader>
        <CardTitle>
          <h2>報到</h2>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <ul
          aria-disabled={panelDisabled ? "true" : undefined}
          className={cn(
            "grid gap-4 sm:grid-cols-2",
            // 兩隊尚未確定：整個面板停用
            panelDisabled && "opacity-60",
          )}
        >
          {SIDES.map((side) => {
            const team = teams[side]
            return (
              <li key={side} className="flex flex-col gap-3">
                {team ? (
                  <div>
                    <p className="font-medium">{team.name}</p>
                    {team.checkedInAt ? (
                      <p className="text-sm text-status-confirmed">
                        已報到 {formatClock(team.checkedInAt)}
                      </p>
                    ) : (
                      <p className="text-sm text-muted-foreground">未報到</p>
                    )}
                  </div>
                ) : (
                  <p className="font-medium text-muted-foreground">待定</p>
                )}
                {side === ownSide && action}
                {side === ownSide && countdownSlot}
              </li>
            )
          })}
        </ul>
        {panelDisabled && (
          <p id={describedById} className="text-sm text-muted-foreground">
            {TEAMS_PENDING_TEXT}
          </p>
        )}
        {ownSide === null && countdownSlot}
      </CardContent>
    </Card>
  )
}
