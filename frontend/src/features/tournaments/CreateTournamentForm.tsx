import { zodResolver } from "@hookform/resolvers/zod"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { ChevronDownIcon } from "lucide-react"
import { type ReactNode, useEffect, useId, useRef, useState } from "react"
import {
  type Control,
  type FieldPath,
  useForm,
  useFormState,
  useWatch,
} from "react-hook-form"
import { z } from "zod"

import type { GameRead, TournamentCreate, TournamentMode } from "@/client"
import { ConfirmDialog } from "@/components/common/ConfirmDialog"
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  type ApiError,
  applyFieldErrors,
  getErrorMessage,
  parseApiError,
} from "@/lib/api-error"
import { taipeiLocalToIso } from "@/lib/datetime"
import { notifySuccess } from "@/lib/feedback"
import {
  organizerGamesQueryOptions,
  useCreateTournament,
} from "./organizer-queries"
import { roundLabel, totalRounds } from "./round-bo"

export const TOURNAMENT_CREATED_TEXT = "已建立賽事。"
export const CAPACITY_WARNING_THRESHOLD = 128
export const CAPACITY_WARNING_TITLE = "確認名額"
export const CAPACITY_WARNING_TEXT = "名額超過 128 隊，請確認沒有輸入錯誤"
export const SUBMIT_TEXT = "建立賽事"
export const ALLOWED_BO = [1, 3, 5, 7] as const
export const ROUND_BO_TOGGLE_TEXT = "分輪 BO"
export const ROUND_BO_HINT =
  "沒有設定的輪次沿用上方的 BO。BO 較大的輪次，下一輪會自動順延。"
export const ROUND_BO_NEED_CAPACITY_TEXT = "先輸入名額，才能依名額列出輪次。"
const ROUND_BO_DEFAULT = "default"
export const MODE_LABEL_TEXT = "賽事模式"
export const TOURNAMENT_MODE_OPTIONS: {
  value: TournamentMode
  label: string
}[] = [
  { value: "campus", label: "校園賽" },
  { value: "custom", label: "自訂" },
]
/** 優先期的預設值（小時）；S28 自訂改回校園賽時也預填這個值 */
export const DEFAULT_PRIORITY_HOURS = "24"

// 與後端 models.py 相同的限制
const TOURNAMENT_NAME_MAX_LENGTH = 100
const LIVESTREAM_URL_MAX_LENGTH = 2048
export const INT_MAX = 2_147_483_647
export const MIN_CAPACITY = 2
export const MIN_FORFEIT_MINUTES = 15
export const MIN_APPEAL_MINUTES = 30
export const GAME_NOT_FOUND = "GAME_NOT_FOUND"

/** 每輪間隔的下限：棄權時限＋BO × 每局預估時間＋申訴期（與後端 `min_round_interval` 相同）。 */
export function minRoundInterval({
  forfeit,
  bo,
  gameMinutes,
  appeal,
}: {
  forfeit: number
  bo: number
  gameMinutes: number
  appeal: number
}): number {
  return forfeit + bo * gameMinutes + appeal
}

export function roundIntervalTooShortText(minimum: number): string {
  return `每輪間隔至少 ${minimum} 分鐘`
}

/** 表單值：輸入框一律是字串，送出前才轉型（S28 賽事設定也用同一份）。 */
export const formShape = z.object({
  name: z.string(),
  game_id: z.string(),
  // 賽事模式（Story 3.10）：自訂賽事沒有優先期
  mode: z.enum(["campus", "custom"]),
  capacity: z.string(),
  starters: z.string(),
  substitutes: z.string(),
  bo: z.string(),
  registration_start: z.string(),
  registration_end: z.string(),
  priority_hours: z.string(),
  start_at: z.string(),
  round_interval_minutes: z.string(),
  forfeit_minutes: z.string(),
  appeal_minutes: z.string(),
  livestream_url: z.string(),
  // 分輪 BO：索引是距決賽的輪數（決賽＝0），值是 "default" 或 BO 數
  round_bo: z.array(z.string()),
})

export type CreateTournamentValues = z.infer<typeof formShape>
export type FieldName = keyof CreateTournamentValues
// 以單一字串輸入的欄位（分輪 BO 是清單、模式是選項，另外處理）
type TextFieldName = Exclude<FieldName, "round_bo" | "mode">

const DEFAULT_VALUES: CreateTournamentValues = {
  name: "",
  game_id: "",
  mode: "campus",
  capacity: "",
  starters: "",
  substitutes: "",
  bo: "",
  registration_start: "",
  registration_end: "",
  priority_hours: DEFAULT_PRIORITY_HOURS,
  start_at: "",
  round_interval_minutes: "",
  forfeit_minutes: "15",
  appeal_minutes: "30",
  livestream_url: "",
  round_bo: [],
}

const INTEGER_FIELDS: { name: TextFieldName; label: string; min: number }[] = [
  { name: "capacity", label: "名額", min: MIN_CAPACITY },
  { name: "starters", label: "先發人數", min: 1 },
  { name: "substitutes", label: "替補人數", min: 0 },
  { name: "priority_hours", label: "優先期", min: 0 },
  { name: "round_interval_minutes", label: "每輪間隔", min: 1 },
  { name: "forfeit_minutes", label: "棄權時限", min: MIN_FORFEIT_MINUTES },
  { name: "appeal_minutes", label: "申訴期", min: MIN_APPEAL_MINUTES },
]

const DATETIME_FIELDS: { name: TextFieldName; label: string }[] = [
  { name: "registration_start", label: "報名開始" },
  { name: "registration_end", label: "報名截止" },
  { name: "start_at", label: "開賽時間" },
]

/** 整數欄位的值；空白、小數或其他文字回傳 null。 */
export function parseInteger(value: string): number | null {
  const text = value.trim()
  return /^-?\d+$/.test(text) ? Number(text) : null
}

/** 直播連結的錯誤訊息；空白（不填）或合法時回傳 null。 */
export function livestreamUrlError(value: string): string | null {
  const url = value.trim()
  if (!url) return null
  if ([...url].length > LIVESTREAM_URL_MAX_LENGTH)
    return `直播連結最多 ${LIVESTREAM_URL_MAX_LENGTH} 個字`
  if (!isHttpUrl(url)) return "直播連結必須是 http:// 或 https:// 開頭的網址"
  return null
}

function isHttpUrl(value: string): boolean {
  try {
    const url = new URL(value)
    return (
      (url.protocol === "http:" || url.protocol === "https:") &&
      url.hostname.length > 0
    )
  } catch {
    return false
  }
}

/**
 * 與後端相同的檢查（`models.py` 欄位規則與 `service._validate_schedule`）。
 * 全部寫在一個 superRefine：任一欄位錯誤時，其他欄位的錯誤仍會一起顯示。
 * `currentGame`（S28）：賽事目前的遊戲以快照的每局預估時間計算最小間隔，
 * 遊戲已不在清單中也視為已選。
 */
export function createTournamentSchema(
  games: readonly GameRead[] | (() => readonly GameRead[]),
  { currentGame }: { currentGame?: { id: string; game_minutes: number } } = {},
) {
  return formShape.superRefine((values, ctx) => {
    const gameList = typeof games === "function" ? games() : games
    const fail = (path: FieldName, message: string) =>
      ctx.addIssue({ code: "custom", path: [path], message })

    const name = values.name.trim()
    if (!name) fail("name", "請輸入賽事名稱")
    else if ([...name].length > TOURNAMENT_NAME_MAX_LENGTH)
      fail("name", `賽事名稱最多 ${TOURNAMENT_NAME_MAX_LENGTH} 個字`)

    const game =
      currentGame && values.game_id === currentGame.id
        ? currentGame
        : gameList.find((item) => item.id === values.game_id)
    if (!game) fail("game_id", "請選擇遊戲")

    // 自訂賽事沒有優先期（欄位隱藏、送出 0），不檢查
    const isCustom = values.mode === "custom"
    const numbers: Partial<Record<FieldName, number>> = {}
    for (const field of INTEGER_FIELDS) {
      if (isCustom && field.name === "priority_hours") continue
      const raw = values[field.name]
      if (!raw.trim()) {
        fail(field.name, `請輸入${field.label}`)
        continue
      }
      const value = parseInteger(raw)
      if (value === null) fail(field.name, "請輸入整數")
      else if (value < field.min)
        fail(field.name, `${field.label}不能小於 ${field.min}`)
      else if (value > INT_MAX) fail(field.name, `${field.label}太大`)
      else numbers[field.name] = value
    }

    const bo = Number(values.bo)
    const boValid = (ALLOWED_BO as readonly number[]).includes(bo)
    if (!boValid) fail("bo", "BO 數只能是 1、3、5 或 7")

    const times: Partial<Record<FieldName, number>> = {}
    for (const field of DATETIME_FIELDS) {
      const raw = values[field.name]
      if (!raw) {
        fail(field.name, `請輸入${field.label}`)
        continue
      }
      const iso = taipeiLocalToIso(raw)
      if (iso === null) fail(field.name, "請輸入正確的日期時間")
      else times[field.name] = new Date(iso).getTime()
    }

    const start = times.registration_start
    const end = times.registration_end
    const startAt = times.start_at
    if (end !== undefined && startAt !== undefined && end > startAt) {
      fail("registration_end", "報名截止不能晚於開賽時間")
    }
    if (start !== undefined && end !== undefined) {
      if (start >= end) {
        fail("registration_start", "報名開始必須早於報名截止")
      } else if (
        numbers.priority_hours !== undefined &&
        numbers.priority_hours * 3_600_000 > end - start
      ) {
        fail("priority_hours", "優先期結束（報名開始＋優先期）不能晚於報名截止")
      }
    }

    const interval = numbers.round_interval_minutes
    const forfeit = numbers.forfeit_minutes
    const appeal = numbers.appeal_minutes
    if (
      game &&
      boValid &&
      interval !== undefined &&
      forfeit !== undefined &&
      appeal !== undefined
    ) {
      const minimum = minRoundInterval({
        forfeit,
        bo,
        gameMinutes: game.game_minutes,
        appeal,
      })
      if (interval < minimum)
        fail("round_interval_minutes", roundIntervalTooShortText(minimum))
    }

    const urlError = livestreamUrlError(values.livestream_url)
    if (urlError) fail("livestream_url", urlError)
  })
}

/** 已通過檢查的表單值轉成 API 的 body；時間由台北時間轉成 UTC。 */
export function toTournamentCreate(
  values: CreateTournamentValues,
): TournamentCreate {
  const int = (value: string) => Number(value.trim())
  const iso = (value: string) => taipeiLocalToIso(value) ?? value
  const url = values.livestream_url.trim()
  // 只送名額可能的輪次中、有設定的那些（名額改小後，超出的輪次不送）
  const rounds = totalRounds(int(values.capacity))
  const roundBo = values.round_bo.flatMap((value, roundsFromFinal) => {
    const bo = Number(value)
    return roundsFromFinal < rounds && isAllowedBo(bo)
      ? [{ rounds_from_final: roundsFromFinal, bo }]
      : []
  })
  return {
    name: values.name.trim(),
    game_id: values.game_id,
    mode: values.mode,
    capacity: int(values.capacity),
    starters: int(values.starters),
    substitutes: int(values.substitutes),
    bo: int(values.bo),
    registration_start: iso(values.registration_start),
    registration_end: iso(values.registration_end),
    // 自訂賽事沒有優先期：一律送 0（後端也會忽略）
    priority_hours: values.mode === "custom" ? 0 : int(values.priority_hours),
    start_at: iso(values.start_at),
    round_interval_minutes: int(values.round_interval_minutes),
    forfeit_minutes: int(values.forfeit_minutes),
    appeal_minutes: int(values.appeal_minutes),
    livestream_url: url || null,
    round_bo: roundBo,
  }
}

function isAllowedBo(value: number): boolean {
  return (ALLOWED_BO as readonly number[]).includes(value)
}

/** 名額欄位的值可以列出輪次時回傳總輪數，否則（空白、不是整數、超出範圍）回傳 null。 */
function roundsForCapacity(capacity: string): number | null {
  const value = parseInteger(capacity)
  return value !== null && value >= MIN_CAPACITY && value <= INT_MAX
    ? totalRounds(value)
    : null
}

/**
 * S26 的「分輪 BO」：預設收合，展開後依名額列出輪次（決賽在最上），
 * 每列可選「沿用預設」或 BO1／3／5／7。伺服器的 `round_bo` 錯誤顯示在下方並自動展開。
 * S28 也用這個元件；`disabled` 時各輪選單停用（仍可展開查看）。
 */
export function RoundBoField({
  control,
  capacity,
  bo,
  disabled = false,
}: {
  control: Control<CreateTournamentValues>
  capacity: string
  bo: string
  disabled?: boolean
}) {
  const [open, setOpen] = useState(false)
  const panelId = useId()
  // 收到伺服器的 round_bo 錯誤時展開；之後仍由使用者自行收合
  const { errors } = useFormState({ control, name: "round_bo" })
  const roundBoError = errors.round_bo
  useEffect(() => {
    if (roundBoError) setOpen(true)
  }, [roundBoError])
  const rounds = roundsForCapacity(capacity)
  const defaultBo = Number(bo)
  const defaultLabel = isAllowedBo(defaultBo)
    ? `沿用預設（BO${defaultBo}）`
    : "沿用預設"

  return (
    <FormField
      control={control}
      name="round_bo"
      render={({ field }) => {
        const expanded = open
        return (
          <FormItem className="min-w-0 sm:col-span-2">
            <Button
              type="button"
              variant="outline"
              className="justify-self-start"
              aria-expanded={expanded}
              aria-controls={panelId}
              onClick={() => setOpen((value) => !value)}
            >
              <ChevronDownIcon
                aria-hidden
                className={expanded ? "rotate-180" : undefined}
              />
              {ROUND_BO_TOGGLE_TEXT}
            </Button>
            {/* 一律渲染，收合時隱藏：aria-controls 才會一直指向存在的元素 */}
            <div
              id={panelId}
              hidden={!expanded}
              // `flex` 會蓋過 hidden 屬性的 display: none，收合時改用 `hidden`
              className={expanded ? "flex min-w-0 flex-col gap-3" : "hidden"}
            >
              <p className="text-sm text-muted-foreground">{ROUND_BO_HINT}</p>
              {rounds === null ? (
                <p className="text-sm text-muted-foreground">
                  {ROUND_BO_NEED_CAPACITY_TEXT}
                </p>
              ) : (
                <ul className="flex min-w-0 flex-col gap-3">
                  {Array.from({ length: rounds }, (_, roundsFromFinal) => {
                    const selectId = `${panelId}-${roundsFromFinal}`
                    return (
                      <li
                        key={roundsFromFinal}
                        className="grid min-w-0 grid-cols-[minmax(0,1fr)_minmax(0,14rem)] items-center gap-3"
                      >
                        <Label htmlFor={selectId}>
                          {roundLabel(roundsFromFinal)}
                        </Label>
                        <Select
                          disabled={disabled}
                          value={
                            field.value[roundsFromFinal] || ROUND_BO_DEFAULT
                          }
                          onValueChange={(value) => {
                            const next = Array.from(
                              {
                                length: Math.max(field.value.length, rounds),
                              },
                              (_, index) =>
                                field.value[index] || ROUND_BO_DEFAULT,
                            )
                            next[roundsFromFinal] = value
                            field.onChange(next)
                          }}
                        >
                          <SelectTrigger
                            id={selectId}
                            className="w-full"
                            onBlur={field.onBlur}
                          >
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value={ROUND_BO_DEFAULT}>
                              {defaultLabel}
                            </SelectItem>
                            {ALLOWED_BO.map((value) => (
                              <SelectItem key={value} value={String(value)}>
                                {`BO${value}`}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </li>
                    )
                  })}
                </ul>
              )}
            </div>
            <FormMessage />
          </FormItem>
        )
      }}
    />
  )
}

/**
 * 賽事模式選單（S26、S28 共用）：校園賽／自訂。`onModeChange` 在使用者改選時呼叫
 * （例如 S28 改回校園賽時預填優先期）。
 */
export function TournamentModeField({
  control,
  disabled = false,
  description,
  onModeChange,
}: {
  control: Control<CreateTournamentValues>
  disabled?: boolean
  description?: ReactNode
  onModeChange?: (mode: TournamentMode) => void
}) {
  return (
    <FormField
      control={control}
      name="mode"
      render={({ field }) => (
        <FormItem>
          <FormLabel>{MODE_LABEL_TEXT}</FormLabel>
          <Select
            value={field.value}
            onValueChange={(value) => {
              field.onChange(value)
              onModeChange?.(value as TournamentMode)
            }}
            disabled={disabled}
          >
            <FormControl>
              <SelectTrigger
                className="w-full"
                onBlur={field.onBlur}
                ref={field.ref}
              >
                <SelectValue />
              </SelectTrigger>
            </FormControl>
            <SelectContent>
              {TOURNAMENT_MODE_OPTIONS.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {description && <FormDescription>{description}</FormDescription>}
          <FormMessage />
        </FormItem>
      )}
    />
  )
}

type TextFieldProps = {
  control: Control<CreateTournamentValues>
  name: FieldPath<CreateTournamentValues>
  label: string
  type?: "text" | "number" | "datetime-local" | "url"
  description?: ReactNode
  /** 數字欄位是數字；`datetime-local` 是台北時間字串（S28 的下限） */
  min?: number | string
  max?: string
  autoComplete?: string
  disabled?: boolean
}

export function TextField({
  control,
  name,
  label,
  type = "text",
  description,
  min,
  max,
  autoComplete = "off",
  disabled = false,
}: TextFieldProps) {
  return (
    <FormField
      control={control}
      name={name}
      render={({ field }) => (
        <FormItem>
          <FormLabel>{label}</FormLabel>
          <FormControl>
            <Input
              type={type}
              inputMode={type === "number" ? "numeric" : undefined}
              min={min}
              max={max}
              step={type === "number" ? 1 : undefined}
              autoComplete={autoComplete}
              {...field}
              disabled={disabled}
            />
          </FormControl>
          {description && <FormDescription>{description}</FormDescription>}
          <FormMessage />
        </FormItem>
      )}
    />
  )
}

export function FormSection({
  title,
  children,
}: {
  title: string
  children: ReactNode
}) {
  return (
    <fieldset className="flex min-w-0 flex-col gap-4">
      <legend className="mb-4 text-heading-md">{title}</legend>
      <div className="grid min-w-0 gap-4 sm:grid-cols-2">{children}</div>
    </fieldset>
  )
}

export const TAIPEI_TIME_HINT = "台北時間"

/** 跨欄位檢查：改變 key 時要一起重新檢查的欄位。 */
export const CROSS_FIELD_DEPENDENTS: Partial<Record<FieldName, FieldName[]>> = {
  game_id: ["round_interval_minutes"],
  bo: ["round_interval_minutes"],
  forfeit_minutes: ["round_interval_minutes"],
  appeal_minutes: ["round_interval_minutes"],
  start_at: ["registration_end"],
  registration_start: ["priority_hours"],
  registration_end: ["registration_start", "priority_hours"],
}

/** S26 建立賽事表單。 */
export function CreateTournamentForm() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const games = useQuery(organizerGamesQueryOptions())
  const gameList = games.data ?? []
  // resolver 只建立一次，檢查時讀最新的遊戲清單
  const gamesRef = useRef(gameList)
  gamesRef.current = gameList
  const [resolver] = useState(() =>
    zodResolver(createTournamentSchema(() => gamesRef.current)),
  )
  const [formError, setFormError] = useState<ApiError | null>(null)
  // 名額超過 128 時，送出前要確認的 body
  const [pendingBody, setPendingBody] = useState<TournamentCreate | null>(null)
  const create = useCreateTournament()

  const form = useForm<CreateTournamentValues>({
    resolver,
    defaultValues: DEFAULT_VALUES,
  })

  const [gameId, bo, forfeit, appeal, capacity, mode] = useWatch({
    control: form.control,
    name: [
      "game_id",
      "bo",
      "forfeit_minutes",
      "appeal_minutes",
      "capacity",
      "mode",
    ],
  })
  const selectedGame = gameList.find((game) => game.id === gameId)
  const boValue = Number(bo)
  const forfeitValue = parseInteger(forfeit)
  const appealValue = parseInteger(appeal)
  const currentMinimum =
    selectedGame &&
    (ALLOWED_BO as readonly number[]).includes(boValue) &&
    forfeitValue !== null &&
    appealValue !== null
      ? minRoundInterval({
          forfeit: forfeitValue,
          bo: boValue,
          gameMinutes: selectedGame.game_minutes,
          appeal: appealValue,
        })
      : null

  const selectGame = (id: string, onChange: (value: string) => void) => {
    onChange(id)
    const game = gameList.find((item) => item.id === id)
    if (!game) return
    // 每次換遊戲都重新帶入該遊戲的預設值（之後仍可修改）
    form.setValue("starters", String(game.starters))
    form.setValue("substitutes", String(game.substitutes))
    form.setValue("bo", String(game.default_bo))
    form.clearErrors(["starters", "substitutes", "bo"])
  }

  // 防止重複送出：resolver 是非同步的，連按時 create.isPending 還沒變成 true；
  // 成功後到導向完成之前也不能再送
  const inFlight = useRef(false)

  // 第一次送出後，改變某個欄位時連帶重新檢查依賴它的欄位，跨欄位的錯誤才不會停在舊的結果
  useEffect(() => {
    const subscription = form.watch((_values, { name }) => {
      if (!name || !form.formState.isSubmitted) return
      const dependents = CROSS_FIELD_DEPENDENTS[name as FieldName]
      if (dependents) void form.trigger(dependents)
    })
    return () => subscription.unsubscribe()
  }, [form])

  const submit = (body: TournamentCreate) => {
    if (inFlight.current) return
    inFlight.current = true
    setFormError(null)
    create.mutate(body, {
      onSuccess: (created) => {
        notifySuccess(TOURNAMENT_CREATED_TEXT)
        void navigate({
          to: "/organizer/tournaments/$tournamentId",
          params: { tournamentId: created.id },
        })
      },
      onError: (error) => {
        // 只有失敗時才能再送；成功後會導向 S27，不再接受送出
        inFlight.current = false
        setFormError(applyFieldErrors(form, error))
        // 遊戲剛被移除：重抓清單，選單才不會留著不存在的遊戲
        const parsed = parseApiError(error)
        if (parsed.kind === "business" && parsed.code === GAME_NOT_FOUND) {
          void queryClient.invalidateQueries({
            queryKey: organizerGamesQueryOptions().queryKey,
          })
        }
      },
    })
  }

  return (
    <section className="flex min-w-0 max-w-3xl flex-col gap-6">
      <h1 className="text-heading-lg">建立賽事</h1>
      <Form {...form}>
        <form
          noValidate
          onSubmit={form.handleSubmit((values) => {
            if (inFlight.current) return
            const body = toTournamentCreate(values)
            if (body.capacity > CAPACITY_WARNING_THRESHOLD) {
              setPendingBody(body)
            } else {
              submit(body)
            }
          })}
          className="flex flex-col gap-8"
        >
          <FormErrorAlert error={formError} />

          <FormSection title="基本資料">
            <div className="sm:col-span-2">
              <TextField control={form.control} name="name" label="賽事名稱" />
            </div>
            <FormField
              control={form.control}
              name="game_id"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>遊戲</FormLabel>
                  <Select
                    value={field.value || undefined}
                    onValueChange={(value) => selectGame(value, field.onChange)}
                    disabled={games.isPending || (games.isError && !games.data)}
                  >
                    <FormControl>
                      <SelectTrigger
                        className="w-full"
                        onBlur={field.onBlur}
                        ref={field.ref}
                      >
                        <SelectValue
                          placeholder={
                            games.isPending ? "載入遊戲中" : "選擇遊戲"
                          }
                        />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {gameList.map((game) => (
                        <SelectItem key={game.id} value={game.id}>
                          {game.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {games.isError && !games.data ? (
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-sm text-destructive">
                        {getErrorMessage(parseApiError(games.error))}
                      </p>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => games.refetch()}
                      >
                        重新載入
                      </Button>
                    </div>
                  ) : games.isSuccess && gameList.length === 0 ? (
                    <FormDescription>
                      目前沒有可選的遊戲，請聯絡平台管理員新增。
                    </FormDescription>
                  ) : null}
                  <FormMessage />
                </FormItem>
              )}
            />
            <TextField
              control={form.control}
              name="capacity"
              label="名額"
              type="number"
              min={MIN_CAPACITY}
              description="正取隊伍數"
            />
            <TournamentModeField
              control={form.control}
              onModeChange={() => form.clearErrors("priority_hours")}
            />
          </FormSection>

          <FormSection title="隊伍與賽制">
            <TextField
              control={form.control}
              name="starters"
              label="先發人數"
              type="number"
              min={1}
            />
            <TextField
              control={form.control}
              name="substitutes"
              label="替補人數"
              type="number"
              min={0}
            />
            <FormField
              control={form.control}
              name="bo"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>BO</FormLabel>
                  <Select
                    value={field.value || undefined}
                    onValueChange={field.onChange}
                  >
                    <FormControl>
                      <SelectTrigger
                        className="w-full"
                        onBlur={field.onBlur}
                        ref={field.ref}
                      >
                        <SelectValue placeholder="選擇 BO 數" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {ALLOWED_BO.map((value) => (
                        <SelectItem key={value} value={String(value)}>
                          {`BO${value}`}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <FormDescription>
                    沒有分輪設定的輪次都用這個 BO 數。
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
            <RoundBoField control={form.control} capacity={capacity} bo={bo} />
          </FormSection>

          <FormSection title="報名與賽程">
            <TextField
              control={form.control}
              name="registration_start"
              label="報名開始"
              type="datetime-local"
              description={TAIPEI_TIME_HINT}
            />
            <TextField
              control={form.control}
              name="registration_end"
              label="報名截止"
              type="datetime-local"
              description={TAIPEI_TIME_HINT}
            />
            {mode === "custom" ? null : (
              <TextField
                control={form.control}
                name="priority_hours"
                label="優先期（小時）"
                type="number"
                min={0}
                description="從報名開始起算。"
              />
            )}
            <TextField
              control={form.control}
              name="start_at"
              label="開賽時間"
              type="datetime-local"
              description={TAIPEI_TIME_HINT}
            />
            <TextField
              control={form.control}
              name="round_interval_minutes"
              label="每輪間隔（分鐘）"
              type="number"
              min={1}
              description={
                currentMinimum !== null && selectedGame
                  ? `目前的最小間隔：${currentMinimum} 分鐘（棄權時限＋BO × 每局 ${selectedGame.game_minutes} 分鐘＋申訴期）`
                  : undefined
              }
            />
          </FormSection>

          <FormSection title="比賽規則">
            <TextField
              control={form.control}
              name="forfeit_minutes"
              label="棄權時限（分鐘）"
              type="number"
              min={MIN_FORFEIT_MINUTES}
              description={`至少 ${MIN_FORFEIT_MINUTES} 分鐘`}
            />
            <TextField
              control={form.control}
              name="appeal_minutes"
              label="申訴期（分鐘）"
              type="number"
              min={MIN_APPEAL_MINUTES}
              description={`至少 ${MIN_APPEAL_MINUTES} 分鐘`}
            />
            <div className="sm:col-span-2">
              <TextField
                control={form.control}
                name="livestream_url"
                label="直播連結（選填）"
                type="url"
                autoComplete="url"
              />
            </div>
          </FormSection>

          <LoadingButton
            type="submit"
            loading={form.formState.isSubmitting || create.isPending}
            className="w-full sm:w-auto sm:self-start"
          >
            {SUBMIT_TEXT}
          </LoadingButton>
        </form>
      </Form>
      <ConfirmDialog
        title={CAPACITY_WARNING_TITLE}
        description={CAPACITY_WARNING_TEXT}
        confirmLabel={SUBMIT_TEXT}
        open={pendingBody !== null}
        onOpenChange={(open) => {
          if (!open) setPendingBody(null)
        }}
        onConfirm={async () => {
          // 只啟動 mutation、不等它完成：對話框隨即關閉，伺服器的欄位錯誤寫回表單，
          // 而不是留在對話框裡。先取出並清掉 pendingBody，連按確認也只送一次
          const body = pendingBody
          setPendingBody(null)
          if (body) submit(body)
        }}
      />
    </section>
  )
}
