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
