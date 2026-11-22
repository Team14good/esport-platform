import { createFileRoute } from "@tanstack/react-router"

import type { TeamDetail } from "@/client"
import { RetireTeamSection } from "@/features/competition/RetireTeamSection"
import { TeamDisqualificationReason } from "@/features/disputes/TeamDisqualificationReason"
import { requireSignedIn } from "@/features/identity/auth"
import { TeamPage } from "@/features/registration/TeamPage"

export const Route = createFileRoute("/teams/$teamId")({
  beforeLoad: requireSignedIn,
  head: () => ({ meta: [{ title: "隊伍 · FLOW" }] }),
  component: TeamRoute,
})

// 報名狀態下方的額外內容：取消資格時顯示主辦方的處理理由（disputes，6.5）；
// 已參賽時顯示抽籤後的「退賽」（competition，4.5；registration 的頁面不依賴 competition）
function renderStatusExtra(team: TeamDetail) {
  const disqualified = team.registration_status === "disqualified"
  if (team.my_role === "captain") {
    // 隊長一律掛載退賽區塊（它自己依報名狀態決定顯不顯示）：退賽被拒後隊伍重新取得，
    // 狀態可能已變，卻不能讓開著的確認對話框連同錯誤訊息一起消失
    return (
      <>
        <RetireTeamSection
          teamId={team.id}
          registrationStatus={team.registration_status}
        />
        {disqualified && <TeamDisqualificationReason teamId={team.id} />}
      </>
    )
  }
  return disqualified ? <TeamDisqualificationReason teamId={team.id} /> : null
}

function TeamRoute() {
  const { teamId } = Route.useParams()
  return (
    <TeamPage
      key={teamId}
      teamId={teamId}
      renderStatusExtra={renderStatusExtra}
    />
  )
}
