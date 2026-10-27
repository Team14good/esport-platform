import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"

import { type AccountRead, IdentityService } from "@/client"
import { FormErrorAlert } from "@/components/common/FormErrorAlert"
import { Button } from "@/components/ui/button"
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
import { Label } from "@/components/ui/label"
import { LoadingButton } from "@/components/ui/loading-button"
import { Skeleton } from "@/components/ui/skeleton"
import {
  type ApiError,
  applyFieldErrors,
  getErrorMessage,
  parseApiError,
} from "@/lib/api-error"
import { notifySuccess } from "@/lib/feedback"
import { currentAccountQueryOptions, useCurrentAccount } from "./auth"
import { SchoolPicker } from "./SchoolPicker"
import { codePointLength, DISPLAY_NAME_MAX_LENGTH } from "./SignupForm"
import { useSchools } from "./schools"
import { useResendVerificationEmail } from "./VerificationRequired"

export const PROFILE_SAVED_TEXT = "帳號資料已更新。"

// 與後端（及 S5 註冊）相同的規則；伺服器的 422 仍會寫回對應欄位
const profileSchema = z.object({
  display_name: z
    .string()
    .trim()
    .min(1, "請輸入顯示名稱")
    .refine((value) => codePointLength(value) <= DISPLAY_NAME_MAX_LENGTH, {
      message: `顯示名稱最多 ${DISPLAY_NAME_MAX_LENGTH} 個字`,
    }),
  school_id: z.string().nullable(),
})

type ProfileInput = z.input<typeof profileSchema>
type ProfileValues = z.output<typeof profileSchema>

function ProfileForm({ account }: { account: AccountRead }) {
  const queryClient = useQueryClient()
  const schools = useSchools()
  const resend = useResendVerificationEmail()
  const [formError, setFormError] = useState<ApiError | null>(null)
  const form = useForm<ProfileInput, unknown, ProfileValues>({
    resolver: zodResolver(profileSchema),
    defaultValues: {
      display_name: account.display_name,
      school_id: account.school_id ?? null,
    },
  })

  const update = useMutation({
    mutationFn: async (values: ProfileValues) =>
      (await IdentityService.updateCurrentAccount({ body: values })).data,
    onSuccess: (updated) => {
      queryClient.setQueryData(currentAccountQueryOptions().queryKey, updated)
      form.reset({
        display_name: updated.display_name,
        school_id: updated.school_id ?? null,
      })
      notifySuccess(PROFILE_SAVED_TEXT)
    },
    onError: (error) => setFormError(applyFieldErrors(form, error)),
  })

  return (
    <Form {...form}>
      <form
        noValidate
        onSubmit={form.handleSubmit((values) => {
          setFormError(null)
          update.mutate(values)
        })}
        className="flex flex-col gap-5"
      >
        <FormErrorAlert error={formError} />
        <div className="flex flex-col gap-2">
          <Label htmlFor="account-email">Email</Label>
          <Input
            id="account-email"
            type="email"
            value={account.email}
            readOnly
            aria-describedby="account-email-description"
            className="text-muted-foreground"
          />
          <p
            id="account-email-description"
            className="text-muted-foreground text-sm"
          >
            {account.email_verified
              ? "Email 已驗證，無法在這裡修改。"
              : "Email 尚未驗證；完成驗證後才能報名賽事或申請成為主辦方。Email 無法在這裡修改。"}
          </p>
          {!account.email_verified && (
            <LoadingButton
              type="button"
              variant="outline"
              size="sm"
              className="self-start"
              loading={resend.isPending}
              onClick={() => resend.mutate(account.email)}
            >
              重寄驗證信
            </LoadingButton>
          )}
        </div>
        <FormField
          control={form.control}
          name="display_name"
          render={({ field }) => (
            <FormItem>
              <FormLabel>顯示名稱</FormLabel>
              <FormControl>
                <Input autoComplete="nickname" {...field} />
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
                />
              </FormControl>
              <FormDescription>
                選填；只能從學校清單選擇，參加校園賽時必須設定。
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />
        <LoadingButton
          type="submit"
          loading={update.isPending}
          className="mt-1 w-full sm:w-auto sm:self-start"
        >
          儲存帳號資料
        </LoadingButton>
      </form>
    </Form>
  )
}

/** S10 帳號資料：修改顯示名稱與學校（School picker，可清除）；Email 唯讀，不能改密碼。 */
export function AccountProfilePage() {
  const account = useCurrentAccount()

  return (
    <section className="mx-auto flex w-full max-w-md flex-col gap-6 py-8 sm:py-12">
      <h1 className="text-heading-lg">帳號資料</h1>
      {account.isPending ? (
        <div role="status" aria-busy="true" className="flex flex-col gap-5">
          <Skeleton className="h-14 w-full" />
          <Skeleton className="h-14 w-full" />
          <Skeleton className="h-14 w-full" />
          <span className="sr-only">載入中</span>
        </div>
      ) : account.isError ? (
        <div className="flex flex-col items-start gap-3">
          <p className="text-body text-destructive">
            {getErrorMessage(parseApiError(account.error))}
          </p>
          <Button variant="outline" onClick={() => account.refetch()}>
            重新載入
          </Button>
        </div>
      ) : (
        <ProfileForm key={account.data.id} account={account.data} />
      )}
    </section>
  )
}
