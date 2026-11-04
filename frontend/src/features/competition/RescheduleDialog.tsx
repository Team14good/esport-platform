import { type FormEvent, useEffect, useId, useState } from "react"

import type { ManagedMatch } from "@/client"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { LoadingButton } from "@/components/ui/loading-button"
import { isoToTaipeiLocal, taipeiLocalToIso } from "@/lib/datetime"
import { matchLabel } from "./match-status"
import { formatMatchDateTime } from "./match-time"
import { useRescheduleMatch } from "./organizer-matches-queries"

type Reason = NonNullable<ManagedMatch["reschedule"]["reason"]>

/** 不能修改時間的原因（`already_checked_in` 為 UX 原文，其餘與後端訊息一致）。 */
export const RESCHEDULE_REASON_TEXT: Record<Reason, string> = {
  already_checked_in: "已有隊伍報到，無法修改時間",
  match_not_reschedulable: "只有待開打的場次可以修改時間",
  forfeit_due: "棄權期限已過，等待系統判定",
  no_valid_time: "目前沒有可選的時間",
  tournament_not_reschedulable: "賽事目前的狀態不能修改時間",
}

const FALLBACK_REASON_TEXT = "目前不能修改時間"
export const INVALID_TIME_TEXT = "請選擇有效的時間"

function RescheduleForm({
  tournamentId,
  match,
  onDone,
}: {
  tournamentId: string
  match: ManagedMatch
  onDone: () => void
}) {
  const inputId = useId()
  const { earliest, latest } = match.reschedule
  const original = isoToTaipeiLocal(match.scheduled_at)
  // 原時間早於允許範圍的起點時，預填起點，避免一開始就低於 min
  const [value, setValue] = useState(
    earliest && Date.parse(earliest) > Date.parse(match.scheduled_at)
      ? isoToTaipeiLocal(earliest)
      : original,
  )
  const [invalid, setInvalid] = useState(false)
  const reschedule = useRescheduleMatch(tournamentId, match.id)

  function submit(event: FormEvent) {
    event.preventDefault()
    const iso = taipeiLocalToIso(value)
    if (iso === null) {
      setInvalid(true)
      return
    }
    setInvalid(false)
    reschedule.mutate(iso, { onSuccess: onDone })
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <Label htmlFor={inputId}>新的開打時間（台北時間）</Label>
        <Input
          id={inputId}
          type="datetime-local"
          value={value}
          min={earliest ? isoToTaipeiLocal(earliest) : undefined}
          max={latest ? isoToTaipeiLocal(latest) : undefined}
          onChange={(event) => setValue(event.target.value)}
          aria-invalid={invalid}
        />
        {invalid && (
          <p role="alert" className="text-body text-destructive">
            {INVALID_TIME_TEXT}
          </p>
        )}
      </div>
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onDone}>
          取消
        </Button>
        <LoadingButton
          type="submit"
          loading={reschedule.isPending}
          disabled={value === original}
        >
          儲存時間
        </LoadingButton>
      </DialogFooter>
    </form>
  )
}

/**
 * 「修改時間」按鈕與 Dialog。不能修改時按鈕停用，並在下方寫原因；
 * 失敗時 Dialog 維持開啟（列表重抓後範圍會跟著更新），成功才關閉。
 */
export function RescheduleDialog({
  tournamentId,
  match,
}: {
  tournamentId: string
  match: ManagedMatch
}) {
  const [open, setOpen] = useState(false)
  const { can_reschedule: can, reason, earliest, latest } = match.reschedule

  // 不能修改時一併關閉，之後再變成可以時不會自己重新打開
  useEffect(() => {
    if (!can) setOpen(false)
  }, [can])

  return (
    <div className="flex flex-col items-start gap-1">
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogTrigger asChild>
          <Button variant="outline" size="sm" disabled={!can}>
            修改時間
          </Button>
        </DialogTrigger>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>修改場次時間</DialogTitle>
            <DialogDescription>
              {matchLabel(match)}　
              {earliest
                ? latest
                  ? `可選 ${formatMatchDateTime(earliest)}～${formatMatchDateTime(latest)}`
                  : `${formatMatchDateTime(earliest)} 以後`
                : "只能選擇允許範圍內的時間。"}
            </DialogDescription>
          </DialogHeader>
          <RescheduleForm
            tournamentId={tournamentId}
            match={match}
            onDone={() => setOpen(false)}
          />
        </DialogContent>
      </Dialog>
      {!can && (
        <p className="text-caption text-muted-foreground">
          {reason ? RESCHEDULE_REASON_TEXT[reason] : FALLBACK_REASON_TEXT}
        </p>
      )}
    </div>
  )
}
