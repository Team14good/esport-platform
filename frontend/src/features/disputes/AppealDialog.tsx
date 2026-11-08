import { zodResolver } from "@hookform/resolvers/zod"
import { useEffect, useRef } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import { LoadingButton } from "@/components/ui/loading-button"
import { Textarea } from "@/components/ui/textarea"
import { codePointLength } from "@/features/identity/SignupForm"
import { ScreenshotUploader } from "@/features/registration/ScreenshotUploader"
import type { AppealValues } from "./queries"

export const APPEAL_DESCRIPTION_MAX_LENGTH = 1000
export const SUBMIT_APPEAL_TEXT = "送出申訴"

// 與後端相同的規則（去頭尾空白後 1～1000 字，以 code point 計算）；伺服器的錯誤仍以伺服器為準
const appealSchema = z.object({
  description: z
    .string()
    .trim()
    .min(1, "請輸入申訴說明")
    .refine(
      (value) => codePointLength(value) <= APPEAL_DESCRIPTION_MAX_LENGTH,
      { message: `申訴說明最多 ${APPEAL_DESCRIPTION_MAX_LENGTH} 個字` },
    ),
  attachment: z.instanceof(File).nullable(),
})

type AppealInput = z.input<typeof appealSchema>

export type AppealDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** 上傳進度 0～100；沒有在上傳時為 null */
  uploadProgress?: number | null
  /** 送出；成功時 resolve（由呼叫端關閉對話框），失敗時 reject（呼叫端已顯示錯誤），內容保留 */
  onSubmit: (values: AppealValues) => Promise<void>
}

/**
 * S21 提出申訴：說明（必填）＋選填的截圖（沿用 3.2 的 Screenshot uploader）。
 * 送出中不能關閉；每次開啟都從空白開始。
 */
export function AppealDialog({
  open,
  onOpenChange,
  uploadProgress = null,
  onSubmit,
}: AppealDialogProps) {
  const form = useForm<AppealInput, unknown, AppealValues>({
    resolver: zodResolver(appealSchema),
    defaultValues: { description: "", attachment: null },
  })

  // 關 → 開時清空上次沒送出的內容
  const wasOpen = useRef(false)
  useEffect(() => {
    if (open && !wasOpen.current) {
      form.reset({ description: "", attachment: null })
    }
    wasOpen.current = open
  }, [open, form])

  async function submit(values: AppealValues) {
    try {
      await onSubmit(values)
    } catch {
      // 錯誤已由呼叫端以 Toast 顯示；保留輸入內容讓使用者修正後重送
    }
  }

  const submitting = form.formState.isSubmitting

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        // 送出中不能關閉（Esc、點遮罩、關閉鈕）
        if (!next && submitting) return
        onOpenChange(next)
      }}
    >
      <DialogContent
        data-testid="appeal-dialog"
        className="max-h-[90dvh] overflow-y-auto"
      >
        <DialogHeader>
          <DialogTitle>提出申訴</DialogTitle>
          <DialogDescription>
            說明你對這場比賽結果的異議，由主辦方查證後處理。每隊每場只能申訴一次。
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form
            noValidate
            onSubmit={form.handleSubmit(submit)}
            className="flex min-w-0 flex-col gap-5"
          >
            <FormField
              control={form.control}
              name="description"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>申訴說明</FormLabel>
                  <FormControl>
                    <Textarea
                      rows={5}
                      className="max-h-64"
                      disabled={submitting}
                      {...field}
                    />
                  </FormControl>
                  <FormDescription>
                    最多 {APPEAL_DESCRIPTION_MAX_LENGTH} 個字。
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="attachment"
              render={({ field, fieldState }) => (
                <FormItem>
                  <FormLabel>截圖（選填）</FormLabel>
                  <FormControl>
                    <ScreenshotUploader
                      value={field.value ?? null}
                      onChange={field.onChange}
                      progress={uploadProgress}
                      error={fieldState.error?.message ?? null}
                      disabled={submitting}
                    />
                  </FormControl>
                </FormItem>
              )}
            />
            <DialogFooter>
              <LoadingButton
                type="submit"
                loading={submitting}
                className="w-full sm:w-auto"
              >
                {SUBMIT_APPEAL_TEXT}
              </LoadingButton>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}
