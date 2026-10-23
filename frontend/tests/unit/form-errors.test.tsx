import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { useState } from "react"
import { useForm } from "react-hook-form"
import { describe, expect, it } from "vitest"

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
import { type ApiError, applyFieldErrors } from "@/lib/api-error"
import { httpError } from "./helpers"

type Values = { email: string; display_name: string }

function TestForm({ submitError }: { submitError: unknown }) {
  const form = useForm<Values>({
    defaultValues: { email: "", display_name: "" },
  })
  const [formError, setFormError] = useState<ApiError | null>(null)

  const onSubmit = async () => {
    setFormError(null)
    try {
      throw submitError
    } catch (error) {
      setFormError(applyFieldErrors(form, error))
    }
  }

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)}>
        <FormErrorAlert error={formError} />
        {(["email", "display_name"] as const).map((name) => (
          <FormField
            key={name}
            control={form.control}
            name={name}
            render={({ field }) => (
              <FormItem data-testid={`field-${name}`}>
                <FormLabel>{name}</FormLabel>
                <FormControl>
                  <Input {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        ))}
        <button type="submit">送出表單</button>
      </form>
    </Form>
  )
}

async function submit(submitError: unknown) {
  const user = userEvent.setup()
  render(<TestForm submitError={submitError} />)
  await user.click(screen.getByRole("button", { name: "送出表單" }))
}

describe("表單錯誤呈現", () => {
  it("422 欄位錯誤顯示在對應欄位下方，找不到欄位的改顯示在表單頂部 Alert", async () => {
    await submit(
      httpError(422, {
        detail: [
          { loc: ["body", "email"], msg: "請輸入有效的 Email", type: "x" },
          { loc: ["body", "school_id"], msg: "找不到這間學校", type: "x" },
        ],
      }),
    )

    expect(
      within(screen.getByTestId("field-email")).getByText("請輸入有效的 Email"),
    ).toBeInTheDocument()
    const alert = screen.getByRole("alert")
    expect(alert).toHaveTextContent("找不到這間學校")
    expect(alert).not.toHaveTextContent("請輸入有效的 Email")
    expect(
      within(screen.getByTestId("field-display_name")).queryByText(
        "找不到這間學校",
      ),
    ).toBeNull()
  })

  it("422 錯誤全部寫進欄位時不顯示 Alert", async () => {
    await submit(
      httpError(422, {
        detail: [
          { loc: ["body", "display_name"], msg: "請輸入顯示名稱", type: "x" },
        ],
      }),
    )

    expect(
      within(screen.getByTestId("field-display_name")).getByText(
        "請輸入顯示名稱",
      ),
    ).toBeInTheDocument()
    expect(screen.queryByRole("alert")).toBeNull()
  })

  it("表單業務錯誤：表單頂部 Alert 照實顯示 message", async () => {
    await submit(
      httpError(409, {
        detail: {
          code: "EMAIL_ALREADY_REGISTERED",
          message: "這個 Email 已經註冊過。",
        },
      }),
    )

    expect(screen.getByRole("alert")).toHaveTextContent(
      "這個 Email 已經註冊過。",
    )
  })
})
