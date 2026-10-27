import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useRouter } from "@tanstack/react-router"
import { useState } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"

import { type Identity, IdentityService } from "@/client"
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
import { PasswordInput } from "@/components/ui/password-input"
import { type ApiError, applyFieldErrors } from "@/lib/api-error"
import {
  getLastIdentity,
  identitiesQueryOptions,
  postLoginDestination,
  signIn,
} from "./auth"
import { safeRedirect } from "./redirect"

// 只檢查有沒有填：Email 格式不符與帳密錯誤一樣交給伺服器回「Email 或密碼錯誤。」
const loginSchema = z.object({
  email: z.string().trim().min(1, "請輸入 Email"),
  password: z.string().min(1, "請輸入密碼"),
})

type LoginInput = z.input<typeof loginSchema>
type LoginValues = z.output<typeof loginSchema>

/** S6 登入表單：成功後依 redirect、身分數量與上次身分導向（見 postLoginDestination）。 */
export function LoginForm({ redirect }: { redirect?: string }) {
  const router = useRouter()
  const queryClient = useQueryClient()
  const [formError, setFormError] = useState<ApiError | null>(null)
  const form = useForm<LoginInput, unknown, LoginValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
  })

  const login = useMutation({
    mutationFn: async (values: LoginValues) =>
      (await IdentityService.login({ body: values })).data,
    onSuccess: async (token) => {
      signIn(queryClient, token.access_token)
      // 有合格的 redirect 時直接回原頁，不必先取得身分清單
      let identities: Identity[] = []
      if (!safeRedirect(redirect)) {
        try {
          // 不重試：登入已成功，拿不到身分清單就直接退回 S1，不讓使用者多等
          identities = await queryClient.fetchQuery({
            ...identitiesQueryOptions(),
            retry: false,
          })
        } catch {
          // 身分清單暫時拿不到：視為只有一種身分（回 S1），頂欄的切換器會再重新取得
        }
      }
      const destination = postLoginDestination({
        redirect,
        identities,
        lastIdentity: getLastIdentity(),
      })
      // redirect 可能帶 ?query 與 #hash：以完整網址交給 history
      router.history.push(destination)
    },
    onError: (error) => {
      form.resetField("password")
      setFormError(applyFieldErrors(form, error))
    },
  })

  return (
    <Form {...form}>
      <form
        noValidate
        onSubmit={form.handleSubmit((values) => {
          setFormError(null)
          login.mutate(values)
        })}
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
                <PasswordInput autoComplete="current-password" {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <LoadingButton
          type="submit"
          loading={login.isPending}
          className="mt-1 w-full"
        >
          登入
        </LoadingButton>
      </form>
    </Form>
  )
}
