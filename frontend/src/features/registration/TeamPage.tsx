import { useQuery, useQueryClient } from "@tanstack/react-query"
import { type ReactNode, useState } from "react"

import type { TeamDetail, TeamInvitePreview } from "@/client"
import { RouteErrorPage } from "@/components/layout/ErrorPage"
import { Skeleton } from "@/components/ui/skeleton"
import { useCurrentAccount } from "@/features/identity/auth"
import { notifySuccess } from "@/lib/feedback"
import { InviteLinkField } from "./InviteLinkField"
import {
  PlayerProfileDialog,
  type PlayerProfileValues,
} from "./PlayerProfileDialog"
import { teamInviteUrl, teamQueryOptions } from "./queries"
import { RosterList } from "./RosterList"
import { RegistrationStatusBadge, WaitlistDetails } from "./registration-status"
import { SubmitRegistrationSection } from "./SubmitRegistrationSection"
import { useUpdatePlayerProfile } from "./useUpdatePlayerProfile"

export const TEAM_FULL_REASON = "隊伍已滿"
export const ROSTER_LOCKED_REASON = "名單已鎖定"
export const REGISTRATION_CLOSED_REASON = "報名已截止"

/** 邀請連結失效的原因；有效時為 null（優先順序由後端決定：已鎖定 > 已截止 > 已滿）。 */
export function inviteInvalidReason(
  status: TeamInvitePreview["invite_status"],
): string | null {
  switch (status) {
    case "locked":
      return ROSTER_LOCKED_REASON
    case "closed":
      return REGISTRATION_CLOSED_REASON
    case "full":
      return TEAM_FULL_REASON
    default:
      return null
  }
}
export const PROFILE_SAVED_TEXT = "已儲存參賽資料"

/**
 * S17 隊伍頁：隊名與報名狀態、邀請連結（Invite link field）、名單（Roster list）；
 * 自己那列的「填寫我的資料」開 S18；名單下方是送出報名（3.3）。
 */
export function TeamPage({
  teamId,
  renderStatusExtra,
}: {
  teamId: string
  /**
   * 報名狀態下方的額外內容（可選）；例如 disputes 的取消資格理由（6.5）。
   * registration 的頁面不依賴 disputes，由路由傳入。
   */
  renderStatusExtra?: (team: TeamDetail) => ReactNode
}) {
  const team = useQuery(teamQueryOptions(teamId))
  const queryClient = useQueryClient()
  const account = useCurrentAccount()
  const [profileOpen, setProfileOpen] = useState(false)
  const { save, uploadProgress } = useUpdatePlayerProfile(teamId)

  if (team.isPending) {
    return (
      <section
        role="status"
        aria-busy="true"
        className="mx-auto flex w-full max-w-2xl flex-col gap-6 py-8 sm:py-12"
      >
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-32 w-full" />
        <span className="sr-only">載入中</span>
      </section>
    )
  }
  if (team.isError) return <RouteErrorPage error={team.error} />

  const data = team.data
  const myAccountId = account.data?.id ?? null
  const me = data.members.find((member) => member.account_id === myAccountId)
  const inviteReason = inviteInvalidReason(data.invite_status)

  async function saveProfile(values: PlayerProfileValues) {
    await save(values)
    setProfileOpen(false)
    notifySuccess(PROFILE_SAVED_TEXT)
  }

  return (
    <section className="mx-auto flex w-full max-w-2xl flex-col gap-8 py-8 sm:py-12">
      <header className="flex flex-col gap-2">
        <p className="text-caption text-muted-foreground">
          {data.tournament_name} · {data.game_name}
        </p>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="break-words text-heading-lg">{data.name}</h1>
          <RegistrationStatusBadge
            status={data.registration_status}
            waitlist={data}
          />
        </div>
        <WaitlistDetails status={data.registration_status} waitlist={data} />
        {renderStatusExtra?.(data)}
      </header>
      <section
        aria-labelledby="team-invite-heading"
        className="flex flex-col gap-3"
      >
        <h2 id="team-invite-heading" className="text-heading-md">
          邀請隊友
        </h2>
        <InviteLinkField
          label="隊伍邀請連結"
          url={teamInviteUrl(data.invite_token)}
          invalid={inviteReason === null ? null : { reason: inviteReason }}
          note={
            data.invite_status === "active"
              ? "隊友開啟連結、登入並完成 Email 驗證後即可加入。"
              : undefined
          }
        />
      </section>
      <section
        aria-labelledby="team-roster-heading"
        className="flex flex-col gap-3"
      >
        <h2 id="team-roster-heading" className="text-heading-md">
          隊伍名單
        </h2>
        <RosterList
          members={data.members}
          starters={data.starters}
          maxMembers={data.max_members}
          avgRankScore={data.avg_rank_score}
          rankFilledCount={data.rank_filled_count}
          currentAccountId={myAccountId}
          onEditMyProfile={() => setProfileOpen(true)}
        />
      </section>
      <SubmitRegistrationSection
        team={data}
        onDeadlinePassed={() =>
          queryClient.invalidateQueries({
            queryKey: teamQueryOptions(teamId).queryKey,
          })
        }
      />
      {/* 開啟時才掛載：S17 平時不需要 S18 的 Sheet／Dialog 與表單狀態 */}
      {me && profileOpen && (
        <PlayerProfileDialog
          open
          onOpenChange={setProfileOpen}
          rankTiers={data.rank_tiers}
          initialValues={{
            game_account_id: me.game_account_id ?? undefined,
            rank_tier: me.rank_tier ?? undefined,
          }}
          uploadedScreenshotName={me.rank_screenshot_name}
          readOnly={!data.profile_editable}
          uploadProgress={uploadProgress}
          onSubmit={saveProfile}
        />
      )}
    </section>
  )
}
