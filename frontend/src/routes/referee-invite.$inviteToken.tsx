import { createFileRoute } from "@tanstack/react-router"

import { RefereeInvitePage } from "@/features/tournaments/RefereeInvitePage"

// 不需登入：未登入時頁面提供註冊與登入（帶 redirect 回到這裡）
export const Route = createFileRoute("/referee-invite/$inviteToken")({
  head: () => ({ meta: [{ title: "接受裁判邀請 · FLOW" }] }),
  component: RefereeInviteRoute,
})

function RefereeInviteRoute() {
  const { inviteToken } = Route.useParams()
  return <RefereeInvitePage key={inviteToken} token={inviteToken} />
}
