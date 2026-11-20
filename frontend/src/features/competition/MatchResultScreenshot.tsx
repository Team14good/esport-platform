import { useState } from "react"

import type { PublicMatchDetail } from "@/client"
import { Button } from "@/components/ui/button"
import { ScreenshotUploader } from "@/features/registration/ScreenshotUploader"
import { getErrorMessage, parseApiError } from "@/lib/api-error"
import { notifySuccess } from "@/lib/feedback"
import { ResultScreenshotCard } from "./ResultScreenshotCard"
import {
  uploadResultScreenshot,
  useResultScreenshotImage,
  useResultScreenshotState,
} from "./result-screenshot-queries"

export const UPLOAD_SCREENSHOT_TEXT = "上傳截圖"
export const REPLACE_SCREENSHOT_TEXT = "更換截圖"
export const SCREENSHOT_UPLOADED_TOAST = "結算截圖已上傳。"

/** 系列結果送出後才有「結算截圖」區塊（判棄權、輪空、取消資格判負的場次沒有）。 */
export function showsResultScreenshot(detail: PublicMatchDetail): boolean {
  return detail.result_screenshot_enabled === true
}

type MatchResultScreenshotProps = {
  detail: PublicMatchDetail
  /** 重抓這一場的所有資料（公開單場與面板狀態），完成後才 resolve */
  refresh: () => Promise<unknown>
  className?: string
}

/**
 * S4 結算截圖的資料轉接（S22）：所有人（含未登入）都看得到截圖；
 * 只有登入者才查詢能不能上傳，勝隊隊長在同一張 Card 看到 Screenshot uploader。
 * 選檔後先顯示本機預覽，按「上傳截圖」（已有截圖時為「更換截圖」）才送出。
 */
export function MatchResultScreenshot({
  detail,
  refresh,
  className,
}: MatchResultScreenshotProps) {
  const image = useResultScreenshotImage(detail)
  const state = useResultScreenshotState(detail)
  const [file, setFile] = useState<File | null>(null)
  const [progress, setProgress] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  if (!showsResultScreenshot(detail)) return null
  const hasScreenshot = detail.result_screenshot_at != null
  const canUpload = state?.can_upload === true

  async function handleUpload() {
    if (!file) return
    setError(null)
    setProgress(0)
    try {
      await uploadResultScreenshot({
        tournamentId: detail.tournament.id,
        matchId: detail.id,
        file,
        onProgress: setProgress,
      })
      await refresh()
      setFile(null)
      notifySuccess(SCREENSHOT_UPLOADED_TOAST)
    } catch (caught) {
      setError(getErrorMessage(parseApiError(caught)))
    } finally {
      setProgress(null)
    }
  }

  return (
    <ResultScreenshotCard
      hasScreenshot={hasScreenshot}
      imageUrl={image.url}
      imageFailed={image.failed}
      className={className}
      uploader={
        canUpload ? (
          <div
            data-slot="result-screenshot-uploader"
            className="flex flex-col gap-2"
          >
            <ScreenshotUploader
              value={file}
              onChange={(next) => {
                setError(null)
                setFile(next)
              }}
              progress={progress}
              error={error}
            />
            {file && (
              <Button
                type="button"
                className="min-h-10 w-full sm:w-auto sm:self-start"
                disabled={progress !== null}
                onClick={() => void handleUpload()}
              >
                {hasScreenshot
                  ? REPLACE_SCREENSHOT_TEXT
                  : UPLOAD_SCREENSHOT_TEXT}
              </Button>
            )}
          </div>
        ) : undefined
      }
    />
  )
}
