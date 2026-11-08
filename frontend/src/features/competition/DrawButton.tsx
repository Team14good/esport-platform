import { useQuery } from "@tanstack/react-query"
import { useId } from "react"

import type { DrawStatus, TournamentRead } from "@/client"
import { ConfirmDialog } from "@/components/common/ConfirmDialog"
import { Button } from "@/components/ui/button"
import { drawStatusQueryOptions, useDraw } from "./draw-queries"

export const DRAW_TEXT = "抽籤"
export const DRAW_CONFIRM_OPEN_TEXT = "抽籤只能執行一次，會立即結束報名。"
export const DRAW_CONFIRM_CLOSED_TEXT = "抽籤只能執行一次。"
export const DRAW_STATUS_ERROR_TEXT = "無法取得抽籤狀態"
const RELOAD_TEXT = "重新載入"

type DrawReason = NonNullable<DrawStatus["reason"]>

/** 按鈕停用時寫在下方的原因；`already_drawn`、`not_drawable` 不顯示按鈕，所以沒有文字。 */
export const DRAW_BLOCKED_TEXT: Partial<Record<DrawReason, string>> = {
  not_enough_teams: "正取不足 2 隊，無法抽籤",
  start_passed: "開賽時間已過，無法抽籤",
}

const HIDDEN_REASONS: ReadonlySet<DrawReason> = new Set([
  "already_drawn",
  "not_drawable",
])

/**
 * S27 抽籤按鈕：只在後端預估可以抽籤時可按，停用時在下方寫原因；已抽籤或賽事狀態不能抽籤時不顯示。
 * 按下後以 AlertDialog 確認，後端抽籤時會再檢查一次。
 */
export function DrawButton({ tournament }: { tournament: TournamentRead }) {
  // 只有開放報名與報名截止才可能抽籤；其他狀態不送出（後端每次預估都持有賽事列鎖）
  const drawable =
    tournament.status === "open" || tournament.status === "closed"
  const status = useQuery({
    ...drawStatusQueryOptions(tournament.id),
    enabled: drawable,
  })
  const draw = useDraw(tournament.id)
  const reasonId = useId()

  if (!drawable) return null
  if (!status.data) {
    // 載入中不顯示；載入失敗要讓主辦方知道並能重試（後端抽籤仍會檢查，不會誤抽）
    if (!status.isError) return null
    return (
      <section
        aria-label="抽籤狀態"
        className="mt-6 flex flex-wrap items-center gap-3"
      >
        <p role="alert" className="text-body text-destructive">
          {DRAW_STATUS_ERROR_TEXT}
        </p>
        <Button
          variant="outline"
          disabled={status.isFetching}
          onClick={() => status.refetch()}
        >
          {RELOAD_TEXT}
        </Button>
      </section>
    )
  }
  const { can_draw: canDraw, reason } = status.data
  if (reason !== null && HIDDEN_REASONS.has(reason)) return null
  const blockedText = reason !== null ? DRAW_BLOCKED_TEXT[reason] : undefined

  return (
    <section aria-label={DRAW_TEXT} className="mt-6 flex flex-col gap-2">
      <ConfirmDialog
        title={DRAW_TEXT}
        description={
          tournament.status === "open"
            ? DRAW_CONFIRM_OPEN_TEXT
            : DRAW_CONFIRM_CLOSED_TEXT
        }
        confirmLabel={DRAW_TEXT}
        // 失敗已由 mutation 以錯誤 Toast 顯示並重抓狀態；這裡吞掉 reject 讓對話框關閉
        onConfirm={() => draw.mutateAsync().catch(() => undefined)}
        trigger={
          <Button
            disabled={!canDraw}
            aria-describedby={blockedText ? reasonId : undefined}
            className="h-10 w-full sm:w-auto sm:self-start"
          >
            {DRAW_TEXT}
          </Button>
        }
      />
      {blockedText && (
        <p id={reasonId} className="text-body text-muted-foreground">
          {blockedText}
        </p>
      )}
    </section>
  )
}
