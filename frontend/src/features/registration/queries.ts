import { queryOptions } from "@tanstack/react-query"

import { RegistrationService } from "@/client"

/** registration 相關 query 的共同前綴。 */
export const REGISTRATION_QUERY_KEY = ["registration"] as const

export const teamQueryOptions = (teamId: string) =>
  queryOptions({
    queryKey: [...REGISTRATION_QUERY_KEY, "team", teamId],
    queryFn: async () =>
      (await RegistrationService.readTeam({ path: { team_id: teamId } })).data,
  })

export const myTeamsQueryOptions = () =>
  queryOptions({
    queryKey: [...REGISTRATION_QUERY_KEY, "my-teams"],
    queryFn: async () => (await RegistrationService.listMyTeams()).data,
  })

export const teamInviteQueryOptions = (token: string) =>
  queryOptions({
    queryKey: [...REGISTRATION_QUERY_KEY, "invite", token],
    queryFn: async () =>
      (await RegistrationService.previewTeamInvite({ path: { token } })).data,
  })

/** S19 的邀請連結（完整網址）；S17 的 Invite link field 顯示這個。 */
export function teamInviteUrl(token: string | null): string {
  // 已解散的隊伍（Story 3.11）沒有邀請 token
  if (token === null) return ""
  return `${window.location.origin}/join/${encodeURIComponent(token)}`
}

/**
 * S2「正取隊伍」的公開名單（不需登入，Story 3.9）。校園賽優先期內 `announce_at`
 * 為優先期結束時間、`teams` 為空。
 */
export const publicAcceptedTeamsQueryOptions = (tournamentId: string) =>
  queryOptions({
    queryKey: [...REGISTRATION_QUERY_KEY, "accepted-teams", tournamentId],
    queryFn: async () =>
      (
        await RegistrationService.listAcceptedTeams({
          path: { tournament_id: tournamentId },
        })
      ).data,
  })
