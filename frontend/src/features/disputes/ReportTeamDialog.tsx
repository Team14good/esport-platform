import { zodResolver } from "@hookform/resolvers/zod"
import { useEffect, useRef, useState } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"

import type { ReportableTeam } from "@/client"
import { FormErrorAlert } from "@/components/common/FormErrorAlert"
import { ResponsiveDialog } from "@/components/common/ResponsiveDialog"
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import { LoadingButton } from "@/components/ui/loading-button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import { ScreenshotUploader } from "@/features/registration/ScreenshotUploader"
import { type ApiError, applyFieldErrors, parseApiError } from "@/lib/api-error"

export const REPORT_DIALOG_TITLE = "提出檢舉"
export const REPORT_DIALOG_DESCRIPTION =
  "主辦方會查證，查證前被檢舉的隊伍不受影響。截圖只有主辦方看得到。"
export const REPORT_SUBMIT_TEXT = "送出檢舉"
export const ALREADY_REPORTED_SUFFIX = "・已檢舉・處理中"
export const ALL_REPORTED_TEXT = "這些隊伍都已檢舉，主辦方處理中。"
export const DESCRIPTION_MAX_LENGTH = 1000

// core.storage 的 415／413：屬於截圖欄位的錯誤
const ATTACHMENT_ERROR_CODES = ["UNSUPPORTED_FILE_TYPE", "FILE_TOO_LARGE"]

/** 以 code point 計算字數，與後端一致（emoji 算一個字）。 */
export function countCharacters(text: string): number {
  return [...text].length
}

/** 表單欄位名與 API 欄位同名，伺服器 422 的 loc 才能對應到欄位。 */
export type ReportTeamValues = {
  reported_team_id: string
  description: string
  /** 選填的截圖 */
  attachment: File | null
}

const schema = z.object({
  reported_team_id: z.string().min(1, "請選擇檢舉對象。"),
  description: z
    .string()
    .trim()
    .min(1, "請輸入說明。")
    .refine(
      (value) => countCharacters(value) <= DESCRIPTION_MAX_LENGTH,
      "說明須為 1～1000 字。",
    ),
  attachment: z.instanceof(File).nullable(),
})

type FormInput = z.input<typeof schema>

const EMPTY_VALUES: FormInput = {
  reported_team_id: "",
  description: "",
  attachment: null,
}

export type ReportTeamDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** 可檢舉的隊伍（不含自己）；`has_open_report` 的項目停用 */
  teams: ReportableTeam[]
  /** 上傳進度 0～100；沒有在上傳時為 null */
  uploadProgress?: number | null
  /** 送出；失敗時 reject，伺服器錯誤顯示在對話框內 */
  onSubmit: (values: ReportTeamValues) => Promise<void>
}

/**
 * S20 提出檢舉：手機用底部 Sheet、桌機用 Dialog。選對象、填說明、選擇性附截圖，
 * 按「送出檢舉」直接送出（不再開確認對話框）。關閉只用右上角，送出中不能關閉。
 */
export function ReportTeamDialog({
  open,
  onOpenChange,
  teams,
  uploadProgress = null,
  onSubmit,
}: ReportTeamDialogProps) {
  const [formError, setFormError] = useState<ApiError | null>(null)
  const form = useForm<FormInput, unknown, ReportTeamValues>({
    resolver: zodResolver(schema),
    defaultValues: EMPTY_VALUES,
  })

  // 每次「開啟」（關→開）都從空白開始，不留上次沒送出的內容與錯誤
  const wasOpen = useRef(false)
  useEffect(() => {
    if (open && !wasOpen.current) {
      form.reset(EMPTY_VALUES)
      setFormError(null)
    }
    wasOpen.current = open
  }, [open, form])

  const allReported =
    teams.length > 0 && teams.every((team) => team.has_open_report)
  const submitting = form.formState.isSubmitting
  const description = form.watch("description")

  async function submit(values: ReportTeamValues) {
    setFormError(null)
    try {
      await onSubmit(values)
    } catch (error) {
      const parsed = parseApiError(error)
      if (
        parsed.kind === "business" &&
        ATTACHMENT_ERROR_CODES.includes(parsed.code)
      ) {
        form.setError("attachment", { type: "server", message: parsed.message })
        return
      }
      setFormError(applyFieldErrors(form, error))
    }
  }

  return (
    <ResponsiveDialog
      open={open}
      onOpenChange={(next) => {
        // 送出中不能關閉（Esc、點遮罩、關閉鈕），否則請求失敗時錯誤沒地方顯示
        if (!next && form.formState.isSubmitting) return
        onOpenChange(next)
      }}
      title={REPORT_DIALOG_TITLE}
      description={REPORT_DIALOG_DESCRIPTION}
      testIdPrefix="report-team"
    >
      <Form {...form}>
        <form
          noValidate
          onSubmit={form.handleSubmit(submit)}
          className="flex flex-col gap-5"
        >
          <FormErrorAlert error={formError} />
          <FormField
            control={form.control}
            name="reported_team_id"
            render={({ field }) => (
              <FormItem>
                <FormLabel>檢舉對象</FormLabel>
                <Select
                  value={field.value}
                  onValueChange={field.onChange}
                  disabled={submitting || allReported}
                >
                  <FormControl>
                    <SelectTrigger ref={field.ref} className="w-full">
                      <SelectValue placeholder="選擇隊伍" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    {teams.map((team) => (
                      <SelectItem
                        key={team.id}
                        value={team.id}
                        disabled={team.has_open_report}
                      >
                        {team.has_open_report
                          ? `${team.name}${ALREADY_REPORTED_SUFFIX}`
                          : team.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {allReported && (
                  <p className="text-caption text-muted-foreground">
                    {ALL_REPORTED_TEXT}
                  </p>
                )}
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="description"
            render={({ field }) => (
              <FormItem>
                <FormLabel>說明</FormLabel>
                <FormControl>
                  <Textarea
                    className="min-h-24 break-words"
                    disabled={submitting || allReported}
                    {...field}
                  />
                </FormControl>
                <p className="self-end text-caption text-muted-foreground">
                  {countCharacters(description ?? "")}／{DESCRIPTION_MAX_LENGTH}
                </p>
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
                    disabled={submitting || allReported}
                  />
                </FormControl>
              </FormItem>
            )}
          />
          <LoadingButton
            type="submit"
            loading={submitting}
            disabled={allReported}
            className="w-full sm:ml-auto sm:w-auto"
          >
            {REPORT_SUBMIT_TEXT}
          </LoadingButton>
        </form>
      </Form>
    </ResponsiveDialog>
  )
}
