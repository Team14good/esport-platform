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
