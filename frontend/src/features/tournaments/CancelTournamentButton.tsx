import { useState } from "react"

import type { TournamentRead } from "@/client"
import { ConfirmDialog } from "@/components/common/ConfirmDialog"
import { Button } from "@/components/ui/button"
import { useCancelTournament } from "./organizer-queries"

export const CANCEL_TOURNAMENT_TEXT = "取消賽事"
/** 對話框的關閉鈕：不用「取消」，免得和「取消賽事」混淆 */
export const KEEP_TOURNAMENT_TEXT = "保留賽事"
export const CANCEL_TOURNAMENT_CONFIRM_TEXT =
  "所有已報名隊伍的隊長與選手會收到通知；賽事資訊改為唯讀，無法復原。"

/** 已結束、已取消的賽事不能取消（後端回 409 `TOURNAMENT_NOT_CANCELLABLE`），不顯示按鈕。 */
export function canCancelTournament(status: TournamentRead["status"]): boolean {
  return status !== "finished" && status !== "cancelled"
}

/** S27「取消賽事」按鈕：按下後以 destructive 的 AlertDialog 確認，確認後呼叫取消 API。 */
export function CancelTournamentButton({
  tournament,
}: {
  tournament: TournamentRead
}) {
  const cancel = useCancelTournament(tournament.id)
  const [open, setOpen] = useState(false)
  // 取消成功時狀態先變成 cancelled、對話框才關閉：等對話框關閉後才移除，
  // 不在對話框開著時卸載（避免焦點與頁面鎖定沒有還原）
  if (!canCancelTournament(tournament.status) && !open) return null

  return (
    <section aria-label={CANCEL_TOURNAMENT_TEXT} className="mt-6 flex">
      <ConfirmDialog
        open={open}
        onOpenChange={setOpen}
        title={CANCEL_TOURNAMENT_TEXT}
        description={CANCEL_TOURNAMENT_CONFIRM_TEXT}
        confirmLabel={CANCEL_TOURNAMENT_TEXT}
        cancelLabel={KEEP_TOURNAMENT_TEXT}
        destructive
        // 失敗已由 mutation 以錯誤 Toast 顯示並重抓賽事；這裡吞掉 reject 讓對話框關閉
        onConfirm={() => cancel.mutateAsync().catch(() => undefined)}
        trigger={
          <Button variant="outline" className="h-10 w-full sm:w-auto">
            {CANCEL_TOURNAMENT_TEXT}
          </Button>
        }
      />
    </section>
  )
}
