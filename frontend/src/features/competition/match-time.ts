// 場次頁的時間格式（EXPERIENCE.md〈倒數與時間〉）：一律以 Asia/Taipei 顯示、不標時區。
// 用 Intl 換算時區，不手算 +8 偏移；星期用自己的對照表，不依賴執行環境的中文語系資料。

const TIME_ZONE = "Asia/Taipei"
const WEEKDAYS: Record<string, string> = {
  Sun: "日",
  Mon: "一",
  Tue: "二",
  Wed: "三",
  Thu: "四",
  Fri: "五",
  Sat: "六",
}

const formatter = new Intl.DateTimeFormat("en-US", {
  timeZone: TIME_ZONE,
  year: "numeric",
  month: "numeric",
  day: "numeric",
  weekday: "short",
  hour: "2-digit",
  minute: "2-digit",
  // h23：午夜是 00，不會出現 24
  hourCycle: "h23",
})

function isValid(date: Date) {
  return !Number.isNaN(date.getTime())
}

function taipeiParts(date: Date) {
  const parts: Record<string, string> = {}
  for (const part of formatter.formatToParts(date))
    parts[part.type] = part.value
  return {
    year: parts.year,
    month: parts.month,
    day: parts.day,
    weekday: WEEKDAYS[parts.weekday],
    clock: `${parts.hour}:${parts.minute}`,
  }
}

/** 絕對時間「10/17（六）11:52」；與 now 不同年（以台北時間算）時前面加年份「2027/1/2（六）09:05」。 */
export function formatMatchDateTime(
  iso: string,
  now: Date = new Date(),
): string {
  const parsed = new Date(iso)
  // 空字串或格式錯誤時不讓整個畫面壞掉
  if (!isValid(parsed)) return ""
  const t = taipeiParts(parsed)
  const date = `${t.month}/${t.day}（${t.weekday}）${t.clock}`
  return t.year === taipeiParts(now).year ? date : `${t.year}/${date}`
}

/** 台北時間的「HH:mm」，用於「已報到 19:32」。 */
export function formatClock(iso: string): string {
  const parsed = new Date(iso)
  return isValid(parsed) ? taipeiParts(parsed).clock : ""
}
