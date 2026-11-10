// 走公開 API 準備大量資料與打完重複的場次：32 隊全走畫面要約 1 小時（第二階段已涵蓋整隊走畫面的流程）。
// 這裡的請求不經過瀏覽器，不計入 NFR-2 的回應時間。
import { expect } from "@playwright/test"

import type {
  PublicBracket,
  PublicMatch,
  TeamDetail,
} from "../../../src/client"
import { newTestAccount, type TestAccount } from "./accounts"
import { markEmailsVerified } from "./db"
import { API_URL } from "./env"
import { type GameConfig, rosterLimit, winsNeeded } from "./games"

type RequestOptions = { token?: string; json?: unknown; form?: FormData }

async function call<T>(
  method: string,
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const response = await fetch(`${API_URL}/api/v1${path}`, {
    method,
    headers: {
      ...(options.token ? { Authorization: `Bearer ${options.token}` } : {}),
      ...(options.json !== undefined
        ? { "Content-Type": "application/json" }
        : {}),
    },
    body:
      options.form ??
      (options.json !== undefined ? JSON.stringify(options.json) : undefined),
  })
  if (!response.ok) {
    throw new Error(
      `${method} ${path} → ${response.status}：${await response.text()}`,
    )
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

/** 同時最多 `size` 個工作：密碼雜湊吃 CPU，全部同時送會拖垮後端。 */
async function inPool<T, R>(
  items: T[],
  size: number,
  work: (item: T, index: number) => Promise<R>,
): Promise<R[]> {
  const results: R[] = new Array(items.length)
  let next = 0
  await Promise.all(
    Array.from({ length: size }, async () => {
      while (next < items.length) {
        const index = next
        next += 1
        results[index] = await work(items[index], index)
      }
    }),
  )
  return results
}

export async function apiLogin(account: TestAccount): Promise<string> {
  const { access_token: token } = await call<{ access_token: string }>(
    "POST",
    "/access-tokens",
    { json: { email: account.email, password: account.password } },
  )
  return token
}

export type BulkMember = { account: TestAccount; token: string }

export type BulkTeam = {
  id: string
  name: string
  captain: BulkMember
}

/** 1×1 的 PNG，當作段位截圖 */
const SCREENSHOT = Uint8Array.from(
  atob(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
  ),
  (char) => char.charCodeAt(0),
)

async function saveProfile(
  team: TeamDetail,
  member: BulkMember,
  gameAccountId: string,
  rankName: string,
) {
  const form = new FormData()
  form.set("game_account_id", gameAccountId)
  form.set("rank_tier", rankName)
  form.set(
    "rank_screenshot",
    new Blob([SCREENSHOT], { type: "image/png" }),
    "rank.png",
  )
  await call("PUT", `/teams/${team.id}/members/me/profile`, {
    token: member.token,
    form,
  })
}

/**
 * 每校一隊、每隊滿編，全員填完參賽資料（校園賽每隊隊員學校要相同，每校一隊才全部成為代表隊）。
 * 回傳的第一隊還沒送出報名，留給畫面操作；其餘都已送出。
 */
export async function createRegisteredTeams(
  tournamentId: string,
  game: GameConfig,
  suffix: string,
): Promise<BulkTeam[]> {
  const schools = await call<{ id: string; name: string }[]>("GET", "/schools")
  expect(schools.length).toBeGreaterThanOrEqual(game.teamCount)

  const rosters = Array.from({ length: game.teamCount }, (_, teamIndex) =>
    Array.from({ length: rosterLimit(game) }, () => ({
      account: newTestAccount("bulk"),
      schoolId: schools[teamIndex].id,
    })),
  )
  await inPool(rosters.flat(), 4, async ({ account, schoolId }) =>
    call("POST", "/accounts", {
      json: {
        email: account.email,
        password: account.password,
        display_name: account.displayName,
        school_id: schoolId,
      },
    }),
  )
  await markEmailsVerified(rosters.flat().map(({ account }) => account.email))

  return inPool(rosters, 4, async (roster, teamIndex) => {
    const members: BulkMember[] = []
    for (const { account } of roster) {
      members.push({ account, token: await apiLogin(account) })
    }
    const [captain, ...others] = members
    const name = `E2E 第 ${teamIndex + 1} 隊 ${suffix.slice(-6)}`
    const team = await call<TeamDetail>(
      "POST",
      `/tournaments/${tournamentId}/teams`,
      { token: captain.token, json: { name } },
    )
    for (const member of others) {
      await call("POST", `/team-invites/${team.invite_token}/members`, {
        token: member.token,
      })
    }
    for (const [memberIndex, member] of members.entries()) {
      await saveProfile(
        team,
        member,
        `E2E-${teamIndex + 1}-${memberIndex + 1}`,
        game.ranks[(teamIndex + memberIndex) % game.ranks.length].name,
      )
    }
    if (teamIndex > 0) {
      await call("POST", `/teams/${team.id}/submission`, {
        token: captain.token,
      })
    }
    return { id: team.id, name, captain }
  })
}

export async function fetchRegistrationStatus(
  team: BulkTeam,
): Promise<TeamDetail["registration_status"]> {
  const detail = await call<TeamDetail>("GET", `/teams/${team.id}`, {
    token: team.captain.token,
  })
  return detail.registration_status
}

export function fetchBracket(tournamentId: string): Promise<PublicBracket> {
  return call("GET", `/tournaments/${tournamentId}/bracket`)
}

export async function fetchTournamentStatus(
  tournamentId: string,
): Promise<string> {
  const { status } = await call<{ status: string }>(
    "GET",
    `/tournaments/${tournamentId}`,
  )
  return status
}

/** 尚未打的、兩隊都確定的場次（`round` 那一輪，含季軍賽） */
export function playableMatches(bracket: PublicBracket, round: number) {
  return bracket.matches.filter(
    (match) =>
      match.round_no === round &&
      match.status === "scheduled" &&
      match.team_a !== null &&
      match.team_b !== null,
  )
}

export function teamsOf(match: PublicMatch): {
  teamA: NonNullable<PublicMatch["team_a"]>
  teamB: NonNullable<PublicMatch["team_b"]>
} {
  if (!match.team_a || !match.team_b) {
    throw new Error(`場次 ${match.code} 兩隊尚未確定`)
  }
  return { teamA: match.team_a, teamB: match.team_b }
}

export function findTeam(teams: BulkTeam[], id: string): BulkTeam {
  const team = teams.find((candidate) => candidate.id === id)
  if (!team) throw new Error(`找不到隊伍 ${id}`)
  return team
}

/** 一局的比分：`rounds` 型態給回合數，`win_loss` 只給勝方。 */
export function gameScore(game: GameConfig, winner: "a" | "b") {
  if (!game.sampleGameScore) return { winner_side: winner }
  const { winner: high, loser: low } = game.sampleGameScore
  return winner === "a"
    ? { score_a: high, score_b: low }
    : { score_a: low, score_b: high }
}

export async function apiCheckIn(
  tournamentId: string,
  matchId: string,
  captain: BulkMember,
) {
  await call(
    "POST",
    `/tournaments/${tournamentId}/matches/${matchId}/check-in`,
    {
      token: captain.token,
    },
  )
}

/** 兩隊報到，由 `scorerToken`（裁判或代為登錄的主辦方）登錄到分出勝負並送出系列結果。 */
export async function playMatchByApi(options: {
  tournamentId: string
  game: GameConfig
  match: PublicMatch
  teams: BulkTeam[]
  scorerToken: string
  winner: "a" | "b"
}) {
  const { tournamentId, game, match, teams, scorerToken, winner } = options
  const { teamA, teamB } = teamsOf(match)
  await apiCheckIn(tournamentId, match.id, findTeam(teams, teamA.id).captain)
  await apiCheckIn(tournamentId, match.id, findTeam(teams, teamB.id).captain)
  const path = `/tournaments/${tournamentId}/matches/${match.id}`
  for (let gameNo = 1; gameNo <= winsNeeded(game.defaultBestOf); gameNo += 1) {
    await call("PUT", `${path}/games/${gameNo}`, {
      token: scorerToken,
      json: gameScore(game, winner),
    })
  }
  await call("POST", `${path}/submit`, { token: scorerToken })
}

export async function playMatchesByApi(
  options: Omit<Parameters<typeof playMatchByApi>[0], "match"> & {
    matches: PublicMatch[]
  },
) {
  const { matches, ...rest } = options
  await inPool(matches, 4, (match) => playMatchByApi({ ...rest, match }))
}

export async function apiAssignReferee(
  tournamentId: string,
  matchId: string,
  organizerToken: string,
  refereeId: string,
) {
  await call("PUT", `/tournaments/${tournamentId}/matches/${matchId}/referee`, {
    token: organizerToken,
    json: { account_id: refereeId },
  })
}

export async function fetchAccountId(token: string): Promise<string> {
  const { id } = await call<{ id: string }>("GET", "/accounts/me", { token })
  return id
}

/** 等 worker 把這些場次處理成 `status`；回傳最新的對戰表。 */
export async function waitForMatchStatus(
  tournamentId: string,
  matchIds: string[],
  status: PublicMatch["status"],
  timeoutMs = 180_000,
): Promise<PublicBracket> {
  const ids = new Set(matchIds)
  let latest: PublicBracket | null = null
  await expect
    .poll(
      async () => {
        latest = await fetchBracket(tournamentId)
        return latest.matches.filter(
          (match) => ids.has(match.id) && match.status === status,
        ).length
      },
      { timeout: timeoutMs, intervals: [1_000] },
    )
    .toBe(ids.size)
  return latest as unknown as PublicBracket
}
