import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation } from "@tanstack/react-query"
import { CircleCheckIcon } from "lucide-react"
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

// 不論 Email 是否已註冊，伺服器回應都相同；這句話也不能透露帳號是否存在
export const RESET_REQUESTED_TEXT =
  "若這個 Email 已註冊，重設信會在幾分鐘內寄達。"

const forgotPasswordSchema = z.object({
  email: z
    .string()
    .trim()
    .min(1, "請輸入 Email")
    .pipe(z.email("請輸入有效的 Email")),
})

type ForgotPasswordInput = z.input<typeof forgotPasswordSchema>
type ForgotPasswordValues = z.output<typeof forgotPasswordSchema>

/** S8 忘記密碼：輸入 Email 寄重設信；送出後顯示同一則訊息，不透露 Email 是否已註冊。 */
export function ForgotPasswordForm() {
  const [formError, setFormError] = useState<ApiError | null>(null)
  const form = useForm<ForgotPasswordInput, unknown, ForgotPasswordValues>({
    resolver: zodResolver(forgotPasswordSchema),
    defaultValues: { email: "" },
  })

  const request = useMutation({
    mutationFn: async (values: ForgotPasswordValues) =>
      IdentityService.requestPasswordResetEmail({
        body: { email: values.email },
      }),
    onError: (error) => setFormError(applyFieldErrors(form, error)),
  })

  return (
    <Form {...form}>
      <form
        noValidate
        onSubmit={form.handleSubmit((values) => {
          setFormError(null)
          request.mutate(values)
        })}
        className="flex flex-col gap-4"
      >
        <FormErrorAlert error={formError} />
        {/* 一直存在的 status 區域：送出後填入文字，螢幕閱讀器才會唸出來 */}
        <p
          role="status"
          className="flex items-start gap-2 text-body empty:hidden"
        >
          {request.isSuccess && (
            <>
              <CircleCheckIcon
                aria-hidden="true"
                className="mt-0.5 size-4 shrink-0 text-primary"
              />
              {RESET_REQUESTED_TEXT}
            </>
          )}
        </p>
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
          loading={request.isPending}
          className="w-full"
        >
          寄送重設信
        </LoadingButton>
      </form>
    </Form>
  )
}
