import { queryOptions, useQuery } from "@tanstack/react-query"

import { TournamentsService } from "@/client"
import { useCurrentAccount, useIsSignedIn } from "@/features/identity/auth"
import { CreateTeamDialog } from "./CreateTeamDialog"
import { myTeamsQueryOptions } from "./queries"
import { RegistrationStatusCard } from "./RegistrationStatusCard"

/** 主辦方自己建立的賽事（只用來判斷是不是本賽事的主辦方）。 */
export const organizerTournamentsQueryOptions = () =>
  queryOptions({
    queryKey: ["tournaments", "organizer", "list"],
    queryFn: async () => (await TournamentsService.listMyTournaments()).data,
  })

/**
 * S2 開放報名時的建隊入口（Story 3.1 收尾）：
 * - 未登入：不顯示
 * - 已在本賽事有隊伍：顯示該隊的 Registration status card（點擊到 S17）
 * - 本賽事的主辦方：不顯示
 * - 其他：S16「建立隊伍」（Email 未驗證時停用並說明原因）
 *
 * 帳號、我的隊伍、主辦方賽事任一查詢還沒完成或失敗時不顯示，避免按了才被伺服器拒絕。
 */
export function CreateTeamEntry({ tournamentId }: { tournamentId: string }) {
  const signedIn = useIsSignedIn()
  const account = useCurrentAccount()
  const myTeams = useQuery({ ...myTeamsQueryOptions(), enabled: signedIn })
  const isOrganizer = account.data?.is_organizer === true
  const organizerTournaments = useQuery({
    ...organizerTournamentsQueryOptions(),
    enabled: signedIn && isOrganizer,
  })

  if (!signedIn || !account.data || !myTeams.data) return null

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

  return (
    <div className="flex flex-col items-start">
      <CreateTeamDialog tournamentId={tournamentId} />
    </div>
  )
}
