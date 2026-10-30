import { CircleAlertIcon } from "lucide-react"
import { type ReactNode, useId, useState } from "react"

import { Alert, AlertDescription } from "@/components/ui/alert"
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog"
import { Label } from "@/components/ui/label"
import { LoadingButton } from "@/components/ui/loading-button"
import { Textarea } from "@/components/ui/textarea"
import { getErrorMessage, parseApiError } from "@/lib/api-error"

export const CANCEL_TEXT = "取消"

type ConfirmDialogProps = {
  /** 標題寫動作，例如「退回主辦方申請」 */
  title: string
  /** 內文寫後果 */
  description: ReactNode
  /** 確認鈕重複動作名（「核准」「退回申請」），不用「確定」 */
  confirmLabel: string
  /** 破壞性動作：確認鈕用 destructive 樣式 */
  destructive?: boolean
  /** 必填理由欄：沒填（去除前後空白後為空）時確認鈕停用 */
  reason?: { label: string; maxLength: number }
  /**
   * 按下確認鈕時呼叫（有理由欄時帶去除前後空白的理由）；resolve 後關閉對話框，
   * reject 時留在對話框並顯示伺服器的 `detail.message`。
   */
  onConfirm: (reason?: string) => Promise<unknown>
  /** 開啟對話框的按鈕（以 asChild 包住）；不給時以 open／onOpenChange 控制 */
  trigger?: ReactNode
  open?: boolean
  onOpenChange?: (open: boolean) => void
}

/**
 * 確認型操作的 AlertDialog 包裝（全站共用）：標題寫動作、內文寫後果、確認鈕重複動作名，
 * 可設定必填理由欄。送出中確認鈕顯示 spinner 並停用，對話框不能關閉。
 */
export function ConfirmDialog({
  title,
  description,
  confirmLabel,
  destructive = false,
  reason,
  onConfirm,
  trigger,
  open: openProp,
  onOpenChange,
}: ConfirmDialogProps) {
  const reasonId = useId()
  const [openState, setOpenState] = useState(false)
  const [reasonText, setReasonText] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const open = openProp ?? openState

  const setOpen = (next: boolean) => {
    if (!next) {
      // 關閉時清掉理由與錯誤：下次開啟從空白開始
      setReasonText("")
      setError(null)
    }
    setOpenState(next)
    onOpenChange?.(next)
  }

  const trimmed = reasonText.trim()
  const confirmDisabled = reason !== undefined && trimmed.length === 0

  const confirm = async () => {
    setError(null)
    setPending(true)
    try {
      await onConfirm(reason ? trimmed : undefined)
      setPending(false)
      setOpen(false)
    } catch (caught) {
      setPending(false)
      setError(getErrorMessage(parseApiError(caught)))
    }
  }

  return (
    <AlertDialog
      open={open}
      onOpenChange={(next) => {
        // 送出中不能關閉（Esc、取消鈕）
        if (!pending) setOpen(next)
      }}
    >
      {trigger && <AlertDialogTrigger asChild>{trigger}</AlertDialogTrigger>}
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle className="text-heading-md">
            {title}
          </AlertDialogTitle>
          <AlertDialogDescription className="text-body">
            {description}
          </AlertDialogDescription>
        </AlertDialogHeader>
        {error && (
          <Alert variant="destructive" className="rounded-md">
            <CircleAlertIcon />
            <AlertDescription className="text-destructive">
              {error}
            </AlertDescription>
          </Alert>
        )}
        {reason && (
          <div className="flex flex-col gap-2">
            <Label htmlFor={reasonId}>{reason.label}</Label>
            <Textarea
              id={reasonId}
              value={reasonText}
              maxLength={reason.maxLength}
              disabled={pending}
              onChange={(event) => setReasonText(event.target.value)}
              className="min-h-24 break-words"
            />
            <p className="self-end text-caption text-muted-foreground">
              {reasonText.length}／{reason.maxLength}
            </p>
          </div>
        )}
        <AlertDialogFooter>
          <AlertDialogCancel disabled={pending}>
            {CANCEL_TEXT}
          </AlertDialogCancel>
          <LoadingButton
            variant={destructive ? "destructive" : "default"}
            loading={pending}
            disabled={confirmDisabled}
            onClick={confirm}
          >
            {confirmLabel}
          </LoadingButton>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
