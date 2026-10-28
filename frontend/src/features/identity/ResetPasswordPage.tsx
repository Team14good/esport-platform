import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link, useNavigate } from "@tanstack/react-router"
import { TriangleAlertIcon } from "lucide-react"
import { useState } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"

import { IdentityService } from "@/client"
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
import { LoadingButton } from "@/components/ui/loading-button"
import { PasswordInput } from "@/components/ui/password-input"
import { Skeleton } from "@/components/ui/skeleton"
import {
  type ApiError,
  applyFieldErrors,
  getErrorMessage,
  parseApiError,
} from "@/lib/api-error"
import { notifySuccess } from "@/lib/feedback"
import { signOut } from "./auth"
import { PASSWORD_MIN_LENGTH, passwordSchema } from "./SignupForm"
import { PageCard } from "./VerifyEmailPage"

export const RESET_LINK_INVALID = "RESET_LINK_INVALID"
export const PASSWORD_RESET_TEXT = "密碼已重設，請用新密碼登入。"

/** 連結本身失效：`RESET_LINK_INVALID`，或 token 格式不合格（被截斷或改壞的連結，重試也不會成功）。 */
function isInvalidLink(error: unknown): boolean {
  const apiError = parseApiError(error)
  if (apiError.kind === "business") return apiError.code === RESET_LINK_INVALID
  return apiError.kind === "validation" && "token" in apiError.fields
}

/** S9 連結失效：「此重設連結已失效。」＋「重新寄送重設信」（→ S8）。 */
function InvalidLink() {
  return (
    <PageCard
      icon={
        <TriangleAlertIcon
          aria-hidden="true"
          className="size-10 text-destructive"
        />
      }
      title="此重設連結已失效。"
    >
      <p className="text-center text-body text-muted-foreground">
        連結用過一次、超過 1
        小時，或之後又申請過重設信，就會失效。請重新寄送一封重設信。
      </p>
      <Button asChild className="w-full">
        <Link to="/forgot-password">重新寄送重設信</Link>
      </Button>
    </PageCard>
  )
}

const resetSchema = z.object({ new_password: passwordSchema })

type ResetInput = z.input<typeof resetSchema>
type ResetValues = z.output<typeof resetSchema>

/** S9 設定新密碼表單：成功後清除這個瀏覽器的登入狀態（舊 token 已失效），導向 S6。 */
function ResetPasswordForm({
  token,
  onLinkInvalid,
}: {
  token: string
  onLinkInvalid: () => void
}) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [formError, setFormError] = useState<ApiError | null>(null)
  const form = useForm<ResetInput, unknown, ResetValues>({
    resolver: zodResolver(resetSchema),
    defaultValues: { new_password: "" },
  })

  const reset = useMutation({
    mutationFn: async (values: ResetValues) =>
      IdentityService.resetPassword({
        body: { token, new_password: values.new_password },
      }),
    onSuccess: () => {
      signOut(queryClient)
      notifySuccess(PASSWORD_RESET_TEXT)
      // replace：上一頁不會回到帶 token 的網址
      navigate({ to: "/login", replace: true })
    },
    onError: (error) => {
      // 開啟後才失效（過期、被重新申請作廢、在別的分頁用掉了）
      if (isInvalidLink(error)) {
        onLinkInvalid()
        return
      }
      setFormError(applyFieldErrors(form, error))
    },
  })

  return (
    <section className="mx-auto flex w-full max-w-md flex-col gap-6 py-8 sm:py-12">
      <div className="flex flex-col gap-2">
        <h1 className="text-heading-lg">設定新密碼</h1>
        <p className="text-body text-muted-foreground">
          設定後，其他裝置上的登入會失效，請用新密碼重新登入。
        </p>
      </div>
      <Form {...form}>
        <form
          noValidate
          onSubmit={form.handleSubmit((values) => {
            setFormError(null)
            reset.mutate(values)
          })}
          className="flex flex-col gap-5"
        >
          <FormErrorAlert error={formError} />
          <FormField
            control={form.control}
            name="new_password"
            render={({ field }) => (
              <FormItem>
                <FormLabel>新密碼</FormLabel>
                <FormControl>
                  <PasswordInput autoComplete="new-password" {...field} />
                </FormControl>
                <FormDescription>
                  至少 {PASSWORD_MIN_LENGTH} 個字元，不限字元種類。
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
          <LoadingButton
            type="submit"
            loading={reset.isPending}
            className="mt-1 w-full"
          >
            設定新密碼
          </LoadingButton>
        </form>
      </Form>
    </section>
  )
}

/** S9 開啟時先檢查連結（不會用掉 token），有效才顯示設定新密碼的表單。 */
function CheckedReset({ token }: { token: string }) {
  const [linkInvalidated, setLinkInvalidated] = useState(false)
  // 用 query：同一個 token 只檢查一次（StrictMode 重複掛載、切回分頁都不重送）
  const check = useQuery({
    queryKey: ["identity", "password-reset-check", token],
    queryFn: async () => {
      await IdentityService.checkPasswordResetLink({ body: { token } })
      return true
    },
    retry: false,
    staleTime: Number.POSITIVE_INFINITY,
    gcTime: Number.POSITIVE_INFINITY,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  })

  if (linkInvalidated) return <InvalidLink />

  if (check.isPending) {
    return (
      <section
        className="mx-auto flex w-full max-w-md flex-col gap-4 py-12"
        role="status"
        aria-busy="true"
      >
        <Skeleton className="h-8 w-40" />
        <Skeleton className="h-10 w-full" />
        <span className="sr-only">正在檢查重設連結</span>
      </section>
    )
  }

  if (check.isError) {
    if (isInvalidLink(check.error)) return <InvalidLink />
    // 連線失敗或伺服器錯誤：不代表連結失效，讓使用者重試同一個連結
    return (
      <PageCard
        icon={
          <TriangleAlertIcon
            aria-hidden="true"
            className="size-10 text-destructive"
          />
        }
        title={getErrorMessage(parseApiError(check.error))}
      >
        <LoadingButton
          type="button"
          className="w-full"
          loading={check.isFetching}
          onClick={() => check.refetch()}
        >
          重試
        </LoadingButton>
      </PageCard>
    )
  }

  return (
    <ResetPasswordForm
      token={token}
      onLinkInvalid={() => setLinkInvalidated(true)}
    />
  )
}

/** S9 重設密碼頁：網址沒有 token 時直接視為失效連結。 */
export function ResetPasswordPage({ token }: { token?: string }) {
  if (!token) return <InvalidLink />
  return <CheckedReset key={token} token={token} />
}
