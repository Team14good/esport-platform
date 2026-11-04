// 觀眾 e2e 的假 API：用 page.route 攔下公開的賽事、對戰樹與單場 GET，回傳單元測試用的同一份假對戰樹
// （32 隊「進行中」，src/features/competition/bracket-fixtures.ts）。示範資料（7.1）還沒有已抽籤的賽事，
// 先用這個讓 S3 → S4 的畫面流程有 e2e；7.1 有資料後仍要補一份走真 API 的版本（見 deferred-work.md）。
// 只攔假賽事 id 的 GET，其他請求照常送到後端。
import type { Page, Route } from "@playwright/test"

import type { PublicTournament } from "../../../src/client"
import {
  createBracketFixture,
  FIXTURE_TOURNAMENT_ID,
} from "../../../src/features/competition/bracket-fixtures"
import {
  FIXTURE_GAME_NAME,
  FIXTURE_TOURNAMENT_NAME,
  matchDetailFromBracket,
} from "../../../src/features/competition/match-fixtures"

export { FIXTURE_TOURNAMENT_ID }

/** 假賽事的場次 id：「match-<代碼>」（與 bracket-fixtures 相同） */
export function fixtureMatchId(code: string): string {
  return `match-${code}`
}

const TOURNAMENT_PATH = new RegExp(
  `/api/v1/tournaments/${FIXTURE_TOURNAMENT_ID}(/bracket|/matches/([^/?]+))?/?(\\?.*)?$`,
)

function fixtureTournament(): PublicTournament {
  return {
    id: FIXTURE_TOURNAMENT_ID,
    name: FIXTURE_TOURNAMENT_NAME,
    status: "ongoing",
    game_name: FIXTURE_GAME_NAME,
    capacity: 32,
    registration_start: "2026-10-12T11:00:00Z",
    priority_end: "2026-10-13T11:00:00Z",
    registration_end: "2026-10-17T11:00:00Z",
    start_at: "2026-10-18T11:00:00Z",
    round_interval_minutes: 180,
    livestream_url: null,
  }
}

function json(route: Route, status: number, body: unknown) {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  })
}

/** 攔下假賽事的公開 GET：賽事、對戰樹、單場（不存在的場次回 404 `MATCH_NOT_FOUND`）。 */
export async function mockFixtureTournament(page: Page): Promise<void> {
  const bracket = createBracketFixture({
    teamCount: 32,
    scenario: "in_progress",
  })
  await page.route(TOURNAMENT_PATH, (route) => {
    if (route.request().method() !== "GET") return route.fallback()
    const match = new URL(route.request().url()).pathname.match(TOURNAMENT_PATH)
    if (match === null) return route.fallback()
    const [, sub, matchId] = match
    if (sub === undefined) return json(route, 200, fixtureTournament())
    if (sub === "/bracket") return json(route, 200, bracket)
    const detail = matchDetailFromBracket(bracket, decodeURIComponent(matchId))
    return detail
      ? json(route, 200, detail)
      : json(route, 404, {
          detail: { code: "MATCH_NOT_FOUND", message: "找不到這個場次。" },
        })
  })
}
