import { zodResolver } from "@hookform/resolvers/zod"
import { PlusIcon, Trash2Icon } from "lucide-react"
import { useState } from "react"
import { useFieldArray, useForm } from "react-hook-form"
import { z } from "zod"

import type { GameIn, GameRead, ScoreType } from "@/client"
import { FormErrorAlert } from "@/components/common/FormErrorAlert"
import { Button } from "@/components/ui/button"
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { type ApiError, applyFieldErrors, parseApiError } from "@/lib/api-error"
import { SCORE_TYPE_LABELS } from "./admin-games"

// 與後端（tournaments/models.py）相同的規則；先在前端擋下，使用者看不到後端的 422
export const GAME_NAME_MAX_LENGTH = 100
export const RANK_TIER_NAME_MAX_LENGTH = 50
export const RANK_TIERS_MAX_COUNT = 100
export const ALLOWED_BO = [1, 3, 5, 7] as const
const INT_MAX = 2_147_483_647
const GAME_NAME_TAKEN = "GAME_NAME_TAKEN"
const SCORE_TYPES: ScoreType[] = ["win_loss", "rounds"]

/** 以 code point 計算長度，與後端 Python 的 `len()` 相同。 */
function codePointLength(value: string): number {
  return [...value].length
}

type Issue = { message: string }

/** 驗證名稱（去除前後空白）；不合法時回傳錯誤訊息。 */
function checkName(
  raw: string,
  label: string,
  maxLength: number,
): string | Issue {
  const name = raw.trim()
  if (!name) return { message: `請輸入${label}` }
  if (codePointLength(name) > maxLength) {
    return { message: `${label}最多 ${maxLength} 個字` }
  }
  return name
}

/** 中文輸入法打出的全形數字與負號（「５」「－１」）轉成半形，並去除前後空白。 */
function normalizeInteger(raw: string): string {
  return raw.normalize("NFKC").trim()
}

/** 把通過驗證的整數文字轉成數字。 */
function toInteger(raw: string): number {
  // `+ 0` 把 -0（輸入「-0」）轉成 0
  return Number(normalizeInteger(raw)) + 0
}

/** 驗證整數輸入框的文字；不合法時回傳錯誤訊息。 */
function checkInteger(
  raw: string,
  label: string,
  minimum: number,
): number | Issue {
  const text = normalizeInteger(raw)
  if (!text) return { message: `請輸入${label}` }
  if (!/^-?\d+$/.test(text)) return { message: `${label}請輸入整數` }
  const value = Number(text)
  if (value < minimum) return { message: `${label}不能小於 ${minimum}` }
  if (value > INT_MAX) return { message: `${label}太大` }
  return value
}

function nameField(label: string, maxLength: number) {
  return z.string().superRefine((raw, ctx) => {
    const result = checkName(raw, label, maxLength)
    if (typeof result !== "string") {
      ctx.addIssue({ code: "custom", message: result.message })
    }
  })
}

function integerField(label: string, minimum: number) {
  return z.string().superRefine((raw, ctx) => {
    const result = checkInteger(raw, label, minimum)
    if (typeof result !== "number") {
      ctx.addIssue({ code: "custom", message: result.message })
    }
  })
}

// 段位表整張一起驗證：每一列的錯誤都標在該列，名稱不分大小寫不能重複
const rankTiersField = z
  .array(z.object({ name: z.string(), score: z.string() }))
  .superRefine((tiers, ctx) => {
    if (tiers.length === 0) {
      ctx.addIssue({ code: "custom", message: "至少需要一筆段位" })
      return
    }
    if (tiers.length > RANK_TIERS_MAX_COUNT) {
      ctx.addIssue({
        code: "custom",
        message: `段位最多 ${RANK_TIERS_MAX_COUNT} 筆`,
      })
      return
    }
    const seen = new Set<string>()
    tiers.forEach((tier, index) => {
      const name = checkName(tier.name, "段位名稱", RANK_TIER_NAME_MAX_LENGTH)
      if (typeof name === "string") {
        // 與後端的 str.casefold() 一致：先轉大寫再轉小寫，「ß」與「SS」視為相同
        const key = name.toUpperCase().toLowerCase()
        if (seen.has(key)) {
          ctx.addIssue({
            code: "custom",
            message: `段位名稱「${name}」重複`,
            path: [index, "name"],
          })
        }
        seen.add(key)
      } else {
        ctx.addIssue({
          code: "custom",
          message: name.message,
          path: [index, "name"],
        })
      }
      const score = checkInteger(tier.score, "積分", 0)
      if (typeof score !== "number") {
        ctx.addIssue({
          code: "custom",
          message: score.message,
          path: [index, "score"],
        })
      }
    })
  })

// 表單值都是輸入框的文字；通過驗證後再以 toGameIn 轉成 API 的型別
export const gameSchema = z.object({
  name: nameField("遊戲名稱", GAME_NAME_MAX_LENGTH),
  starters: integerField("先發人數", 1),
  substitutes: integerField("替補人數", 0),
  default_bo: z.string().superRefine((raw, ctx) => {
    if (!raw) {
      ctx.addIssue({ code: "custom", message: "請選擇預設 BO 數" })
    } else if (!(ALLOWED_BO as readonly number[]).includes(Number(raw))) {
      ctx.addIssue({ code: "custom", message: "BO 數只能是 1、3、5 或 7" })
    }
  }),
  game_minutes: integerField("每局預估時間", 1),
  score_type: z.string().superRefine((raw, ctx) => {
    if (!SCORE_TYPES.some((type) => type === raw)) {
      ctx.addIssue({ code: "custom", message: "請選擇比分型態" })
    }
  }),
  rank_tiers: rankTiersField,
})

export type GameFormInput = z.infer<typeof gameSchema>

/** 把通過驗證的表單值轉成 API 的 `GameIn`（名稱去除前後空白、數字轉成整數）。 */
export function toGameIn(values: GameFormInput): GameIn {
  return {
    name: values.name.trim(),
    starters: toInteger(values.starters),
    substitutes: toInteger(values.substitutes),
    default_bo: Number(values.default_bo),
    game_minutes: toInteger(values.game_minutes),
    score_type: values.score_type as ScoreType,
    rank_tiers: values.rank_tiers.map((tier) => ({
      name: tier.name.trim(),
      score: toInteger(tier.score),
    })),
  }
}

const EMPTY_TIER = { name: "", score: "" }

/** 新增遊戲的空白表單：段位表先放一列空白。 */
export const EMPTY_GAME_FORM: GameFormInput = {
  name: "",
  starters: "",
  substitutes: "",
  default_bo: "",
  game_minutes: "",
  score_type: "",
  rank_tiers: [EMPTY_TIER],
}

/** 編輯時預填遊戲的現值。 */
export function gameToFormInput(game: GameRead): GameFormInput {
  return {
    name: game.name,
    starters: String(game.starters),
    substitutes: String(game.substitutes),
    default_bo: String(game.default_bo),
    game_minutes: String(game.game_minutes),
    score_type: game.score_type,
    rank_tiers: game.rank_tiers.map((tier) => ({
      name: tier.name,
      score: String(tier.score),
    })),
  }
}

type GameFormProps = {
  defaultValues: GameFormInput
  submitLabel: string
  /** 送出合法資料；reject 時錯誤寫回表單（409 名稱重複標在名稱欄位） */
  onSubmit: (values: GameIn) => Promise<unknown>
  pending: boolean
}

/** S36 新增與編輯遊戲共用的表單：基本設定＋段位對照表（可新增、刪除列）。 */
export function GameForm({
  defaultValues,
  submitLabel,
  onSubmit,
  pending,
}: GameFormProps) {
  const [formError, setFormError] = useState<ApiError | null>(null)
  const form = useForm<GameFormInput>({
    resolver: zodResolver(gameSchema),
    defaultValues,
  })
  const tiers = useFieldArray({ control: form.control, name: "rank_tiers" })
  const tiersError =
    form.formState.errors.rank_tiers?.message ??
    form.formState.errors.rank_tiers?.root?.message

  const submit = form.handleSubmit(async (values) => {
    setFormError(null)
    try {
      await onSubmit(toGameIn(values))
    } catch (error) {
      const parsed = parseApiError(error)
      if (parsed.kind === "business" && parsed.code === GAME_NAME_TAKEN) {
        form.setError(
          "name",
          { type: "server", message: parsed.message },
          { shouldFocus: true },
        )
        return
      }
      setFormError(applyFieldErrors(form, error))
    }
  })

  return (
    <Form {...form}>
      <form noValidate onSubmit={submit} className="flex flex-col gap-6">
        <FormErrorAlert error={formError} />
        <FormField
          control={form.control}
          name="name"
          render={({ field }) => (
            <FormItem>
              <FormLabel>遊戲名稱</FormLabel>
              <FormControl>
                <Input {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <div className="grid gap-5 sm:grid-cols-2">
          <FormField
            control={form.control}
            name="starters"
            render={({ field }) => (
              <FormItem>
                <FormLabel>先發人數</FormLabel>
                <FormControl>
                  <Input inputMode="numeric" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="substitutes"
            render={({ field }) => (
              <FormItem>
                <FormLabel>替補人數</FormLabel>
                <FormControl>
                  <Input inputMode="numeric" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="default_bo"
            render={({ field }) => (
              <FormItem>
                <FormLabel>預設 BO 數</FormLabel>
                <Select value={field.value} onValueChange={field.onChange}>
                  <FormControl>
                    <SelectTrigger className="w-full" onBlur={field.onBlur}>
                      <SelectValue placeholder="選擇 BO 數" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    {ALLOWED_BO.map((bo) => (
                      <SelectItem key={bo} value={String(bo)}>
                        BO{bo}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="game_minutes"
            render={({ field }) => (
              <FormItem>
                <FormLabel>每局預估時間（分鐘）</FormLabel>
                <FormControl>
                  <Input inputMode="numeric" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="score_type"
            render={({ field }) => (
              <FormItem>
                <FormLabel>比分型態</FormLabel>
                <Select value={field.value} onValueChange={field.onChange}>
                  <FormControl>
                    <SelectTrigger className="w-full" onBlur={field.onBlur}>
                      <SelectValue placeholder="選擇比分型態" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    {SCORE_TYPES.map((type) => (
                      <SelectItem key={type} value={type}>
                        {SCORE_TYPE_LABELS[type]}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>

        <fieldset className="flex min-w-0 flex-col gap-3">
          <legend className="mb-3 text-heading-md">段位對照表</legend>
          <div
            aria-hidden="true"
            className="grid grid-cols-[minmax(0,1fr)_6rem_2.25rem] gap-2 text-caption text-muted-foreground"
          >
            <span>段位名稱</span>
            <span>積分</span>
          </div>
          <ul aria-label="段位" className="flex flex-col gap-3">
            {tiers.fields.map((tier, index) => (
              <li
                key={tier.id}
                className="grid grid-cols-[minmax(0,1fr)_6rem_2.25rem] items-start gap-2"
              >
                <FormField
                  control={form.control}
                  name={`rank_tiers.${index}.name`}
                  render={({ field }) => (
                    <FormItem className="min-w-0">
                      <FormLabel className="sr-only">
                        第 {index + 1} 筆段位名稱
                      </FormLabel>
                      <FormControl>
                        <Input {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name={`rank_tiers.${index}.score`}
                  render={({ field }) => (
                    <FormItem className="min-w-0">
                      <FormLabel className="sr-only">
                        第 {index + 1} 筆積分
                      </FormLabel>
                      <FormControl>
                        <Input inputMode="numeric" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  aria-label={`刪除第 ${index + 1} 筆段位`}
                  onClick={() => tiers.remove(index)}
                >
                  <Trash2Icon aria-hidden="true" />
                </Button>
              </li>
            ))}
          </ul>
          {tiersError && (
            <p role="alert" className="text-sm text-destructive">
              {tiersError}
            </p>
          )}
          <Button
            type="button"
            variant="outline"
            className="self-start"
            disabled={tiers.fields.length >= RANK_TIERS_MAX_COUNT}
            onClick={() => tiers.append(EMPTY_TIER)}
          >
            <PlusIcon aria-hidden="true" />
            新增段位
          </Button>
        </fieldset>

        <LoadingButton
          type="submit"
          // 驗證中或送出後到換頁前也停用，避免連點送出兩次
          loading={pending || form.formState.isSubmitting}
          className="w-full sm:w-auto sm:self-start"
        >
          {submitLabel}
        </LoadingButton>
      </form>
    </Form>
  )
}
