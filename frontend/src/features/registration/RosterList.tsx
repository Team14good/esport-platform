import type { TeamMemberRead } from "@/client"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { cn } from "@/lib/utils"

export const EDIT_MY_PROFILE_TEXT = "填寫我的資料"
export const PROFILE_COMPLETE_TEXT = "資料完成"

type MissingField = TeamMemberRead["missing_fields"][number]

/** 後端的缺漏欄位代碼轉成介面文字（後端已依固定順序排列）。 */
const MISSING_FIELD_LABELS: Record<MissingField, string> = {
  game_account_id: "遊戲 ID",
  rank_tier: "段位",
  rank_screenshot: "段位截圖",
}

type RosterListProps = {
  members: TeamMemberRead[]
  /** 先發人數 */
  starters: number
  /** 人數上限（先發＋替補） */
  maxMembers: number
  /** 已填段位成員的平均段位積分（後端已取到小數第二位）；沒有人填時為 null */
  avgRankScore: number | null
  /** 已填段位的人數 */
  rankFilledCount: number
  /** 目前登入的帳號；自己那列才有「填寫我的資料」 */
  currentAccountId?: string | null
  onEditMyProfile?: () => void
}

/** 名單下方的人數：「4／6 人（先發 5）」。 */
export function rosterCountText(
  count: number,
  maxMembers: number,
  starters: number,
): string {
  return `${count}／${maxMembers} 人（先發 ${starters}）`
}

/**
 * 名單下方的平均段位積分（含替補，一律兩位小數）：只算已填段位的成員並註明人數，
 * 全員都填了不註明，沒有人填時寫「尚無人填寫」。
 */
export function avgRankScoreText(
  avgRankScore: number | null,
  filledCount: number,
  memberCount: number,
): string {
  if (avgRankScore === null || filledCount === 0) {
    return "平均段位積分：尚無人填寫"
  }
  const value = avgRankScore.toFixed(2)
  if (filledCount >= memberCount) return `平均段位積分 ${value}`
  return `平均段位積分 ${value}（${filledCount}／${memberCount} 人已填）`
}

/** 每列的 caption：「遊戲 ID · 段位 · 段位截圖：已上傳」，只列有填的部分。 */
export function profileCaption(member: TeamMemberRead): string {
  return [
    member.game_account_id,
    member.rank_tier,
    member.has_rank_screenshot ? "段位截圖：已上傳" : null,
  ]
    .filter(Boolean)
    .join(" · ")
}

/** 完成度：「資料完成」或「缺：遊戲 ID、段位、段位截圖」。 */
export function profileStatusText(member: TeamMemberRead): string {
  if (member.missing_fields.length === 0) return PROFILE_COMPLETE_TEXT
  return `缺：${member.missing_fields
    .map((field) => MISSING_FIELD_LABELS[field])
    .join("、")}`
}

/**
 * Roster list（UX-DR34，S17）：名單放在 Card 內、列間 1px 分隔。每人一列顯示名稱
 * （隊長加 outline Badge「隊長」）、已填的參賽資料與完成度；自己那列有「填寫我的資料」。
 * 下方顯示人數與平均段位積分。
 */
export function RosterList({
  members,
  starters,
  maxMembers,
  avgRankScore,
  rankFilledCount,
  currentAccountId = null,
  onEditMyProfile,
}: RosterListProps) {
  return (
    <div className="flex flex-col gap-2">
      <Card className="gap-0 py-0">
        <ul aria-label="隊伍名單" className="divide-y">
          {members.map((member) => {
            const caption = profileCaption(member)
            const complete = member.missing_fields.length === 0
            const isMe = member.account_id === currentAccountId
            return (
              <li
                key={member.account_id}
                className="flex min-h-12 flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3"
              >
                <div className="flex min-w-0 flex-1 basis-40 flex-col gap-1">
                  <div className="flex min-w-0 items-center gap-2">
                    <span className="min-w-0 break-words text-body">
                      {member.display_name}
                    </span>
                    {member.role === "captain" && (
                      <Badge variant="outline">隊長</Badge>
                    )}
                  </div>
                  {caption && (
                    <p className="break-words text-caption text-muted-foreground">
                      {caption}
                    </p>
                  )}
                </div>
                <div className="flex flex-wrap items-center gap-3">
                  <span
                    className={cn(
                      "text-caption",
                      complete
                        ? "text-status-confirmed"
                        : "text-muted-foreground",
                    )}
                  >
                    {profileStatusText(member)}
                  </span>
                  {isMe && onEditMyProfile && (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={onEditMyProfile}
                    >
                      {EDIT_MY_PROFILE_TEXT}
                    </Button>
                  )}
                </div>
              </li>
            )
          })}
        </ul>
      </Card>
      <p className="text-caption text-muted-foreground">
        {rosterCountText(members.length, maxMembers, starters)}
      </p>
      <p className="text-caption text-muted-foreground">
        {avgRankScoreText(avgRankScore, rankFilledCount, members.length)}
      </p>
    </div>
  )
}
