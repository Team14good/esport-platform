import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { useState } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"

import { IdentityService } from "@/client"
import { FormErrorAlert } from "@/components/common/FormErrorAlert"
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
import { PasswordInput } from "@/components/ui/password-input"
import { type ApiError, applyFieldErrors } from "@/lib/api-error"
import "./history-state"
import { SchoolPicker } from "./SchoolPicker"
import { useSchools } from "./schools"

export const PASSWORD_MIN_LENGTH = 8
export const PASSWORD_MAX_LENGTH = 128
export const DISPLAY_NAME_MAX_LENGTH = 50

/** 以 Unicode 碼位計算長度，與後端（Python len）一致；emoji 等字元算 1 個字。 */
export function codePointLength(value: string): number {
  return [...value].length
}

/** 密碼規則（註冊與 S9 設定新密碼共用），與後端 `PasswordField` 相同。 */
export const passwordSchema = z
  .string()
  .refine((value) => codePointLength(value) >= PASSWORD_MIN_LENGTH, {
    message: `密碼至少需要 ${PASSWORD_MIN_LENGTH} 個字元`,
  })
  .refine((value) => codePointLength(value) <= PASSWORD_MAX_LENGTH, {
    message: `密碼最多 ${PASSWORD_MAX_LENGTH} 個字元`,
  })

// 與後端相同的規則；送出前先在前端擋下，伺服器的 422 仍會寫回對應欄位
const signupSchema = z.object({
  email: z
    .string()
    .trim()
    .min(1, "請輸入 Email")
    .pipe(z.email("請輸入有效的 Email")),
  password: passwordSchema,
  display_name: z
    .string()
    .trim()
    .min(1, "請輸入顯示名稱")
    .refine((value) => codePointLength(value) <= DISPLAY_NAME_MAX_LENGTH, {
      message: `顯示名稱最多 ${DISPLAY_NAME_MAX_LENGTH} 個字`,
    }),
  school_id: z.string().nullable(),
})

type SignupInput = z.input<typeof signupSchema>
type SignupValues = z.output<typeof signupSchema>

/** S5 註冊表單：成功後導向 S7「請收信驗證」，不自動登入。 */
export function SignupForm({ redirect }: { redirect?: string }) {
  const navigate = useNavigate()
  const schools = useSchools()
  const [formError, setFormError] = useState<ApiError | null>(null)
  const form = useForm<SignupInput, unknown, SignupValues>({
    resolver: zodResolver(signupSchema),
    defaultValues: {
      email: "",
      password: "",
      display_name: "",
      school_id: null,
    },
  })

  const register = useMutation({
    mutationFn: async (values: SignupValues) =>
      (
        await IdentityService.register({
          body: { ...values, redirect: redirect ?? null },
        })
      ).data,
    onSuccess: (account) => {
      navigate({
        to: "/verify-email",
        search: redirect ? { redirect } : {},
        state: { registeredEmail: account.email },
      })
    },
    onError: (error) => {
      setFormError(applyFieldErrors(form, error))
    },
  })

  const onSubmit = (values: SignupValues) => {
    setFormError(null)
    register.mutate(values)
  }

  return (
    <Form {...form}>
      <form
        noValidate
        onSubmit={form.handleSubmit(onSubmit)}
        className="flex flex-col gap-5"
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
        <FormField
          control={form.control}
          name="password"
          render={({ field }) => (
            <FormItem>
              <FormLabel>密碼</FormLabel>
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
          loading={register.isPending}
          className="mt-1 w-full"
        >
          註冊帳號
        </LoadingButton>
      </form>
    </Form>
  )
}
