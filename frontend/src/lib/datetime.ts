// 時間一律以台北時間顯示（後端存 UTC 的 timestamptz）
const TAIPEI_FORMAT = new Intl.DateTimeFormat("zh-TW", {
  timeZone: "Asia/Taipei",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
})

/** 以台北時間顯示日期時間，例如 `2026/10/29 14:05`。 */
export function formatDateTime(value: string | Date): string {
  const parts = TAIPEI_FORMAT.formatToParts(new Date(value))
  const part = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((item) => item.type === type)?.value ?? ""
  return `${part("year")}/${part("month")}/${part("day")} ${part("hour")}:${part("minute")}`
}

const LOCAL_DATETIME_PATTERN =
  /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?$/

const TAIPEI_OFFSET_FORMAT = new Intl.DateTimeFormat("en-US", {
  timeZone: "Asia/Taipei",
  year: "numeric",
  month: "numeric",
  day: "numeric",
  hour: "numeric",
  minute: "numeric",
  second: "numeric",
  hourCycle: "h23",
})

/** 某個時刻在台北的 UTC 偏移（毫秒）；以 Intl 換算，不寫死 +8。 */
function taipeiOffsetMs(utcMs: number): number {
  const parts: Record<string, number> = {}
  for (const part of TAIPEI_OFFSET_FORMAT.formatToParts(new Date(utcMs))) {
    if (part.type !== "literal") parts[part.type] = Number(part.value)
  }
  const asUtc = Date.UTC(
    parts.year,
    parts.month - 1,
    parts.day,
    parts.hour,
    parts.minute,
    parts.second,
  )
  return asUtc - Math.floor(utcMs / 1000) * 1000
}

/**
 * `datetime-local` 的值（台北時間，例如 `2026-11-10T19:00`）轉成 UTC 的 ISO 字串
 * （`2026-11-10T11:00:00.000Z`）；格式不合或日期不存在時回傳 null。
 */
export function taipeiLocalToIso(value: string): string | null {
  const match = LOCAL_DATETIME_PATTERN.exec(value)
  if (!match) return null
  const [year, month, day, hour, minute, second = "0"] = match.slice(1)
  const wallMs = Date.UTC(
    Number(year),
    Number(month) - 1,
    Number(day),
    Number(hour),
    Number(minute),
    Number(second),
  )
  const wall = new Date(wallMs)
  // Date.UTC 會把 2 月 30 日進位成 3 月 2 日：進位過就是不存在的日期
  if (
    wall.getUTCFullYear() !== Number(year) ||
    wall.getUTCMonth() !== Number(month) - 1 ||
    wall.getUTCDate() !== Number(day) ||
    wall.getUTCHours() !== Number(hour) ||
    wall.getUTCMinutes() !== Number(minute)
  ) {
    return null
  }
  const utcMs = wallMs - taipeiOffsetMs(wallMs - taipeiOffsetMs(wallMs))
  return new Date(utcMs).toISOString()
}

/**
 * UTC 的 ISO 字串轉成 `datetime-local` 的值（台北時間，例如 `2026-11-10T19:00`），
 * `taipeiLocalToIso` 的反向；秒以下捨去，無法解析時回傳空字串。
 */
export function isoToTaipeiLocal(value: string): string {
  const ms = new Date(value).getTime()
  if (Number.isNaN(ms)) return ""
  const shifted = new Date(ms + taipeiOffsetMs(ms))
  return shifted.toISOString().slice(0, 16)
}

const WEEKDAYS = ["日", "一", "二", "三", "四", "五", "六"]

/** 以台北時間顯示月日、星期與時分，例如 `10/18（六）19:00`；無法解析時回傳空字串。 */
export function formatShortDateTime(value: string | Date): string {
  const ms = new Date(value).getTime()
  if (Number.isNaN(ms)) return ""
  const local = new Date(ms + taipeiOffsetMs(ms))
  const pad = (n: number) => String(n).padStart(2, "0")
  return `${pad(local.getUTCMonth() + 1)}/${pad(local.getUTCDate())}（${WEEKDAYS[local.getUTCDay()]}）${pad(local.getUTCHours())}:${pad(local.getUTCMinutes())}`
}

const MINUTE_MS = 60_000
const HOUR_MS = 60 * MINUTE_MS
const DAY_MS = 24 * HOUR_MS

/**
 * 相對於 `now` 的時間，例如「剛剛」「3 分鐘前」「2 小時前」「5 天前」；
 * 未來的時間（時鐘誤差）也顯示「剛剛」，無法解析時回傳空字串。
 */
export function formatRelativeTime(
  value: string | Date,
  now: Date = new Date(),
): string {
  const ms = new Date(value).getTime()
  if (Number.isNaN(ms)) return ""
  const diff = now.getTime() - ms
  if (diff < MINUTE_MS) return "剛剛"
  if (diff < HOUR_MS) return `${Math.floor(diff / MINUTE_MS)} 分鐘前`
  if (diff < DAY_MS) return `${Math.floor(diff / HOUR_MS)} 小時前`
  return `${Math.floor(diff / DAY_MS)} 天前`
}
