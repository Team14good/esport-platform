import { useQuery, useQueryClient } from "@tanstack/react-query"
import { type ReactNode, useState } from "react"

import type { TeamDetail, TeamInvitePreview, TeamMemberRead } from "@/client"
import { ConfirmDialog } from "@/components/common/ConfirmDialog"
import { RouteErrorPage } from "@/components/layout/ErrorPage"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { useCurrentAccount } from "@/features/identity/auth"
import { notifySuccess } from "@/lib/feedback"
import { InviteLinkField } from "./InviteLinkField"
import {
  PlayerProfileDialog,
  type PlayerProfileValues,
} from "./PlayerProfileDialog"
import { teamInviteUrl, teamQueryOptions } from "./queries"
import {
  LEAVE_TEAM_TEXT,
  REMOVE_MEMBER_TEXT,
  RosterList,
  TRANSFER_CAPTAIN_TEXT,
} from "./RosterList"
import {
  REJECT_REASON_PREFIX,
  RegistrationStatusBadge,
  WaitlistDetails,
} from "./registration-status"
import { SubmitRegistrationSection } from "./SubmitRegistrationSection"
import {
  useDisbandTeam,
  useLeaveTeam,
  useRemoveMember,
  useTransferCaptain,
} from "./useRosterChanges"
import { useUpdatePlayerProfile } from "./useUpdatePlayerProfile"

export const TEAM_FULL_REASON = "隊伍已滿"
export const ROSTER_LOCKED_REASON = "名單已鎖定"
export const REGISTRATION_CLOSED_REASON = "報名已截止"
export const TEAM_DISBANDED_REASON = "隊伍已解散"

export const DISBAND_TEAM_TEXT = "解散隊伍"
export const TEAM_DISBANDED_NOTE = "這支隊伍已由隊長解散。"
export const LEAVE_TEAM_DESCRIPTION =
  "退出後你的參賽資料會一併刪除，之後可以加入這場賽事的其他隊伍。"
export const DISBAND_TEAM_DESCRIPTION =
  "解散後所有隊員都會離開隊伍、報名改為撤回，邀請連結失效，無法復原。"

export function removeMemberDescription(name: string): string {
  return `${name}會離開隊伍，參賽資料一併刪除；之後仍可經邀請連結重新加入。`
}

export function transferCaptainDescription(name: string): string {
  return `轉讓後${name}成為隊長，你會成為一般隊員，不能再送出報名或管理隊員。`
}

/** 邀請連結失效的原因；有效時為 null（優先順序由後端決定：已解散 > 已鎖定 > 已截止 > 已滿）。 */
export function inviteInvalidReason(
  status: TeamInvitePreview["invite_status"],
): string | null {
  switch (status) {
    case "disbanded":
      return TEAM_DISBANDED_REASON
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

/** S17 名單異動的確認對象（Story 3.11）。 */
type RosterAction =
  | { kind: "remove" | "transfer"; member: TeamMemberRead }
  | { kind: "leave" }
  | { kind: "disband" }

/**
 * 隊員異動的確認對話框（UX-DR15：標題寫動作、內文寫後果、確認鈕重複動作名）。
 * 由 TeamPage 控制開關：被拒（409）後名單重新取得、選單消失，對話框仍保留並顯示原因。
 */
function RosterActionDialog({
  teamId,
  action,
  onClose,
}: {
  teamId: string
  action: RosterAction
  onClose: () => void
}) {
  const remove = useRemoveMember(teamId)
  const transfer = useTransferCaptain(teamId)
  const leave = useLeaveTeam(teamId)
  const disband = useDisbandTeam(teamId)

  const props = (() => {
    switch (action.kind) {
      case "remove":
        return {
          title: REMOVE_MEMBER_TEXT,
          description: removeMemberDescription(action.member.display_name),
          destructive: true,
          onConfirm: () => remove.mutateAsync(action.member.account_id),
        }
      case "transfer":
        return {
          title: TRANSFER_CAPTAIN_TEXT,
          description: transferCaptainDescription(action.member.display_name),
          destructive: false,
          onConfirm: () => transfer.mutateAsync(action.member.account_id),
        }
      case "leave":
        return {
          title: LEAVE_TEAM_TEXT,
          description: LEAVE_TEAM_DESCRIPTION,
          destructive: true,
          onConfirm: () => leave.mutateAsync(),
        }
      case "disband":
        return {
          title: DISBAND_TEAM_TEXT,
          description: DISBAND_TEAM_DESCRIPTION,
          destructive: true,
          onConfirm: () => disband.mutateAsync(),
        }
    }
  })()

  return (
    <ConfirmDialog
      title={props.title}
      description={props.description}
      confirmLabel={props.title}
      destructive={props.destructive}
      open
      onOpenChange={(open) => {
        if (!open) onClose()
      }}
      onConfirm={props.onConfirm}
    />
  )
}

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
  const [rosterAction, setRosterAction] = useState<RosterAction | null>(null)
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
  const disbanded = data.disbanded ?? false
  const rosterEditable = !disbanded && (data.roster_editable ?? false)

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
            backfilled={data.backfilled}
          />
        </div>
        <WaitlistDetails status={data.registration_status} waitlist={data} />
        {data.reject_reason && (
          <p
            data-slot="reject-reason"
            className="break-words text-body text-muted-foreground"
          >
            {REJECT_REASON_PREFIX}
            {data.reject_reason}
          </p>
        )}
        {disbanded && (
          <p className="text-body text-muted-foreground">
            {TEAM_DISBANDED_NOTE}
          </p>
        )}
        {renderStatusExtra?.(data)}
      </header>
      {!disbanded && data.invite_token && (
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
      )}
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
          readOnly={disbanded}
          myRole={data.my_role}
          rosterEditable={rosterEditable}
          onTransferCaptain={(member) =>
            setRosterAction({ kind: "transfer", member })
          }
          onRemoveMember={(member) =>
            setRosterAction({ kind: "remove", member })
          }
          onLeaveTeam={() => setRosterAction({ kind: "leave" })}
        />
        {rosterEditable && data.my_role === "captain" && (
          <Button
            type="button"
            variant="outline"
            className="h-10 w-full border-destructive text-destructive hover:text-destructive sm:w-auto sm:self-start"
            onClick={() => setRosterAction({ kind: "disband" })}
          >
            {DISBAND_TEAM_TEXT}
          </Button>
        )}
      </section>
      {!disbanded && (
        <SubmitRegistrationSection
          team={data}
          onDeadlinePassed={() =>
            queryClient.invalidateQueries({
              queryKey: teamQueryOptions(teamId).queryKey,
            })
          }
        />
      )}
      {rosterAction && (
        <RosterActionDialog
          teamId={teamId}
          action={rosterAction}
          onClose={() => setRosterAction(null)}
        />
      )}
      {/* 開啟時才掛載：S17 平時不需要 S18 的 Sheet／Dialog 與表單狀態 */}
      {me && profileOpen && !disbanded && (
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
