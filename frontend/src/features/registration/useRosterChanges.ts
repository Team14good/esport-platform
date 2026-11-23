import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"

import { RegistrationService, type TeamDetail } from "@/client"
import { notifySuccess } from "@/lib/feedback"
import { myTeamsQueryOptions, teamQueryOptions } from "./queries"

export const MEMBER_REMOVED_TEXT = "已移除隊員"
export const CAPTAIN_TRANSFERRED_TEXT = "已轉讓隊長"
export const TEAM_LEFT_TEXT = "已退出隊伍"
export const TEAM_DISBANDED_TEXT = "已解散隊伍"

/**
 * 隊員異動（Story 3.11）共用的快取處理：成功與失敗都讓 S12 重新取得；失敗時隊伍也重新取得，
 * 讓名單與選單跟上伺服器（錯誤訊息由 ConfirmDialog 顯示）。
 */
function useRosterCache(teamId: string) {
  const queryClient = useQueryClient()
  const teamKey = teamQueryOptions(teamId).queryKey
  const invalidateMyTeams = () =>
    queryClient.invalidateQueries({ queryKey: myTeamsQueryOptions().queryKey })
  return {
    setTeam: (team: TeamDetail) => queryClient.setQueryData(teamKey, team),
    removeTeam: () => queryClient.removeQueries({ queryKey: teamKey }),
    invalidateMyTeams,
    onError: () => {
      queryClient.invalidateQueries({ queryKey: teamKey })
      invalidateMyTeams()
    },
  }
}

/** 隊長移除隊員：成功後以回應更新名單，Toast「已移除隊員」。 */
export function useRemoveMember(teamId: string) {
  const cache = useRosterCache(teamId)
  return useMutation({
    mutationFn: async (accountId: string) =>
      (
        await RegistrationService.removeTeamMember({
          path: { team_id: teamId, account_id: accountId },
        })
      ).data,
    onSuccess: (team) => {
      cache.setTeam(team)
      cache.invalidateMyTeams()
      notifySuccess(MEMBER_REMOVED_TEXT)
    },
    onError: cache.onError,
  })
}

/** 隊長轉讓隊長：成功後以回應更新名單（自己成為一般隊員），Toast「已轉讓隊長」。 */
export function useTransferCaptain(teamId: string) {
  const cache = useRosterCache(teamId)
  return useMutation({
    mutationFn: async (accountId: string) =>
      (
        await RegistrationService.transferTeamCaptain({
          path: { team_id: teamId },
          body: { account_id: accountId },
        })
      ).data,
    onSuccess: (team) => {
      cache.setTeam(team)
      cache.invalidateMyTeams()
      notifySuccess(CAPTAIN_TRANSFERRED_TEXT)
    },
    onError: cache.onError,
  })
}

/**
 * 退出與解散成功後已看不到原隊伍的可操作頁面：先導向 S12，導頁完成（S17 已卸載）後才移除
 * 隊伍快取。若先移除，S17 仍掛載時重新渲染會重建查詢、再抓一次隊伍而拿到 403。
 */
function useLeaveTeamPage(teamId: string, successText: string) {
  const cache = useRosterCache(teamId)
  const navigate = useNavigate()
  return {
    onSuccess: () => {
      cache.invalidateMyTeams()
      notifySuccess(successText)
      void navigate({ to: "/me/teams" }).then(() => cache.removeTeam())
    },
    onError: cache.onError,
  }
}

/** 隊員退出隊伍：成功後導向 S12，Toast「已退出隊伍」。 */
export function useLeaveTeam(teamId: string) {
  const handlers = useLeaveTeamPage(teamId, TEAM_LEFT_TEXT)
  return useMutation({
    mutationFn: async () => {
      await RegistrationService.leaveTeam({ path: { team_id: teamId } })
    },
    ...handlers,
  })
}

/** 隊長解散隊伍：成功後導向 S12，Toast「已解散隊伍」。 */
export function useDisbandTeam(teamId: string) {
  const handlers = useLeaveTeamPage(teamId, TEAM_DISBANDED_TEXT)
  return useMutation({
    mutationFn: async () => {
      await RegistrationService.disbandTeam({ path: { team_id: teamId } })
    },
    ...handlers,
  })
}
