import { queryOptions, useQuery } from "@tanstack/react-query"
import { Link, useSearch } from "@tanstack/react-router"

import { type TournamentMode, TournamentsService } from "@/client"
import { Button } from "@/components/ui/button"
import { useCurrentAccount, useIsSignedIn } from "@/features/identity/auth"
import {
  INVITE_EXPIRED_TEXT,
  INVITE_MISSING_TEXT,
  INVITE_SIGN_IN_TEXT,
  registrationLinkPath,
  registrationLinkStatusQueryOptions,
} from "@/features/tournaments/registration-link"
import { CreateTeamDialog } from "./CreateTeamDialog"
import { myTeamsQueryOptions } from "./queries"
import { RegistrationStatusCard } from "./RegistrationStatusCard"

/** 主辦方自己建立的賽事（只用來判斷是不是本賽事的主辦方）。 */
export const organizerTournamentsQueryOptions = () =>
  queryOptions({
    queryKey: ["tournaments", "organizer", "list"],
    queryFn: async () => (await TournamentsService.listMyTournaments()).data,
  })

function InviteHint({ text }: { text: string }) {
  return <p className="text-body text-muted-foreground">{text}</p>
}

/** 未登入、開著賽事報名連結：登入（或註冊並驗證 Email）後回到同一個含 invite 的網址。 */
function SignInForInvite({
  tournamentId,
  invite,
}: {
  tournamentId: string
  invite: string
}) {
  const redirect = registrationLinkPath(tournamentId, invite)
  return (
    <div className="flex flex-col items-start gap-3">
      <InviteHint text={INVITE_SIGN_IN_TEXT} />
      <Button asChild>
        <Link to="/login" search={{ redirect }}>
          登入
        </Link>
      </Button>
    </div>
  )
}

/**
 * S2 開放報名時的建隊入口（Story 3.1 收尾；自訂賽事見 Story 3.10）：
 * - 未登入：不顯示；自訂賽事且網址帶 `invite` 時顯示「登入後即可建立隊伍。」＋「登入」，
 *   沒帶 `invite` 時顯示索取連結的提示
 * - 已在本賽事有隊伍：顯示該隊的 Registration status card（點擊到 S17）
 * - 本賽事的主辦方：不顯示
 * - 自訂賽事：沒有 `invite` 顯示索取連結的提示；連結不符顯示已失效的提示
 * - 其他：S16「建立隊伍」（Email 未驗證時停用並說明原因；自訂賽事建隊時帶 token）
 *
 * 帳號、我的隊伍、主辦方賽事、連結檢查任一查詢還沒完成或失敗時不顯示，避免按了才被
 * 伺服器拒絕。校園賽忽略網址的 `invite`。
 */
export function CreateTeamEntry({
  tournamentId,
  mode = "campus",
}: {
  tournamentId: string
  mode?: TournamentMode
}) {
  const search: { invite?: string } = useSearch({ strict: false })
  const isCustom = mode === "custom"
  const invite = isCustom ? search.invite : undefined
  const signedIn = useIsSignedIn()
  const account = useCurrentAccount()
  const myTeams = useQuery({ ...myTeamsQueryOptions(), enabled: signedIn })
  const isOrganizer = account.data?.is_organizer === true
  const organizerTournaments = useQuery({
    ...organizerTournamentsQueryOptions(),
    enabled: signedIn && isOrganizer,
  })
  const linkStatus = useQuery({
    ...registrationLinkStatusQueryOptions(tournamentId, invite ?? ""),
    enabled: signedIn && invite !== undefined,
  })

  if (!signedIn) {
    if (invite !== undefined) {
      return <SignInForInvite tournamentId={tournamentId} invite={invite} />
    }
    return isCustom ? <InviteHint text={INVITE_MISSING_TEXT} /> : null
  }
  if (!account.data || !myTeams.data) return null

  const myTeam = myTeams.data.find(
    (card) => card.tournament_id === tournamentId,
  )
  if (myTeam) return <RegistrationStatusCard card={myTeam} />

  if (isOrganizer) {
    if (!organizerTournaments.data) return null
    if (organizerTournaments.data.some((t) => t.id === tournamentId)) {
      return null
    }
  }

  if (isCustom) {
    if (invite === undefined) return <InviteHint text={INVITE_MISSING_TEXT} />
    if (!linkStatus.data) return null
    if (!linkStatus.data.valid) return <InviteHint text={INVITE_EXPIRED_TEXT} />
  }

  return (
    <div className="flex flex-col items-start">
      <CreateTeamDialog tournamentId={tournamentId} inviteToken={invite} />
    </div>
  )
}
