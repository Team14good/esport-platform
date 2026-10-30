import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { type ReactNode, useState } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"

import {
  type AccountRead,
  IdentityService,
  type OrganizerApplicationRead,
} from "@/client"
import { FormErrorAlert } from "@/components/common/FormErrorAlert"
import { StatusBadge } from "@/components/common/StatusBadge"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import { Input } from "@/components/ui/input"
import { LoadingButton } from "@/components/ui/loading-button"
import { Skeleton } from "@/components/ui/skeleton"
import {
  type ApiError,
  applyFieldErrors,
  getErrorMessage,
  parseApiError,
} from "@/lib/api-error"
import { formatDateTime } from "@/lib/datetime"
import { notifySuccess } from "@/lib/feedback"
import { useCurrentAccount } from "./auth"
import {
  APPLICATION_STATUS_BADGES,
  organizerApplicationQueryOptions,
  useMyOrganizerApplication,
} from "./organizer-application"
import { SchoolPicker } from "./SchoolPicker"
import { codePointLength } from "./SignupForm"
import { useSchools } from "./schools"
import { VerificationRequired } from "./VerificationRequired"

export const CLUB_NAME_MAX_LENGTH = 50
export const APPLICATION_SUBMITTED_TEXT = "已送出主辦方申請。"
export const PENDING_SUMMARY_TEXT = "平台管理員審核後，結果會顯示在這裡。"
export const ALREADY_ORGANIZER_TEXT = "你已經是主辦方。"

// 與後端相同的規則；伺服器的 422 仍會寫回對應欄位
const applicationSchema = z.object({
  club_name: z
    .string()
    .trim()
    .min(1, "請輸入社團名稱")
    .refine((value) => codePointLength(value) <= CLUB_NAME_MAX_LENGTH, {
      message: `社團名稱最多 ${CLUB_NAME_MAX_LENGTH} 個字`,
    }),
  school_id: z
    .string()
    .nullable()
    .transform((value, ctx) => {
      if (value === null) {
        ctx.addIssue({ code: "custom", message: "請選擇學校" })
        return z.NEVER
      }
      return value
    }),
})

type ApplicationInput = z.input<typeof applicationSchema>
type ApplicationValues = z.output<typeof applicationSchema>

function ApplicationForm({ account }: { account: AccountRead }) {
  const queryClient = useQueryClient()
  const schools = useSchools()
  const [formError, setFormError] = useState<ApiError | null>(null)
  const form = useForm<ApplicationInput, unknown, ApplicationValues>({
    resolver: zodResolver(applicationSchema),
    // 學校預設帶入帳號的學校，可以改
    defaultValues: { club_name: "", school_id: account.school_id ?? null },
  })

  const submit = useMutation({
    mutationFn: async (values: ApplicationValues) =>
      (await IdentityService.submitOrganizerApplication({ body: values })).data,
    onSuccess: (created) => {
      // 以回傳值換成唯讀摘要，不另外重抓
      queryClient.setQueryData(
        organizerApplicationQueryOptions().queryKey,
        created,
      )
      notifySuccess(APPLICATION_SUBMITTED_TEXT)
    },
    onError: (error) => setFormError(applyFieldErrors(form, error)),
  })

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-2">
        <h1 className="text-heading-lg">申請成為主辦方</h1>
        <p className="text-body text-muted-foreground">
          平台管理員會依社團名稱與學校審核。
        </p>
      </div>
      <VerificationRequired action="申請成為主辦方" linkToVerifyPage>
        <Form {...form}>
          <form
            noValidate
            onSubmit={form.handleSubmit((values) => {
              setFormError(null)
              submit.mutate(values)
            })}
            className="flex flex-col gap-5"
          >
            <FormErrorAlert error={formError} />
            <FormField
              control={form.control}
              name="club_name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>社團名稱</FormLabel>
                  <FormControl>
                    <Input autoComplete="organization" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="school_id"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>學校</FormLabel>
                  <FormControl>
                    <SchoolPicker
                      schools={schools.data ?? []}
                      loading={schools.isPending}
                      loadError={schools.isError}
                      onRetry={() => schools.refetch()}
                      value={field.value}
                      onChange={field.onChange}
                      onBlur={field.onBlur}
                      placeholder="選擇學校"
                    />
                  </FormControl>
                  <FormDescription>只能從學校清單選擇。</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
            <LoadingButton
              type="submit"
              loading={submit.isPending}
              className="mt-1 w-full sm:w-auto sm:self-start"
            >
              送出申請
            </LoadingButton>
          </form>
        </Form>
      </VerificationRequired>
    </div>
  )
}

/** 已送出的申請：唯讀摘要（社團名稱、學校、送出時間、狀態徽章）。 */
function ApplicationSummary({
  application,
}: {
  application: OrganizerApplicationRead
}) {
  const badge = APPLICATION_STATUS_BADGES[application.status]
  return (
    <Card className="gap-4 px-4 py-4 sm:px-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-heading-lg">主辦方申請</h1>
        <StatusBadge tone={badge.tone}>{badge.label}</StatusBadge>
      </div>
      <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-2 text-body">
        <dt className="text-muted-foreground">社團名稱</dt>
        <dd className="break-words">{application.club_name}</dd>
        <dt className="text-muted-foreground">學校</dt>
        <dd className="break-words">{application.school_name}</dd>
        <dt className="text-muted-foreground">送出時間</dt>
        <dd>
          <time dateTime={application.created_at}>
            {formatDateTime(application.created_at)}
          </time>
        </dd>
      </dl>
      {application.status === "pending" && (
        <p className="text-caption text-muted-foreground">
          {PENDING_SUMMARY_TEXT}
        </p>
      )}
    </Card>
  )
}

/**
 * S15 主辦方申請：沒有申請時顯示表單（Email 未驗證時整個停用並連到 S7）；
 * 有申請時顯示最新一筆的唯讀摘要。審核、退回原因與重送在 Story 1.8。
 */
export function OrganizerApplyPage() {
  const account = useCurrentAccount()
  const application = useMyOrganizerApplication()

  let content: ReactNode
  if (account.isPending || application.isPending) {
    content = (
      <div role="status" aria-busy="true" className="flex flex-col gap-5">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-14 w-full" />
        <Skeleton className="h-14 w-full" />
        <span className="sr-only">載入中</span>
      </div>
    )
  } else if (account.isError || application.isError) {
    const error = account.error ?? application.error
    content = (
      <div className="flex flex-col items-start gap-3">
        <h1 className="text-heading-lg">主辦方申請</h1>
        <p className="text-body text-destructive">
          {getErrorMessage(parseApiError(error))}
        </p>
        <Button
          variant="outline"
          onClick={() => {
            if (account.isError) account.refetch()
            if (application.isError) application.refetch()
          }}
        >
          重新載入
        </Button>
      </div>
    )
  } else if (application.data) {
    content = <ApplicationSummary application={application.data} />
  } else if (account.data.is_organizer) {
    content = (
      <div className="flex flex-col gap-2">
        <h1 className="text-heading-lg">主辦方申請</h1>
        <p className="text-body">{ALREADY_ORGANIZER_TEXT}</p>
      </div>
    )
  } else {
    content = <ApplicationForm key={account.data.id} account={account.data} />
  }

  return (
    <section className="mx-auto flex w-full max-w-md flex-col gap-6 py-8 sm:py-12">
      {content}
    </section>
  )
}
