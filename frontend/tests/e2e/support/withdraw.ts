// Story 3.7 退賽 e2e 的前置資料：走公開 API 建立已核准的主辦方、遊戲與開放報名的賽事，
// 以及隊長送出、撤回報名。被測的退賽操作走畫面，這裡只準備資料與製造「確認前已被撤回」的狀態。
// 這裡的請求不經過瀏覽器，不計入 NFR-2 的回應時間。
import { newTestAccount, platformAdmin } from "./accounts"
import { apiLogin, type BulkTeam } from "./bulk"
import { markEmailsVerified } from "./db"
import { minRoundIntervalMinutes } from "./drill"
import { API_URL } from "./env"
import type { GameConfig } from "./games"

const HOUR_MS = 3_600_000
const DAY_MS = 24 * HOUR_MS

async function request<T>(
  method: string,
  path: string,
  options: { token?: string; json?: unknown } = {},
): Promise<T> {
  const response = await fetch(`${API_URL}/api/v1${path}`, {
    method,
    headers: {
      ...(options.token ? { Authorization: `Bearer ${options.token}` } : {}),
      ...(options.json !== undefined
        ? { "Content-Type": "application/json" }
        : {}),
    },
    body: options.json !== undefined ? JSON.stringify(options.json) : undefined,
  })
  if (!response.ok) {
    throw new Error(
      `${method} ${path} → ${response.status}：${await response.text()}`,
    )
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

/**
 * 建立主辦方（註冊、標成已驗證、申請、由平台管理員核准）與遊戲，再建立校園賽：
 * 報名開始＝現在前 1 小時（建立後即「開放報名」、在優先期內），截止＝7 天後，名額 `capacity`。
 * 回傳賽事 id。
 */
export async function createOpenTournamentByApi(
  game: GameConfig,
  suffix: string,
  capacity: number,
): Promise<string> {
  const adminToken = await apiLogin(platformAdmin())
  const schools = await request<{ id: string }[]>("GET", "/schools")

  const organizer = newTestAccount("organizer")
  await request("POST", "/accounts", {
    json: {
      email: organizer.email,
      password: organizer.password,
      display_name: organizer.displayName,
      school_id: schools[0].id,
    },
  })
  await markEmailsVerified([organizer.email])
  const organizerToken = await apiLogin(organizer)
  const application = await request<{ id: string }>(
    "POST",
    "/organizer-applications",
    {
      token: organizerToken,
      json: { club_name: `E2E 電競社 ${suffix}`, school_id: schools[0].id },
    },
  )
  await request(
    "POST",
    `/admin/organizer-applications/${application.id}/approval`,
    { token: adminToken },
  )

  const created = await request<{ id: string }>("POST", "/admin/games", {
    token: adminToken,
    json: {
      name: `${game.name} ${suffix}`,
      starters: game.starters,
      substitutes: game.substitutes,
      default_bo: game.defaultBestOf,
      game_minutes: game.minutesPerGame,
      score_type: game.scoreType,
      rank_tiers: game.ranks.map(({ name, points }) => ({
        name,
        score: points,
      })),
    },
  })

  const now = Date.now()
  const tournament = await request<{ id: string; status: string }>(
    "POST",
    "/organizer/tournaments",
    {
      token: organizerToken,
      json: {
        name: `E2E 退賽 ${suffix}`,
        game_id: created.id,
        capacity,
        registration_start: new Date(now - HOUR_MS).toISOString(),
        registration_end: new Date(now + 7 * DAY_MS).toISOString(),
        start_at: new Date(now + 8 * DAY_MS).toISOString(),
        round_interval_minutes: minRoundIntervalMinutes(game),
      },
    },
  )
  if (tournament.status !== "open") {
    throw new Error(`賽事建立後狀態是 ${tournament.status}，不是 open`)
  }
  return tournament.id
}

/** 隊長走 API 送出報名。 */
export async function apiSubmitRegistration(team: BulkTeam) {
  await request("POST", `/teams/${team.id}/submission`, {
    token: team.captain.token,
  })
}

/** 隊長走 API 撤回報名（用來讓畫面上已開啟的確認對話框變成不可撤回）。 */
export async function apiWithdrawRegistration(team: BulkTeam) {
  await request("POST", `/teams/${team.id}/withdrawal`, {
    token: team.captain.token,
  })
}
