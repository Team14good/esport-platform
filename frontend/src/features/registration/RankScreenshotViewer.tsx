import { ChevronLeftIcon, ChevronRightIcon } from "lucide-react"
import { type ReactNode, useState } from "react"

import type { OrganizerRegistration } from "@/client"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { Skeleton } from "@/components/ui/skeleton"
import { useIsMobile } from "@/hooks/useMobile"
import {
  NEXT_MEMBER_TEXT,
  NOT_UPLOADED_TEXT,
  PREVIOUS_MEMBER_TEXT,
  RANK_SCREENSHOT_TEXT,
  REJECT_TEXT,
  SCREENSHOT_FAILED_TEXT,
  useRankScreenshotImage,
} from "./organizer-registrations"

type RankScreenshotViewerProps = {
  tournamentId: string
  registration: OrganizerRegistration
  open: boolean
  onOpenChange: (open: boolean) => void
  /** 按「退回報名」：呼叫端先關閉檢視器，再開確認對話框（不疊 Dialog） */
  onReject: () => void
}

/** 目前隊員的截圖：載入中 Skeleton、未上傳、載入失敗或圖片（contain 置於框內）。 */
function ScreenshotFrame({
  tournamentId,
  registration,
  index,
}: {
  tournamentId: string
  registration: OrganizerRegistration
  index: number
}) {
  const member = registration.members[index]
  const { url, failed } = useRankScreenshotImage(
    tournamentId,
    registration.registration_id,
    member,
  )
  let content: ReactNode
  if (!member.has_rank_screenshot) {
    content = (
      <p data-slot="rank-screenshot-empty" className="text-muted-foreground">
        {NOT_UPLOADED_TEXT}
      </p>
    )
  } else if (url) {
    content = (
      <img
        src={url}
        alt={`${member.display_name}的${RANK_SCREENSHOT_TEXT}`}
        data-slot="rank-screenshot-image"
        className="max-h-full max-w-full object-contain"
      />
    )
  } else if (failed) {
    content = (
      <p role="alert" className="text-destructive">
        {SCREENSHOT_FAILED_TEXT}
      </p>
    )
  } else {
    content = (
      <Skeleton data-slot="rank-screenshot-loading" className="size-full" />
    )
  }
  return (
    <div className="flex h-[min(60dvh,540px)] items-center justify-center overflow-hidden rounded-md border bg-background">
      {content}
    </div>
  )
}

/**
 * Rank screenshot viewer（UX-DR36，S29 主辦方專用）：標頭為隊名與目前隊員（顯示名稱、
 * 遊戲 ID、申報段位），截圖經授權 API 載入；「上一位」「下一位」與「n／N」在同隊隊員間
 * 切換（隊長在前、再依加入順序），第一位／最後一位時對應按鈕停用。可退回時右側有
 * destructive outline「退回報名」。桌機 Dialog 最大寬 960px，手機用底部 Sheet。
 */
export function RankScreenshotViewer({
  tournamentId,
  registration,
  open,
  onOpenChange,
  onReject,
}: RankScreenshotViewerProps) {
  const isMobile = useIsMobile()
  const [index, setIndex] = useState(0)
  const total = registration.members.length
  const current = Math.min(index, Math.max(total - 1, 0))
  const member = registration.members[current]
  const title = `${registration.team_name}・${RANK_SCREENSHOT_TEXT}`
  const description = member
    ? [
        member.display_name,
        `遊戲 ID：${member.game_account_id ?? "未填寫"}`,
        `申報段位：${member.rank_tier ?? "未填寫"}`,
      ].join("・")
    : ""

  const body = member ? (
    <div className="flex min-w-0 flex-col gap-4">
      <ScreenshotFrame
        // 換隊員時重新掛載，不沿用前一位的載入狀態
        key={member.account_id}
        tournamentId={tournamentId}
        registration={registration}
        index={current}
      />
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            disabled={current <= 0}
            onClick={() => setIndex(current - 1)}
          >
            <ChevronLeftIcon aria-hidden="true" />
            {PREVIOUS_MEMBER_TEXT}
          </Button>
          <span
            data-slot="rank-screenshot-counter"
            aria-live="polite"
            className="px-2 text-body text-muted-foreground"
          >
            {current + 1}／{total}
          </span>
          <Button
            variant="outline"
            disabled={current >= total - 1}
            onClick={() => setIndex(current + 1)}
          >
            {NEXT_MEMBER_TEXT}
            <ChevronRightIcon aria-hidden="true" />
          </Button>
        </div>
        {registration.rejectable && (
          <Button
            variant="outline"
            className="border-destructive/40 text-destructive hover:text-destructive"
            onClick={onReject}
          >
            {REJECT_TEXT}
          </Button>
        )}
      </div>
    </div>
  ) : null

  if (isMobile) {
    return (
      <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetContent
          side="bottom"
          className="max-h-[90dvh] overflow-y-auto"
          data-testid="rank-screenshot-sheet"
        >
          <SheetHeader>
            <SheetTitle className="break-words">{title}</SheetTitle>
            <SheetDescription className="break-words">
              {description}
            </SheetDescription>
          </SheetHeader>
          <div className="px-4 pb-4">{body}</div>
        </SheetContent>
      </Sheet>
    )
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        data-testid="rank-screenshot-dialog"
        className="sm:max-w-screenshot-viewer-max"
      >
        <DialogHeader>
          <DialogTitle className="break-words">{title}</DialogTitle>
          <DialogDescription className="break-words">
            {description}
          </DialogDescription>
        </DialogHeader>
        {body}
      </DialogContent>
    </Dialog>
  )
}
