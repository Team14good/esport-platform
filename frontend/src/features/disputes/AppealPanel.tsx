import { useId, useState } from "react"

import type { AppealState, PublicMatchDetail } from "@/client"
import { Button } from "@/components/ui/button"
import { notifyError, notifySuccess } from "@/lib/feedback"
import { AppealDialog } from "./AppealDialog"
import { type AppealValues, fileAppeal, useAppealState } from "./queries"

export const FILE_APPEAL_TEXT = "提出申訴"
export const ALREADY_FILED_TEXT = "本隊已對此場次提出申訴"
export const DEADLINE_PASSED_TEXT = "已截止"
export const APPEAL_FILED_TOAST = "申訴已送出。"

/**
 * 按鈕停用時的說明；`null` 代表不顯示按鈕（不是兩隊隊長、場次不能申訴、狀態還沒回來）。
 * 本隊已申訴優先於已截止：期限過後本隊仍看得到自己申訴過。
 */
export function appealEntry(
  state: AppealState | undefined,
): { disabled: boolean; note: string | null } | null {
  if (!state) return null
  if (state.already_filed) return { disabled: true, note: ALREADY_FILED_TEXT }
  if (state.reason === "deadline_passed") {
    return { disabled: true, note: DEADLINE_PASSED_TEXT }
  }
  if (state.reason === null && state.can_file) {
    return { disabled: false, note: null }
  }
  // not_captain、not_appealable（以及其他未知原因）不顯示按鈕
  return null
}

type AppealPanelProps = {
  detail: PublicMatchDetail
  /** 重抓這一場的所有資料（公開單場與申訴狀態），完成後才 resolve */
  refresh: () => Promise<unknown>
}

/**
 * S4 申訴入口（放在申訴期區塊的插槽）：滿版 outline「提出申訴」，只有兩隊隊長看得到；
 * 本隊已申訴或已截止時停用並說明。點擊開 S21 `AppealDialog`；成功 Toast、關閉並重抓 S4，
 * 失敗以錯誤 Toast 顯示伺服器訊息。
 */
export function AppealPanel({ detail, refresh }: AppealPanelProps) {
  const { state, isPlaceholder } = useAppealState(detail)
  const [open, setOpen] = useState(false)
  const [uploadProgress, setUploadProgress] = useState<number | null>(null)
  const noteId = useId()
  const latest = appealEntry(state)
  // 場次版本剛改變（例如本隊剛送出）時顯示的是舊狀態：不顯示可按的按鈕，以免按下後回 409
  const entry =
    latest && isPlaceholder && !latest.disabled
      ? { disabled: true, note: null }
      : latest
  // 對話框開著時狀態變成不能申訴（例如另一個分頁已送出），仍保留對話框讓送出的錯誤有地方顯示
  if (!entry && !open) return null

  async function handleSubmit(values: AppealValues) {
    setUploadProgress(values.attachment ? 0 : null)
    try {
      await fileAppeal({
        tournamentId: detail.tournament.id,
        matchId: detail.id,
        values,
        onProgress: setUploadProgress,
      })
    } catch (error) {
      notifyError(error)
      // 被拒（例如已截止、已申訴）時重抓，讓按鈕狀態跟上伺服器
      void refresh()
      throw error
    } finally {
      setUploadProgress(null)
    }
    notifySuccess(APPEAL_FILED_TOAST)
    setOpen(false)
    await refresh()
  }

  return (
    <div data-slot="appeal-panel" className="flex flex-col gap-2">
      {entry && (
        <>
          <Button
            type="button"
            variant="outline"
            size="lg"
            className="h-touch-target w-full"
            disabled={entry.disabled}
            aria-describedby={entry.note ? noteId : undefined}
            onClick={() => setOpen(true)}
          >
            {FILE_APPEAL_TEXT}
          </Button>
          {entry.note && (
            <p id={noteId} className="text-sm text-muted-foreground">
              {entry.note}
            </p>
          )}
        </>
      )}
      <AppealDialog
        open={open}
        onOpenChange={setOpen}
        uploadProgress={uploadProgress}
        onSubmit={handleSubmit}
      />
    </div>
  )
}
