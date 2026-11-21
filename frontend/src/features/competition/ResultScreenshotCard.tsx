import type { ReactNode } from "react"

import { Card } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"

export const RESULT_SCREENSHOT_TITLE = "結算截圖"
export const RESULT_SCREENSHOT_EMPTY_TEXT = "勝隊尚未上傳結算截圖"
export const RESULT_SCREENSHOT_FAILED_TEXT =
  "結算截圖載入失敗，請重新整理頁面。"

type ResultScreenshotCardProps = {
  /** 勝隊已上傳（公開單場的 `result_screenshot_at` 有值） */
  hasScreenshot: boolean
  /** 圖片的 object URL；下載中或失敗時為 null */
  imageUrl: string | null
  /** 圖片下載失敗 */
  imageFailed?: boolean
  /** 勝隊隊長的上傳區（Screenshot uploader 與按鈕）；其他人不傳 */
  uploader?: ReactNode
  className?: string
}

/**
 * S4 Result screenshot（DESIGN.md〈Result screenshot〉、UX-DR32）：標題「結算截圖」的 Card。
 * 已上傳顯示縮圖（最大寬 320px），點擊以 Dialog 放大；未上傳顯示一行說明。
 * 勝隊隊長在同一張 Card 看到上傳區。系列結果送出前由呼叫端決定不渲染。
 */
export function ResultScreenshotCard({
  hasScreenshot,
  imageUrl,
  imageFailed = false,
  uploader,
  className,
}: ResultScreenshotCardProps) {
  return (
    <Card data-slot="result-screenshot" className={cn("gap-3 p-4", className)}>
      <h2 className="font-semibold text-label text-muted-foreground">
        {RESULT_SCREENSHOT_TITLE}
      </h2>
      {!hasScreenshot ? (
        <p
          data-slot="result-screenshot-empty"
          className="text-muted-foreground text-sm"
        >
          {RESULT_SCREENSHOT_EMPTY_TEXT}
        </p>
      ) : imageUrl ? (
        <Dialog>
          <DialogTrigger asChild>
            <button
              type="button"
              data-slot="result-screenshot-thumbnail"
              aria-label="放大結算截圖"
              className="block w-full max-w-80 cursor-zoom-in self-start overflow-hidden rounded-md border focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2"
            >
              <img
                src={imageUrl}
                alt={RESULT_SCREENSHOT_TITLE}
                className="block h-auto w-full"
              />
            </button>
          </DialogTrigger>
          <DialogContent className="max-h-[calc(100dvh-2rem)] overflow-auto sm:max-w-4xl">
            <DialogTitle>{RESULT_SCREENSHOT_TITLE}</DialogTitle>
            <DialogDescription className="sr-only">
              勝隊隊長上傳的遊戲結算畫面
            </DialogDescription>
            <img
              src={imageUrl}
              alt={RESULT_SCREENSHOT_TITLE}
              data-slot="result-screenshot-full"
              className="block h-auto w-full rounded-md"
            />
          </DialogContent>
        </Dialog>
      ) : imageFailed ? (
        <p role="alert" className="text-destructive text-sm">
          {RESULT_SCREENSHOT_FAILED_TEXT}
        </p>
      ) : (
        <Skeleton
          data-slot="result-screenshot-loading"
          className="aspect-video w-full max-w-80"
        />
      )}
      {uploader}
    </Card>
  )
}
