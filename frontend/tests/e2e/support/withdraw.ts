// Story 3.7 退賽 e2e 的前置資料：走公開 API 建立已核准的主辦方、遊戲與開放報名的賽事，
// 以及隊長送出、撤回報名。被測的退賽操作走畫面，這裡只準備資料與製造「確認前已被撤回」的狀態。
// 這裡的請求不經過瀏覽器，不計入 NFR-2 的回應時間。
import { newTestAccount, platformAdmin, type TestAccount } from "./accounts"
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

/**
 * Story 3.8：與 `createOpenTournamentByApi` 相同的前置資料（已核准的主辦方、遊戲、開放報名
 * 且在優先期內的校園賽），另外回傳主辦方帳號，讓主辦方能在瀏覽器登入操作 S29。
 */
export async function createOpenTournamentWithOrganizerByApi(
  game: GameConfig,
  suffix: string,
  capacity: number,
): Promise<{ tournamentId: string; organizer: TestAccount }> {
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
        name: `E2E 退回 ${suffix}`,
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
  return { tournamentId: tournament.id, organizer }
}

/** Story 4.5：主辦方走 API 抽籤（開放報名中抽籤會立即結束報名），之後的退賽走畫面。 */
export async function apiDrawBracket(
  tournamentId: string,
  organizer: TestAccount,
) {
  await request("POST", `/tournaments/${tournamentId}/draw`, {
    token: await apiLogin(organizer),
  })
}

/**
 * Story 3.10 第 2 部分：與 `createOpenTournamentByApi` 相同的前置資料（已核准的主辦方與遊戲），
 * 但不建立賽事：自訂賽事由主辦方在 S26 走畫面建立。回傳主辦方帳號與遊戲名稱。
 */
export async function createOrganizerAndGameByApi(
  game: GameConfig,
  suffix: string,
): Promise<{ organizer: TestAccount; gameName: string }> {
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

  const gameName = `${game.name} ${suffix}`
  await request("POST", "/admin/games", {
    token: adminToken,
    json: {
      name: gameName,
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
  return { organizer, gameName }
}

/** Story 3.10 第 2 部分：走 API 註冊 `count` 個已驗證 Email 的帳號（分屬不同學校）。 */
export async function createVerifiedAccountsByApi(
  role: string,
  count: number,
): Promise<TestAccount[]> {
  const schools = await request<{ id: string }[]>("GET", "/schools")
  const accounts = Array.from({ length: count }, () => newTestAccount(role))
  for (const [index, account] of accounts.entries()) {
    await request("POST", "/accounts", {
      json: {
        email: account.email,
        password: account.password,
        display_name: account.displayName,
        school_id: schools[index % schools.length].id,
      },
    })
  }
  await markEmailsVerified(accounts.map((account) => account.email))
  return accounts
}
