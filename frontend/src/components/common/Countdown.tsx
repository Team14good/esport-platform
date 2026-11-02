import { Loader2 } from "lucide-react"
import { useEffect, useRef, useState } from "react"

import { formatMatchDateTime } from "@/features/competition/match-time"
import { cn } from "@/lib/utils"

// 倒數（DESIGN.md〈Components〉Countdown、EXPERIENCE.md〈倒數與時間〉）。
// 以使用者裝置時間計算；歸零後只改顯示並通知呼叫端重抓，狀態以伺服器為準。

export type CountdownVariant = "muted" | "live" | "appeal" | "destructive"

/** 歸零後多久呼叫一次 onExpire（毫秒） */
export const EXPIRE_POLL_INTERVAL_MS = 5_000
/** 歸零後最多重抓多久（毫秒）；之後改顯示逾時提示 */
export const EXPIRE_POLL_TIMEOUT_MS = 120_000
/** appeal 進度條沒有指定起點時，以截止前 24 小時為起點 */
const DEFAULT_BAR_WINDOW_MS = 24 * 60 * 60 * 1000

export const EXPIRED_TEXT = "已截止 · 系統處理中"
export const EXPIRE_TIMEOUT_TEXT =
  "處理時間比預期長。重新整理頁面查看最新狀態。"

const VARIANT_CLASS: Record<CountdownVariant, string> = {
  muted: "text-muted-foreground",
  live: "text-status-live",
  appeal: "text-status-appeal",
  destructive: "text-destructive",
}

const SECOND = 1000
const MINUTE = 60
const HOUR = 60 * MINUTE
const DAY = 24 * HOUR

/**
 * 剩餘時間的文字：24 小時以上「剩 2 天 5 小時」、1～24 小時「剩 5 小時 12 分」、
 * 未滿 1 小時「mm:ss」。秒數無條件進位，歸零那一刻才顯示 00:00。
 */
export function formatRemaining(remainingMs: number): string {
  const total = Math.max(0, Math.ceil(remainingMs / SECOND))
  if (total >= DAY) {
    return `剩 ${Math.floor(total / DAY)} 天 ${Math.floor((total % DAY) / HOUR)} 小時`
  }
  if (total >= HOUR) {
    return `剩 ${Math.floor(total / HOUR)} 小時 ${Math.floor((total % HOUR) / MINUTE)} 分`
  }
  const minutes = String(Math.floor(total / MINUTE)).padStart(2, "0")
  const seconds = String(total % MINUTE).padStart(2, "0")
  return `${minutes}:${seconds}`
}

type CountdownProps = {
  /** 左側說明文字，例如「報名截止」 */
  label: string
  /** 目標時間（ISO） */
  deadline: string
  /** 數字顏色；傳函式時依剩餘毫秒數決定（例如最後 24 小時改用 appeal） */
  variant?: CountdownVariant | ((remainingMs: number) => CountdownVariant)
  /** appeal 進度條的起點（ISO），進度條隨時間由滿到空；省略時以截止前 24 小時為起點 */
  startsAt?: string
  /** 下方絕對時間後面的文字，預設「截止」；例如報名開始倒數傳「開放報名」 */
  suffix?: string
  /** 歸零後顯示的文字，預設「已截止 · 系統處理中」；例如報名開始倒數傳「報名開放中 · 系統處理中」 */
  expiredText?: string
  /** 歸零後立即呼叫、之後每 5 秒呼叫一次，最多 2 分鐘：呼叫端在這裡重抓資料 */
  onExpire?: () => void
  className?: string
}

/** 每秒更新的目前時間（毫秒）；stopped 時停止更新。 */
function useNow(stopped: boolean): number {
  const [now, setNow] = useState(() => Date.now())
  const [wasStopped, setWasStopped] = useState(stopped)
  let current = now
  if (wasStopped !== stopped) {
    // 停止後重新開始（換了目標時間）時，這次 render 就改用目前時間，不沿用停止當下的時間
    setWasStopped(stopped)
    if (!stopped) {
      current = Date.now()
      setNow(current)
    }
  }
  useEffect(() => {
    if (stopped) return
    const timer = setInterval(() => setNow(Date.now()), SECOND)
    return () => clearInterval(timer)
  }, [stopped])
  return current
}

/**
 * 歸零後的重抓：立即呼叫一次，之後每 5 秒一次；2 分鐘後停止並回傳 true（逾時）。
 * `resetKey`（目標時間）改變時重設逾時狀態並重新計時。
 */
function useExpirePolling(
  expired: boolean,
  resetKey: string,
  onExpire?: () => void,
): boolean {
  const [timedOut, setTimedOut] = useState(false)
  const [timedOutKey, setTimedOutKey] = useState(resetKey)
  if (timedOutKey !== resetKey) {
    // render 期間依 props 重設狀態（React 建議的寫法）
    setTimedOutKey(resetKey)
    setTimedOut(false)
  }
  // 呼叫端每次 render 傳入新函式時不重設計時器
  const onExpireRef = useRef(onExpire)
  onExpireRef.current = onExpire

  // biome-ignore lint/correctness/useExhaustiveDependencies: 目標時間改變時重新開始重抓與 2 分鐘計時
  useEffect(() => {
    if (!expired) return
    onExpireRef.current?.()
    const poll = setInterval(
      () => onExpireRef.current?.(),
      EXPIRE_POLL_INTERVAL_MS,
    )
    const timeout = setTimeout(() => {
      clearInterval(poll)
      setTimedOut(true)
    }, EXPIRE_POLL_TIMEOUT_MS)
    return () => {
      clearInterval(poll)
      clearTimeout(timeout)
    }
  }, [expired, resetKey])

  return timedOut
}

/**
 * 全站共用的倒數：說明文字＋等寬數字，下方一行「{絕對時間} {suffix}」（預設「截止」）。
 * `deadline` 改變時重設「已截止」與逾時狀態。
 */
export function Countdown({
  label,
  deadline,
  variant = "muted",
  startsAt,
  suffix = "截止",
  expiredText = EXPIRED_TEXT,
  onExpire,
  className,
}: CountdownProps) {
  const deadlineMs = new Date(deadline).getTime()
  const valid = !Number.isNaN(deadlineMs)
  const [expiredOnce, setExpiredOnce] = useState(false)
  const [expiredFor, setExpiredFor] = useState(deadline)
  // 換了目標時間：回到倒數，重新判斷是否已截止（這次 render 就不再當成已截止）
  const deadlineChanged = expiredFor !== deadline
  if (deadlineChanged) {
    setExpiredFor(deadline)
    setExpiredOnce(false)
  }
  const stillExpired = expiredOnce && !deadlineChanged
  const now = useNow(stillExpired || !valid)
  const remainingMs = deadlineMs - now
  // 歸零後不再回到倒數（裝置時間被往回調也一樣），直到目標時間改變
  const expired = stillExpired || (valid && remainingMs <= 0)

  useEffect(() => {
    if (expired && !expiredOnce) setExpiredOnce(true)
  }, [expired, expiredOnce])

  const timedOut = useExpirePolling(expired, deadline, onExpire)

  // 格式錯誤的時間不讓整個畫面壞掉
  if (!valid) return null

  const resolvedVariant =
    typeof variant === "function" ? variant(remainingMs) : variant
  const showBar = resolvedVariant === "appeal" && !expired
  const barStartMs = startsAt
    ? new Date(startsAt).getTime()
    : deadlineMs - DEFAULT_BAR_WINDOW_MS
  const windowMs = deadlineMs - barStartMs
  const fraction =
    Number.isFinite(windowMs) && windowMs > 0
      ? Math.min(1, Math.max(0, remainingMs / windowMs))
      : 0

  return (
    <div
      data-slot="countdown"
      data-variant={resolvedVariant}
      className={cn("flex min-w-0 flex-col gap-1", className)}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <span className="text-label text-muted-foreground">{label}</span>
        {/* 一直掛著的 live region，只換內容，螢幕閱讀器才會唸出歸零與逾時 */}
        <span
          role="status"
          className={
            expired
              ? "inline-flex items-center gap-1.5 text-body text-muted-foreground"
              : "sr-only"
          }
        >
          {!expired ? null : timedOut ? (
            EXPIRE_TIMEOUT_TEXT
          ) : (
            <>
              {expiredText}
              <Loader2 aria-hidden className="size-3.5 animate-spin" />
            </>
          )}
        </span>
        {expired ? null : (
          <span
            role="timer"
            className={cn(
              "font-mono text-countdown tabular-nums",
              VARIANT_CLASS[resolvedVariant],
            )}
          >
            {formatRemaining(remainingMs)}
          </span>
        )}
      </div>
      {showBar ? (
        <div
          data-testid="countdown-bar"
          aria-hidden
          className="h-1 w-full overflow-hidden rounded-full bg-status-appeal/16"
        >
          <div
            className="h-full rounded-full bg-status-appeal"
            style={{ width: `${fraction * 100}%` }}
          />
        </div>
      ) : null}
      <span className="text-caption text-muted-foreground">
        {formatMatchDateTime(deadline)} {suffix}
      </span>
    </div>
  )
}
