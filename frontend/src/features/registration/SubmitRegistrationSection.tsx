import {
  type ReactNode,
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
} from "react"

import type { SubmitBlocker, TeamDetail } from "@/client"
import { ConfirmDialog } from "@/components/common/ConfirmDialog"
import { Countdown, type CountdownVariant } from "@/components/common/Countdown"
import { Button } from "@/components/ui/button"
import { formatMatchDateTime } from "@/features/competition/match-time"
import { REGISTRATION_STATUS_LABELS } from "./registration-status"
import { useSubmitRegistration } from "./useSubmitRegistration"

export const SUBMIT_TEXT = "送出報名"
export const SUBMIT_CONFIRM_DESCRIPTION =
  "送出後名單會鎖定，只有被主辦方退回才能修改。"
export const CAPTAIN_SUBMITS_TEXT = "由隊長送出報名"
export const DEADLINE_LABEL = "報名截止"
export const DEADLINE_PASSED_TEXT = "已截止"
export const PRIORITY_COUNTDOWN_LABEL = "優先期結束後分配名額"
export const ALLOCATION_HEADING = "名額分配"
/** 只供畫面停用「送出報名」：倒數歸零到重新取得隊伍之間，先在本地補上這一項 */
const DEADLINE_PASSED_BLOCKER: SubmitBlocker = {
  code: "REGISTRATION_CLOSED",
  message: DEADLINE_PASSED_TEXT,
}

const DAY_MS = 24 * 60 * 60 * 1000
// setTimeout 的上限（約 24.8 天）；更久的截止時間分段等待
const MAX_TIMEOUT_MS = 2_147_483_647

/** 剩餘超過 24 小時用 muted，最後 24 小時用 appeal。 */
export function deadlineVariant(remainingMs: number): CountdownVariant {
  return remainingMs > DAY_MS ? "muted" : "appeal"
}

/**
 * 目標時間是否已到（裝置時間）；到期後不再輪詢。格式錯誤的時間視為未到期。
 *
 * 除了排一個到期的 setTimeout，裝置休眠或計時器被延後時還有兩個補救：分頁重新顯示時
 * 再檢查一次，以及呼叫端把 `recheck` 交給 `Countdown` 的 `onExpire`（倒數歸零時立即再檢查）。
 */
export function useDeadlinePassed(deadline: string): {
  passed: boolean
  recheck: () => void
} {
  const deadlineMs = new Date(deadline).getTime()
  const [now, setNow] = useState(() => Date.now())
  const valid = !Number.isNaN(deadlineMs)
  const passed = valid && now >= deadlineMs

  useEffect(() => {
    if (!valid || passed) return
    const wait = Math.min(Math.max(0, deadlineMs - now), MAX_TIMEOUT_MS)
    // 每次觸發都更新 now；還沒到期（分段等待）時 effect 會再排下一段
    const timer = setTimeout(() => setNow(Date.now()), wait)
    return () => clearTimeout(timer)
  }, [valid, passed, deadlineMs, now])

  const recheck = useCallback(() => setNow(Date.now()), [])

  useEffect(() => {
    if (!valid || passed) return
    const onVisibilityChange = () => {
      if (document.visibilityState === "visible") recheck()
    }
    document.addEventListener("visibilitychange", onVisibilityChange)
    return () =>
      document.removeEventListener("visibilitychange", onVisibilityChange)
  }, [valid, passed, recheck])

  return { passed, recheck }
}

/** 由未到期變成到期的那一刻呼叫 `onPassed`；一開啟頁面就已到期時不呼叫。 */
function useOnBecamePassed(passed: boolean, onPassed: () => void) {
  const previous = useRef(passed)
  const onPassedRef = useRef(onPassed)
  onPassedRef.current = onPassed
  useEffect(() => {
    if (passed && !previous.current) onPassedRef.current()
    previous.current = passed
  }, [passed])
}

/** 已到期的倒數：維持 Countdown 的版面，不輪詢、不顯示逾時。 */
function PassedDeadline({
  label,
  text,
  deadline,
}: {
  label: string
  text: string
  deadline: string
}) {
  return (
    <div data-slot="countdown" className="flex min-w-0 flex-col gap-1">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <span className="text-label text-muted-foreground">{label}</span>
        <span role="status" className="text-body text-muted-foreground">
          {text}
        </span>
      </div>
      <span className="text-caption text-muted-foreground">
        {formatMatchDateTime(deadline)} 截止
      </span>
    </div>
  )
}

function RegistrationSection({
  heading,
  children,
}: {
  heading: string
  children: ReactNode
}) {
  const headingId = useId()
  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-4">
      <h2 id={headingId} className="text-heading-md">
        {heading}
      </h2>
      {children}
    </section>
  )
}

type SubmitRegistrationSectionProps = {
  team: TeamDetail
  /** 報名截止倒數歸零時呼叫一次：呼叫端重新取得隊伍（後端會回 `REGISTRATION_CLOSED`） */
  onDeadlinePassed: () => void
}

/** 組隊中：報名截止倒數、「送出報名」（隊長）或「由隊長送出報名」（隊員），與逐項的停用原因。 */
function FormingSubmit({
  team,
  onDeadlinePassed,
}: SubmitRegistrationSectionProps) {
  const reasonsId = useId()
  const submit = useSubmitRegistration(team.id)
  const { passed: deadlinePassed, recheck } = useDeadlinePassed(
    team.registration_end,
  )
  useOnBecamePassed(deadlinePassed, onDeadlinePassed)

  const blockers =
    deadlinePassed &&
    !team.submit_blockers.some((b) => b.code === "REGISTRATION_CLOSED")
      ? [DEADLINE_PASSED_BLOCKER, ...team.submit_blockers]
      : team.submit_blockers
  const isCaptain = team.my_role === "captain"

  return (
    <RegistrationSection heading={SUBMIT_TEXT}>
      {deadlinePassed ? (
        <PassedDeadline
          label={DEADLINE_LABEL}
          text={DEADLINE_PASSED_TEXT}
          deadline={team.registration_end}
        />
      ) : (
        <Countdown
          label={DEADLINE_LABEL}
          deadline={team.registration_end}
          variant={deadlineVariant}
          expiredText={DEADLINE_PASSED_TEXT}
          // 倒數歸零時立即改成靜態的「已截止」：不等可能被延後的計時器，也不讓 Countdown 輪詢
          onExpire={recheck}
        />
      )}
      {isCaptain ? (
        <ConfirmDialog
          title={SUBMIT_TEXT}
          description={SUBMIT_CONFIRM_DESCRIPTION}
          confirmLabel={SUBMIT_TEXT}
          onConfirm={() => submit.mutateAsync()}
          trigger={
            <Button
              disabled={blockers.length > 0}
              aria-describedby={blockers.length > 0 ? reasonsId : undefined}
              className="h-10 w-full sm:w-auto sm:self-start"
            >
              {SUBMIT_TEXT}
            </Button>
          }
        />
      ) : (
        <p className="text-body">{CAPTAIN_SUBMITS_TEXT}</p>
      )}
      {blockers.length > 0 && (
        <ul
          id={reasonsId}
          aria-label="尚未符合送出條件"
          className="flex list-disc flex-col gap-1 pl-5 text-body text-muted-foreground"
        >
          {blockers.map((blocker) => (
            <li key={blocker.code} className="break-words">
              {blocker.message}
            </li>
          ))}
        </ul>
      )}
    </RegistrationSection>
  )
}

/**
 * 已送出・待分配：優先期內顯示「優先期結束後分配名額」倒數；倒數歸零後改顯示
 * 「已送出・待分配」（分配在 3.4 第二階段），不輪詢。開啟頁面時優先期已過則不顯示。
 */
function PriorityCountdown({ priorityEnd }: { priorityEnd: string }) {
  const { passed, recheck } = useDeadlinePassed(priorityEnd)
  const [passedOnMount] = useState(passed)

  if (passed && passedOnMount) return null
  return (
    <RegistrationSection heading={ALLOCATION_HEADING}>
      {passed ? (
        <p role="status" className="text-body text-muted-foreground">
          {REGISTRATION_STATUS_LABELS.pending}
        </p>
      ) : (
        <Countdown
          label={PRIORITY_COUNTDOWN_LABEL}
          deadline={priorityEnd}
          variant="muted"
          expiredText={REGISTRATION_STATUS_LABELS.pending}
          onExpire={recheck}
        />
      )}
    </RegistrationSection>
  )
}

/** S17 的報名區塊：組隊中可送出報名，已送出後顯示分配前的倒數。 */
export function SubmitRegistrationSection({
  team,
  onDeadlinePassed,
}: SubmitRegistrationSectionProps) {
  if (team.registration_status === "forming") {
    return <FormingSubmit team={team} onDeadlinePassed={onDeadlinePassed} />
  }
  if (team.registration_status === "pending") {
    return <PriorityCountdown priorityEnd={team.priority_end} />
  }
  return null
}
