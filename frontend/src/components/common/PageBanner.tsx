import { Link, type LinkProps } from "@tanstack/react-router"
import { CircleAlertIcon, InfoIcon, XIcon } from "lucide-react"
import type { ReactNode } from "react"

import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

// Page banner（DESIGN.md〈Components〉、EXPERIENCE.md〈Component Patterns〉）：
// 頁面內容最上方滿版的一則 Alert，用於整頁層級的狀況。同一頁最多一則，destructive 優先。

type BannerAction =
  | {
      /** 按鈕文字（動詞＋名詞） */
      label: string
      onClick: () => void
      to?: never
    }
  | {
      /** 按鈕文字（動詞＋名詞） */
      label: string
      /** 連到站內頁面：以連結呈現，可中鍵開新分頁、複製連結 */
      to: LinkProps["to"]
      onClick?: never
    }

export type PageBannerProps =
  | {
      variant: "destructive"
      children: ReactNode
      action?: never
      onDismiss?: never
    }
  | {
      variant?: "default"
      children: ReactNode
      /** 附帶的 outline Button */
      action?: BannerAction
      /** 有傳入時顯示關閉鈕；關閉後是否保存（例如 localStorage）由呼叫端決定 */
      onDismiss?: () => void
    }

/** 單一則 Page banner。同頁有多則候選時用 `PageBannerSlot`。 */
export function PageBanner(props: PageBannerProps) {
  const destructive = props.variant === "destructive"
  const action = destructive ? undefined : props.action
  const onDismiss = destructive ? undefined : props.onDismiss

  return (
    <Alert
      variant={destructive ? "destructive" : "default"}
      data-slot="page-banner"
      // destructive 立即朗讀；default 不打斷螢幕閱讀器
      role={destructive ? "alert" : "status"}
      className={cn(
        "rounded-md",
        destructive ? "border-destructive" : "bg-transparent",
      )}
    >
      {destructive ? <CircleAlertIcon /> : <InfoIcon />}
      <AlertDescription
        className={cn(
          "flex flex-wrap items-center gap-x-3 gap-y-2 text-body",
          destructive ? "text-destructive" : "text-foreground",
          onDismiss && "pr-8",
        )}
      >
        <span className="min-w-0 flex-1 basis-48">{props.children}</span>
        {action?.to !== undefined ? (
          <Button variant="outline" size="sm" asChild>
            <Link to={action.to}>{action.label}</Link>
          </Button>
        ) : action ? (
          <Button variant="outline" size="sm" onClick={action.onClick}>
            {action.label}
          </Button>
        ) : null}
      </AlertDescription>
      {onDismiss ? (
        <Button
          variant="ghost"
          size="icon"
          aria-label="關閉提示"
          onClick={onDismiss}
          className="absolute top-1.5 right-1.5 size-8"
        >
          <XIcon />
        </Button>
      ) : null}
    </Alert>
  )
}

/** 從候選中挑出要顯示的那一則：destructive 優先，其次照傳入順序。沒有候選時回傳 null。 */
export function pickPageBanner(
  candidates: ReadonlyArray<PageBannerProps | null | undefined | false>,
): PageBannerProps | null {
  const present = candidates.filter((c): c is PageBannerProps => Boolean(c))
  return present.find((c) => c.variant === "destructive") ?? present[0] ?? null
}

/** 同一頁最多顯示一則 Page banner。 */
export function PageBannerSlot({
  banners,
}: {
  banners: ReadonlyArray<PageBannerProps | null | undefined | false>
}) {
  const banner = pickPageBanner(banners)
  return banner ? <PageBanner {...banner} /> : null
}
