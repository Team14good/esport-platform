import { keepPreviousData, queryOptions, useQuery } from "@tanstack/react-query"

import { type AuditLogEntry, TournamentsService } from "@/client"

// S34 操作紀錄（Story 2.8）：查詢、動作對照表、時間格式與變更內容差異。

export const AUDIT_LOG_EMPTY_TEXT = "這場賽事還沒有操作紀錄。"
/** `actor_id` 為 null（worker 自動執行）時的操作者文字。 */
export const SYSTEM_ACTOR_TEXT = "系統自動"
/** 帳號已不存在（查不到顯示名稱）時的操作者文字。 */
export const UNKNOWN_ACTOR_TEXT = "未知帳號"

/**
 * 動作代碼的繁中名稱：涵蓋目前所有帶 `tournament_id` 的動作。
 * 帳號類動作（`account.*`、`school.*`、`game.*`、`organizer_application.*`）不屬於
 * 任何賽事，不會出現在 S34，所以不列入；未知代碼顯示原文。
 * 後端 `tests/tournaments/test_audit_action_labels.py` 掃描所有 `audit.record` 並與這份清單的
 * 副本比對；新增或移除動作時兩邊要一起改。
 */
export const AUDIT_ACTION_LABELS: Record<string, string> = {
  "tournament.created": "建立賽事",
  "tournament.status_changed": "賽事狀態變更",
  "tournament.podium": "產生最終名次",
  "tournament.capacity_changed": "提高名額",
  "referee_invitation.created": "產生裁判邀請",
  "referee.accepted": "裁判接受邀請",
  "team.created": "建立隊伍",
  "team.member_joined": "隊員加入隊伍",
  "team.member_removed": "移除隊員",
  "team.captain_transferred": "轉讓隊長",
  "team.member_left": "隊員退出隊伍",
  "team.disbanded": "解散隊伍",
  "team_member.profile_updated": "修改隊員資料",
  "registration.submitted": "送出報名",
  "registration.status_changed": "報名狀態變更",
  "registration.priority_window_settled": "優先期結算",
  "registration.rejected": "退回報名",
  "bracket.drawn": "抽籤",
  "bracket.auto_draw_skipped": "略過自動抽籤",
  "match.referee_assigned": "指派裁判",
  "match.referee_unassigned": "取消指派裁判",
  "match.checked_in": "報到",
  "match.forfeited": "判定棄權",
  "match.game_recorded": "登錄單局比分",
  "match.game_deleted": "刪除單局比分",
  "match.result_submitted": "送出比賽結果",
  "match.result_screenshot_uploaded": "上傳結算截圖",
  "match.confirmed": "確認比賽結果",
  "match.rescheduled": "調整比賽時間",
  "match.replay_scheduled": "安排重賽",
  "match.teams_changed": "場次隊伍變更",
  "match.voided": "取消場次",
  "report.filed": "提出檢舉",
  "report.resolved": "處理檢舉",
  "appeal.filed": "提出申訴",
  "appeal.resolved": "處理申訴",
}

// 用 Map 查詢：`toString` 這類原型鏈上的名稱不會被當成已知動作
// （不用 Object.hasOwn：target 是 ES2020）
const ACTION_LABELS = new Map(Object.entries(AUDIT_ACTION_LABELS))

/** 動作的顯示文字；不在對照表的代碼顯示原文。 */
export function auditActionLabel(action: string): string {
  return ACTION_LABELS.get(action) ?? action
}

/** 操作者的顯示文字：system 為「系統自動」。 */
export function auditActorLabel(entry: AuditLogEntry): string {
  if (entry.actor_id === null || entry.actor_id === undefined) {
    return SYSTEM_ACTOR_TEXT
  }
  return entry.actor_display_name ?? UNKNOWN_ACTOR_TEXT
}

// 用 Intl 換算台北時間，不手算 +8；用 en-US 的數字欄位，不依賴執行環境的中文語系資料
const SECONDS_FORMAT = new Intl.DateTimeFormat("en-US", {
  timeZone: "Asia/Taipei",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hourCycle: "h23",
})

/** 台北時間到秒，例如 `2026/11/21 14:05:09`；格式錯誤時回空字串。 */
export function formatAuditTime(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ""
  const parts: Record<string, string> = {}
  for (const part of SECONDS_FORMAT.formatToParts(date)) {
    parts[part.type] = part.value
  }
  return `${parts.year}/${parts.month}/${parts.day} ${parts.hour}:${parts.minute}:${parts.second}`
}

/** 變更內容的一個欄位；`before`／`after` 為 undefined 表示那一邊沒有這個欄位。 */
export type AuditChange = {
  field: string
  before?: unknown
  after?: unknown
}

type Snapshot = { [key: string]: unknown } | null | undefined

/**
 * 變更內容差異：新增類（`before` 為 null）列出 `after` 的全部欄位；刪除類（`after`
 * 為 null）列出 `before` 的全部欄位；兩邊都有時只列值不同的欄位（依 `after` 的欄位
 * 順序，再接只在 `before` 的欄位）。
 */
export function auditChanges(before: Snapshot, after: Snapshot): AuditChange[] {
  if (!before && !after) return []
  if (!before) {
    return Object.entries(after ?? {}).map(([field, value]) => ({
      field,
      after: value,
    }))
  }
  if (!after) {
    return Object.entries(before).map(([field, value]) => ({
      field,
      before: value,
    }))
  }
  // Object.keys 只含自己的欄位（不用 Object.hasOwn：target 是 ES2020）
  const beforeKeys = new Set(Object.keys(before))
  const afterKeys = new Set(Object.keys(after))
  const fields = [
    ...afterKeys,
    ...[...beforeKeys].filter((field) => !afterKeys.has(field)),
  ]
  return fields
    .filter(
      (field) =>
        stableStringify(before[field]) !== stableStringify(after[field]),
    )
    .map((field) => {
      const change: AuditChange = { field }
      if (beforeKeys.has(field)) change.before = before[field]
      if (afterKeys.has(field)) change.after = after[field]
      return change
    })
}

/** 物件鍵排序後的 JSON：JSONB 不保證鍵的順序，比較時不能受順序影響。 */
function stableStringify(value: unknown): string {
  return JSON.stringify(value, (_key, inner: unknown) =>
    inner && typeof inner === "object" && !Array.isArray(inner)
      ? Object.fromEntries(
          Object.entries(inner as Record<string, unknown>).sort(([a], [b]) =>
            a < b ? -1 : a > b ? 1 : 0,
          ),
        )
      : inner,
  )
}

/** 變更內容裡的值：字串照原文，其他（數字、布林、null、物件、陣列）以 JSON 呈現。 */
export function formatAuditValue(value: unknown): string {
  if (value === undefined) return "—"
  if (typeof value === "string") return value
  return JSON.stringify(value)
}

export const auditLogQueryOptions = (tournamentId: string, page: number) =>
  queryOptions({
    queryKey: ["tournaments", "organizer", "audit-log", tournamentId, { page }],
    queryFn: async () =>
      (
        await TournamentsService.listTournamentAuditLog({
          path: { tournament_id: tournamentId },
          query: { page },
        })
      ).data,
  })

/** S34 的分頁查詢；換頁時先保留上一頁的資料，不再顯示 Skeleton。 */
export function useAuditLog(tournamentId: string, page: number) {
  return useQuery({
    ...auditLogQueryOptions(tournamentId, page),
    placeholderData: keepPreviousData,
  })
}
