import { zodResolver } from "@hookform/resolvers/zod"
import { useQuery } from "@tanstack/react-query"
import type { LinkOptions } from "@tanstack/react-router"
import { useEffect, useId, useRef, useState } from "react"
import { useForm, useWatch } from "react-hook-form"

import type {
  GameRead,
  TournamentRead,
  TournamentStatus,
  TournamentUpdate,
} from "@/client"
import { ConfirmDialog } from "@/components/common/ConfirmDialog"
import { FormErrorAlert } from "@/components/common/FormErrorAlert"
import { PageBannerSlot } from "@/components/common/PageBanner"
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
import { type ApiError, applyFieldErrors } from "@/lib/api-error"
import { isoToTaipeiLocal, taipeiLocalToIso } from "@/lib/datetime"
import { notifySuccess } from "@/lib/feedback"
import {
  ALLOWED_BO,
  CROSS_FIELD_DEPENDENTS,
  type CreateTournamentValues,
  createTournamentSchema,
  type FieldName,
  FormSection,
  formShape,
  INT_MAX,
  livestreamUrlError,
  MIN_APPEAL_MINUTES,
  MIN_CAPACITY,
  MIN_FORFEIT_MINUTES,
  minRoundInterval,
  parseInteger,
  RoundBoField,
  TAIPEI_TIME_HINT,
  TextField,
  toTournamentCreate,
} from "./CreateTournamentForm"
import {
  myTournamentQueryOptions,
  organizerGamesQueryOptions,
  useRaiseCapacity,
  useUpdateTournament,
} from "./organizer-queries"

// S28 賽事設定（Story 2.5）：依賽事狀態限制可改的欄位（與後端 `update_tournament` 相同）。

export const SETTINGS_TITLE = "賽事設定"
export const SAVE_SETTINGS_TEXT = "儲存設定"
export const SETTINGS_SAVED_TEXT = "已儲存設定。"
export const SETTINGS_LOCKED_BANNER_TEXT = "抽籤後只能修改場次時間"
export const NOT_EDITABLE_BANNER_TEXT = "已結束或已取消的賽事不能修改。"
export const RAISE_CAPACITY_TEXT = "提高名額"
export const RAISE_CAPACITY_CONFIRM_TEXT = "候補會依順位立即遞補，無法復原。"
export const CAPACITY_RAISED_TEXT = "已提高名額。"
export const NEW_CAPACITY_LABEL = "新名額"

/**
 * 可修改的範圍：
 * - `full`：尚未開放，全部欄位都能改
 * - `relax`：開放報名、報名截止，只能延長時限、改分輪 BO 與直播連結；名額另以「提高名額」修改
 * - `livestream`：賽程已公布、進行中，只能改直播連結
 * - `readonly`：已結束、已取消
 */
export type SettingsMode = "full" | "relax" | "livestream" | "readonly"

export function settingsMode(status: TournamentStatus): SettingsMode {
  switch (status) {
    case "upcoming":
      return "full"
    case "open":
    case "closed":
      return "relax"
    case "published":
    case "ongoing":
      return "livestream"
    default:
      return "readonly"
  }
}

// 開放報名後仍可修改的欄位
const RELAX_FIELDS: ReadonlySet<FieldName> = new Set<FieldName>([
  "registration_end",
  "forfeit_minutes",
  "appeal_minutes",
  "round_interval_minutes",
  "round_bo",
  "livestream_url",
])

function isEditable(mode: SettingsMode, field: FieldName): boolean {
  if (mode === "full") return true
  if (mode === "relax") return RELAX_FIELDS.has(field)
  if (mode === "livestream") return field === "livestream_url"
  return false
}

// 開放報名後只能延長的數字欄位
const RELAX_MINIMUM_FIELDS = [
  {
    name: "forfeit_minutes",
    message: "開放報名後棄權時限只能延長",
  },
  {
    name: "appeal_minutes",
    message: "開放報名後申訴期只能延長",
  },
  {
    name: "round_interval_minutes",
    message: "開放報名後每輪間隔只能延長",
  },
] as const

const HOUR_MS = 3_600_000
const MINUTE_MS = 60_000

/** 開放報名後報名截止的上限：開賽時間的前一分鐘（必須早於開賽時間）。 */
function latestRegistrationEnd(tournament: TournamentRead): string {
  return isoToTaipeiLocal(
    new Date(Date.parse(tournament.start_at) - MINUTE_MS).toISOString(),
  )
}

/** 賽事目前的值轉成表單值（時間為台北時間、到分鐘）。 */
export function toSettingsValues(
  tournament: TournamentRead,
): CreateTournamentValues {
  const priorityHours = Math.floor(
    (Date.parse(tournament.priority_end) -
      Date.parse(tournament.registration_start)) /
      HOUR_MS,
  )
  const roundBo: string[] = []
  for (const item of tournament.round_bo) {
    roundBo[item.rounds_from_final] = String(item.bo)
  }
  return {
    name: tournament.name,
    game_id: tournament.game_id,
    capacity: String(tournament.capacity),
    starters: String(tournament.starters),
    substitutes: String(tournament.substitutes),
    bo: String(tournament.bo),
    registration_start: isoToTaipeiLocal(tournament.registration_start),
    registration_end: isoToTaipeiLocal(tournament.registration_end),
    priority_hours: String(priorityHours),
    start_at: isoToTaipeiLocal(tournament.start_at),
    round_interval_minutes: String(tournament.round_interval_minutes),
    forfeit_minutes: String(tournament.forfeit_minutes),
    appeal_minutes: String(tournament.appeal_minutes),
    livestream_url: tournament.livestream_url ?? "",
    round_bo: Array.from(roundBo, (value) => value ?? "default"),
  }
}

type UpdateField = Exclude<keyof TournamentUpdate, "round_bo">

const SIMPLE_FIELDS: UpdateField[] = [
  "name",
  "game_id",
  "capacity",
  "registration_start",
  "registration_end",
  "priority_hours",
  "start_at",
  "round_interval_minutes",
  "forfeit_minutes",
  "appeal_minutes",
  "starters",
  "substitutes",
  "bo",
  "livestream_url",
]

/**
 * 只送有變動、且目前狀態可以修改的欄位（以表單字串與初始值比較，時間不受秒數影響）。
 * 換遊戲時先發、替補、BO 一併送出，伺服器才不會改帶新遊戲的預設值。
 */
export function toTournamentUpdate(
  values: CreateTournamentValues,
  initial: CreateTournamentValues,
  tournament: TournamentRead,
  mode: SettingsMode,
): TournamentUpdate {
  const full = toTournamentCreate(values)
  const body: TournamentUpdate = {}
  const gameChanged = values.game_id !== initial.game_id
  const assign = <K extends UpdateField>(field: K) => {
    ;(body as Record<UpdateField, unknown>)[field] =
      full[field as keyof typeof full]
  }
  for (const field of SIMPLE_FIELDS) {
    if (!isEditable(mode, field)) continue
    const changed =
      values[field] !== initial[field] ||
      (gameChanged &&
        (field === "starters" || field === "substitutes" || field === "bo"))
    if (changed) assign(field)
  }
  if (isEditable(mode, "round_bo")) {
    const current = JSON.stringify(
      [...tournament.round_bo].sort(
        (a, b) => a.rounds_from_final - b.rounds_from_final,
      ),
    )
    if (JSON.stringify(full.round_bo) !== current) body.round_bo = full.round_bo
  }
  return body
}

/** 各狀態的檢查：可修改的欄位沿用建立賽事的檢查，開放報名後另檢查不能縮短。 */
function settingsSchema(
  tournament: TournamentRead,
  mode: SettingsMode,
  games: () => readonly GameRead[],
  initial: CreateTournamentValues,
) {
  if (mode === "livestream" || mode === "readonly") {
    return formShape.superRefine((values, ctx) => {
      const message = livestreamUrlError(values.livestream_url)
      if (message)
        ctx.addIssue({ code: "custom", path: ["livestream_url"], message })
    })
  }
  const base = createTournamentSchema(games, {
    currentGame: {
      id: tournament.game_id,
      game_minutes: tournament.game_minutes,
    },
  })
  if (mode === "full") return base
  return base.superRefine((values, ctx) => {
    const end = taipeiLocalToIso(values.registration_end)
    const initialEnd = taipeiLocalToIso(initial.registration_end)
    if (end && initialEnd && Date.parse(end) < Date.parse(initialEnd)) {
      ctx.addIssue({
        code: "custom",
        path: ["registration_end"],
        message: "開放報名後報名截止只能延後",
      })
    }
    const startAt = taipeiLocalToIso(values.start_at)
    if (end && startAt && Date.parse(end) >= Date.parse(startAt)) {
      ctx.addIssue({
        code: "custom",
        path: ["registration_end"],
        message: "報名截止必須早於開賽時間",
      })
    }
    for (const field of RELAX_MINIMUM_FIELDS) {
      const value = parseInteger(values[field.name])
      if (value !== null && value < tournament[field.name]) {
        ctx.addIssue({
          code: "custom",
          path: [field.name],
          message: field.message,
        })
      }
    }
  })
}

/** S28 賽事設定頁。 */
export function TournamentSettingsPage({
  tournamentId,
}: {
  tournamentId: string
}) {
  const tournament = useQuery(myTournamentQueryOptions(tournamentId))
  // 放在表單外：409 後重抓賽事、表單重新掛載時，伺服器訊息仍留在畫面上
  const [formError, setFormError] = useState<ApiError | null>(null)
  // 儲存或提高名額成功時加 1：表單只在這時（或狀態改變時）以新值重建，
  // 背景重抓不會清掉沒儲存的修改
  const [version, setVersion] = useState(0)
  // 上層 layout 已載入賽事；這裡只在有資料時顯示
  if (!tournament.data) return null
  const data = tournament.data
  const mode = settingsMode(data.status)

  return (
    <section className="flex min-w-0 max-w-3xl flex-col gap-6">
      <PageBannerSlot
        banners={[
          mode === "livestream" && {
            children: SETTINGS_LOCKED_BANNER_TEXT,
            action: {
              label: "前往場次管理",
              to: `/organizer/tournaments/${encodeURIComponent(data.id)}/matches` as LinkOptions["to"],
            },
          },
          mode === "readonly" && { children: NOT_EDITABLE_BANNER_TEXT },
        ]}
      />
      <h1 className="text-heading-lg">{SETTINGS_TITLE}</h1>
      <FormErrorAlert error={formError} />
      {/* 儲存、提高名額成功或狀態改變後，以新的值重新建立表單 */}
      <SettingsForm
        key={`${data.status}:${version}`}
        tournament={data}
        mode={mode}
        onError={setFormError}
        onSaved={() => setVersion((value) => value + 1)}
      />
      {mode === "relax" && (
        <RaiseCapacitySection
          tournament={data}
          onRaised={() => {
            // 先前儲存失敗的訊息已不適用
            setFormError(null)
            setVersion((value) => value + 1)
          }}
        />
      )}
    </section>
  )
}

function SettingsForm({
  tournament,
  mode,
  onError,
  onSaved,
}: {
  tournament: TournamentRead
  mode: SettingsMode
  onError: (error: ApiError | null) => void
  onSaved: () => void
}) {
  const games = useQuery(organizerGamesQueryOptions())
  // 賽事目前的遊戲以快照的名稱顯示；遊戲已不在清單中時也列出
  const gameList: GameRead[] = [
    ...(games.data ?? []).filter((game) => game.id !== tournament.game_id),
  ]
  const currentGameOption = {
    id: tournament.game_id,
    name: tournament.game_name,
  }
  const gamesRef = useRef(gameList)
  gamesRef.current = gameList
  const [initial] = useState(() => toSettingsValues(tournament))
  const [resolver] = useState(() =>
    zodResolver(
      settingsSchema(tournament, mode, () => gamesRef.current, initial),
    ),
  )
  const update = useUpdateTournament(tournament.id)
  const inFlight = useRef(false)
  const form = useForm<CreateTournamentValues>({
    resolver,
    defaultValues: initial,
  })
  const editable = (field: FieldName) => isEditable(mode, field)
  const relax = mode === "relax"

  const [gameId, bo, forfeit, appeal, capacity] = useWatch({
    control: form.control,
    name: ["game_id", "bo", "forfeit_minutes", "appeal_minutes", "capacity"],
  })
  const gameMinutes =
    gameId === tournament.game_id
      ? tournament.game_minutes
      : gameList.find((game) => game.id === gameId)?.game_minutes
  const boValue = Number(bo)
  const forfeitValue = parseInteger(forfeit)
  const appealValue = parseInteger(appeal)
  const currentMinimum =
    gameMinutes !== undefined &&
    (ALLOWED_BO as readonly number[]).includes(boValue) &&
    forfeitValue !== null &&
    appealValue !== null
      ? minRoundInterval({
          forfeit: forfeitValue,
          bo: boValue,
          gameMinutes,
          appeal: appealValue,
        })
      : null

  const selectGame = (id: string, onChange: (value: string) => void) => {
    onChange(id)
    const game =
      id === tournament.game_id
        ? {
            starters: tournament.starters,
            substitutes: tournament.substitutes,
            default_bo: tournament.bo,
          }
        : gameList.find((item) => item.id === id)
    if (!game) return
    // 與 S26 相同：換遊戲時帶入該遊戲的預設值（之後仍可修改）
    form.setValue("starters", String(game.starters))
    form.setValue("substitutes", String(game.substitutes))
    form.setValue("bo", String(game.default_bo))
    form.clearErrors(["starters", "substitutes", "bo"])
  }

  useEffect(() => {
    const subscription = form.watch((_values, { name }) => {
      if (!name || !form.formState.isSubmitted) return
      const dependents = CROSS_FIELD_DEPENDENTS[name as FieldName]
      if (dependents) void form.trigger(dependents)
    })
    return () => subscription.unsubscribe()
  }, [form])

  const onSubmit = form.handleSubmit((values) => {
    if (inFlight.current) return
    inFlight.current = true
    onError(null)
    update.mutate(toTournamentUpdate(values, initial, tournament, mode), {
      onSuccess: () => {
        notifySuccess(SETTINGS_SAVED_TEXT)
        onSaved()
      },
      onError: (error) => onError(applyFieldErrors(form, error)),
      onSettled: () => {
        inFlight.current = false
      },
    })
  })

  // 開放報名後，數字欄位的輸入下限為目前值
  const numberMin = (field: FieldName, fallback: number) =>
    relax && editable(field) ? Number(initial[field]) : fallback

  return (
    <Form {...form}>
      <form noValidate onSubmit={onSubmit} className="flex flex-col gap-8">
        <FormSection title="基本資料">
          <div className="sm:col-span-2">
            <TextField
              control={form.control}
              name="name"
              label="賽事名稱"
              disabled={!editable("name")}
            />
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
                  disabled={!editable("game_id") || games.isPending}
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
                    {[currentGameOption, ...gameList].map((game) => (
                      <SelectItem key={game.id} value={game.id}>
                        {game.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
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
            disabled={!editable("capacity")}
            description={
              relax ? "要增加名額，請用下方的「提高名額」。" : "正取隊伍數"
            }
          />
        </FormSection>

        <FormSection title="隊伍與賽制">
          <TextField
            control={form.control}
            name="starters"
            label="先發人數"
            type="number"
            min={1}
            disabled={!editable("starters")}
          />
          <TextField
            control={form.control}
            name="substitutes"
            label="替補人數"
            type="number"
            min={0}
            disabled={!editable("substitutes")}
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
                  disabled={!editable("bo")}
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
          <RoundBoField
            control={form.control}
            capacity={capacity}
            bo={bo}
            disabled={!editable("round_bo")}
          />
        </FormSection>

        <FormSection title="報名與賽程">
          <TextField
            control={form.control}
            name="registration_start"
            label="報名開始"
            type="datetime-local"
            description={TAIPEI_TIME_HINT}
            disabled={!editable("registration_start")}
          />
          <TextField
            control={form.control}
            name="registration_end"
            label="報名截止"
            type="datetime-local"
            description={
              relax
                ? `${TAIPEI_TIME_HINT}；只能延後，須早於開賽時間`
                : TAIPEI_TIME_HINT
            }
            min={relax ? initial.registration_end : undefined}
            max={relax ? latestRegistrationEnd(tournament) : undefined}
            disabled={!editable("registration_end")}
          />
          <TextField
            control={form.control}
            name="priority_hours"
            label="優先期（小時）"
            type="number"
            min={0}
            description="從報名開始起算。"
            disabled={!editable("priority_hours")}
          />
          <TextField
            control={form.control}
            name="start_at"
            label="開賽時間"
            type="datetime-local"
            description={TAIPEI_TIME_HINT}
            disabled={!editable("start_at")}
          />
          <TextField
            control={form.control}
            name="round_interval_minutes"
            label="每輪間隔（分鐘）"
            type="number"
            min={numberMin("round_interval_minutes", 1)}
            disabled={!editable("round_interval_minutes")}
            description={
              currentMinimum !== null && gameMinutes !== undefined
                ? `目前的最小間隔：${currentMinimum} 分鐘（棄權時限＋BO × 每局 ${gameMinutes} 分鐘＋申訴期）`
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
            min={numberMin("forfeit_minutes", MIN_FORFEIT_MINUTES)}
            description={`至少 ${MIN_FORFEIT_MINUTES} 分鐘`}
            disabled={!editable("forfeit_minutes")}
          />
          <TextField
            control={form.control}
            name="appeal_minutes"
            label="申訴期（分鐘）"
            type="number"
            min={numberMin("appeal_minutes", MIN_APPEAL_MINUTES)}
            description={`至少 ${MIN_APPEAL_MINUTES} 分鐘`}
            disabled={!editable("appeal_minutes")}
          />
          <div className="sm:col-span-2">
            <TextField
              control={form.control}
              name="livestream_url"
              label="直播連結（選填）"
              type="url"
              autoComplete="url"
              description="清空後儲存即移除直播連結。"
              disabled={!editable("livestream_url")}
            />
          </div>
        </FormSection>

        {mode !== "readonly" && (
          <LoadingButton
            type="submit"
            loading={form.formState.isSubmitting || update.isPending}
            className="w-full sm:w-auto sm:self-start"
          >
            {SAVE_SETTINGS_TEXT}
          </LoadingButton>
        )}
      </form>
    </Form>
  )
}

/** 開放報名、報名截止時的「提高名額」：確認後經 3.7 的 API 送出，候補立即遞補。 */
function RaiseCapacitySection({
  tournament,
  onRaised,
}: {
  tournament: TournamentRead
  onRaised: () => void
}) {
  const inputId = useId()
  const errorId = useId()
  const [value, setValue] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState<number | null>(null)
  const raise = useRaiseCapacity(tournament.id)

  const open = () => {
    const capacity = parseInteger(value)
    if (capacity === null) {
      setError(value.trim() ? "請輸入整數" : "請輸入新名額")
    } else if (capacity <= tournament.capacity) {
      setError(`新名額必須大於目前的名額（${tournament.capacity} 隊）。`)
    } else if (capacity > INT_MAX) {
      setError("名額太大")
    } else {
      setError(null)
      setPending(capacity)
    }
  }

  return (
    <fieldset className="flex min-w-0 flex-col gap-4">
      <legend className="mb-4 text-heading-md">{RAISE_CAPACITY_TEXT}</legend>
      <p className="text-sm text-muted-foreground">
        {`目前名額 ${tournament.capacity} 隊。提高後候補會依順位立即遞補。`}
      </p>
      <div className="grid min-w-0 gap-2 sm:max-w-xs">
        <Label htmlFor={inputId}>{NEW_CAPACITY_LABEL}</Label>
        <Input
          id={inputId}
          type="number"
          inputMode="numeric"
          min={tournament.capacity + 1}
          step={1}
          value={value}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? errorId : undefined}
          onChange={(event) => setValue(event.target.value)}
        />
        {error && (
          <p id={errorId} className="text-sm text-destructive">
            {error}
          </p>
        )}
      </div>
      <Button
        type="button"
        variant="outline"
        className="w-full sm:w-auto sm:self-start"
        onClick={open}
      >
        {RAISE_CAPACITY_TEXT}
      </Button>
      <ConfirmDialog
        title={RAISE_CAPACITY_TEXT}
        description={
          pending !== null
            ? `名額從 ${tournament.capacity} 隊提高到 ${pending} 隊。${RAISE_CAPACITY_CONFIRM_TEXT}`
            : RAISE_CAPACITY_CONFIRM_TEXT
        }
        confirmLabel={RAISE_CAPACITY_TEXT}
        open={pending !== null}
        onOpenChange={(next) => {
          if (!next) setPending(null)
        }}
        onConfirm={async () => {
          if (pending === null) return
          await raise.mutateAsync(pending)
          notifySuccess(CAPACITY_RAISED_TEXT)
          setValue("")
          onRaised()
        }}
      />
    </fieldset>
  )
}
