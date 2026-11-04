import type { ManagedMatch } from "@/client"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { matchLabel } from "./match-status"
import { useSetReferee } from "./organizer-matches-queries"

export const NO_REFEREE_TEXT = "不指派（主辦方登錄比分）"
export const ORGANIZER_SCORES_TEXT = "主辦方登錄比分"
export const NO_REFEREES_TEXT = "還沒有裁判接受邀請。"
const UNKNOWN_REFEREE_TEXT = "未知的裁判"
const NONE = "__none__"

/**
 * 裁判欄：不能指派時唯讀顯示目前裁判；可以時用 Select，選定即送出（指派、收回都能再改）。
 * 目前的裁判即使不在可指派名單內也列為已選。
 */
export function RefereeSelect({
  tournamentId,
  match,
  names,
  hasReferees,
}: {
  tournamentId: string
  match: ManagedMatch
  /** `account_id` → 裁判顯示名稱；裁判清單載入失敗時為 null（只顯示「—」，錯誤由頁面說明） */
  names: ReadonlyMap<string, string> | null
  /** 賽事是否已有裁判接受邀請 */
  hasReferees: boolean
}) {
  const setReferee = useSetReferee(tournamentId, match.id)
  const current = match.referee_account_id
  if (names === null) return <span aria-hidden="true">—</span>
  const nameOf = (id: string) => names.get(id) ?? UNKNOWN_REFEREE_TEXT

  if (!match.can_assign_referee) {
    return <span>{current ? nameOf(current) : ORGANIZER_SCORES_TEXT}</span>
  }

  const ids = [...match.assignable_referee_ids]
  if (current && !ids.includes(current)) ids.push(current)

  return (
    <div className="flex flex-col items-start gap-1">
      <Select
        value={current ?? NONE}
        onValueChange={(next) => setReferee.mutate(next === NONE ? null : next)}
        disabled={setReferee.isPending}
      >
        <SelectTrigger
          size="sm"
          className="min-w-40"
          aria-label={`${matchLabel(match)}的裁判`}
        >
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={NONE}>{NO_REFEREE_TEXT}</SelectItem>
          {ids.map((id) => (
            <SelectItem key={id} value={id}>
              {nameOf(id)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {!hasReferees && (
        <p className="text-caption text-muted-foreground">{NO_REFEREES_TEXT}</p>
      )}
    </div>
  )
}
