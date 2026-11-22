import { useQuery } from "@tanstack/react-query"
import { useId, useState } from "react"

import { ConfirmDialog } from "@/components/common/ConfirmDialog"
import { Button } from "@/components/ui/button"
import { retirementQueryOptions } from "./retirement-queries"
import { useRetireTeam } from "./useRetireTeam"

export const RETIRE_TEXT = "退賽"
export const RETIRE_CONFIRM_DESCRIPTION =
  "退賽後無法恢復。有候補隊伍時，由候補第 1 位接手你們在對戰表上的位置；沒有候補時，對手以輪空晉級。"

/**
 * S17 抽籤後的「退賽」（Story 4.5）：只在後端回報可退賽（`retirable`）時出現；
 * 對手未定又沒有候補時，後端帶 `reason`，按鈕停用並顯示原因。
 * 確認對話框開著時保持掛載：被拒（409）後重新取得的狀態變成不可退賽（或隊伍報名狀態已
 * 不是已參賽），仍要讓使用者在對話框內看到原因，關閉後按鈕才消失。
 */
export function RetireTeamSection({
  teamId,
  registrationStatus,
}: {
  teamId: string
  registrationStatus: string
}) {
  const reasonId = useId()
  const isDrawn = registrationStatus === "drawn"
  const status = useQuery({
    ...retirementQueryOptions(teamId),
    enabled: isDrawn,
  })
  const retire = useRetireTeam(teamId)
  const [open, setOpen] = useState(false)

  const data = status.data
  if (!data) return null
  // 報名狀態不再是已參賽（例如剛被主辦方取消資格）：對話框關著就收起；開著則保留，
  // 讓被拒的原因留在畫面上
  if (!isDrawn && !open) return null

  if (!data.retirable && !open) {
    if (!data.reason) return null
    return (
      <div className="flex flex-col gap-2">
        <Button
          variant="outline"
          disabled
          aria-describedby={reasonId}
          className="h-10 w-full sm:w-auto sm:self-start"
        >
          {RETIRE_TEXT}
        </Button>
        <p id={reasonId} className="text-body text-muted-foreground">
          {data.reason}
        </p>
      </div>
    )
  }

  return (
    <ConfirmDialog
      title={RETIRE_TEXT}
      description={RETIRE_CONFIRM_DESCRIPTION}
      confirmLabel={RETIRE_TEXT}
      destructive
      open={open}
      onOpenChange={setOpen}
      onConfirm={() => retire.mutateAsync()}
      trigger={
        <Button
          variant="outline"
          className="h-10 w-full sm:w-auto sm:self-start"
        >
          {RETIRE_TEXT}
        </Button>
      }
    />
  )
}
