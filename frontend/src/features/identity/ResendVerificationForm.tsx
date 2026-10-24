import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation } from "@tanstack/react-query"
import { useState } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"

import { IdentityService } from "@/client"
import { FormErrorAlert } from "@/components/common/FormErrorAlert"
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import { Input } from "@/components/ui/input"
import { LoadingButton } from "@/components/ui/loading-button"
import { type ApiError, applyFieldErrors } from "@/lib/api-error"
import { notifySuccess } from "@/lib/feedback"

// 不論 Email 是否存在或已驗證，伺服器回應都相同；這句話也不能透露帳號是否存在
export const RESEND_SUCCESS_TEXT =
  "若這個 Email 尚未驗證，驗證信會在幾分鐘內寄達。"

const resendSchema = z.object({
  email: z
    .string()
    .trim()
    .min(1, "請輸入 Email")
    .pipe(z.email("請輸入有效的 Email")),
})

type ResendInput = z.input<typeof resendSchema>
type ResendValues = z.output<typeof resendSchema>

/** S7 的「重寄驗證信」：以 Email 識別，預設帶入剛註冊的 Email。 */
export function ResendVerificationForm({
  defaultEmail,
  redirect,
}: {
  defaultEmail?: string
  redirect?: string
}) {
  const [formError, setFormError] = useState<ApiError | null>(null)
  const form = useForm<ResendInput, unknown, ResendValues>({
    resolver: zodResolver(resendSchema),
    defaultValues: { email: defaultEmail ?? "" },
  })

  const resend = useMutation({
    mutationFn: async (values: ResendValues) =>
      IdentityService.resendVerificationEmail({
        body: { email: values.email, redirect: redirect ?? null },
      }),
    onSuccess: () => notifySuccess(RESEND_SUCCESS_TEXT),
    onError: (error) => setFormError(applyFieldErrors(form, error)),
  })

  return (
    <Form {...form}>
      <form
        noValidate
        onSubmit={form.handleSubmit((values) => {
          setFormError(null)
          resend.mutate(values)
        })}
        className="flex flex-col gap-4"
      >
        <FormErrorAlert error={formError} />
        <FormField
          control={form.control}
          name="email"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Email</FormLabel>
              <FormControl>
                <Input
                  type="email"
                  autoComplete="email"
                  inputMode="email"
                  {...field}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <LoadingButton
          type="submit"
          loading={resend.isPending}
          className="w-full"
        >
          重寄驗證信
        </LoadingButton>
      </form>
    </Form>
  )
}
