import { createFileRoute } from "@tanstack/react-router"

import type { MyTeamCard } from "@/client"
import { MyTeamNextMatch } from "@/features/competition/NextMatchRow"
import { TeamDisqualificationReason } from "@/features/disputes/TeamDisqualificationReason"
import { requireSignedIn } from "@/features/identity/auth"
import { MyTeamsPage } from "@/features/registration/MyTeamsPage"

// 檔名 me_.teams：/me（S11 身分選擇）沒有 Outlet，S12 不巢狀在它底下
export const Route = createFileRoute("/me_/teams")({
  beforeLoad: requireSignedIn,
  head: () => ({ meta: [{ title: "我的隊伍 · FLOW" }] }),
  component: MyTeamsRoute,
})

// 已參賽的隊伍在卡片下方加一列下一場（competition）；取消資格的隊伍加處理理由（disputes，6.5）。
// registration 的頁面不依賴 competition、disputes
function renderTeamExtra(card: MyTeamCard) {
  return (
    <>
      <MyTeamNextMatch card={card} />
      {card.registration_status === "disqualified" && (
        <TeamDisqualificationReason teamId={card.team_id} />
      )}
    </>
  )
}

function MyTeamsRoute() {
  return <MyTeamsPage renderTeamExtra={renderTeamExtra} />
}
