// Story 5.6：賽事結束後，觀眾在 S2、S3 看到頒獎台與名次標記。
// 本機示範資料沒有已結束的賽事，公開 API 以 page.route 回傳已結束的 32 隊假資料，測畫面流程與版面。
import type { Page, Route } from "@playwright/test"

import type { PublicBracket, PublicTournament } from "../../src/client"
import { createBracketFixture } from "../../src/features/competition/bracket-fixtures"
import { matchDetailFromBracket } from "../../src/features/competition/match-fixtures"
import { expect, test } from "./support/fixtures"
import { expectNoHorizontalScroll, isNarrowViewport } from "./support/layout"

const TOURNAMENT_ID = "tournament-finished"
const TOURNAMENT_NAME = "已結束的期中盃"
const API_PATH = new RegExp(
  `/api/v1/tournaments/${TOURNAMENT_ID}(/bracket|/matches/([^/?]+))?/?(\\?.*)?$`,
)

function finishedBracket(): PublicBracket {
  const fixture = {
    ...createBracketFixture({ teamCount: 32, scenario: "finished" }),
    tournament_id: TOURNAMENT_ID,
  }
  const teams = fixture.matches.flatMap((match) => {
    if (match.round_no !== fixture.rounds) return []
    const winnerIsA = match.winner_id === match.team_a?.id
    return [
      {
        thirdPlace: match.is_third_place,
        winner: winnerIsA ? match.team_a : match.team_b,
        loser: winnerIsA ? match.team_b : match.team_a,
      },
    ]
  })
  const final = teams.find((row) => !row.thirdPlace)
  const third = teams.find((row) => row.thirdPlace)
  return {
    ...fixture,
    podium: {
      champion: final?.winner ?? null,
      runner_up: final?.loser ?? null,
      third_place: third?.winner ?? null,
    },
  }
}

const tournament: PublicTournament = {
  id: TOURNAMENT_ID,
  name: TOURNAMENT_NAME,
  status: "finished",
  game_name: "特戰英豪",
  capacity: 32,
  registration_start: "2026-10-12T11:00:00Z",
  priority_end: "2026-10-13T11:00:00Z",
  registration_end: "2026-10-17T11:00:00Z",
  start_at: "2026-10-18T11:00:00Z",
  round_interval_minutes: 180,
  livestream_url: null,
}

function json(route: Route, status: number, body: unknown) {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  })
}

async function mockFinishedTournament(page: Page, bracket: PublicBracket) {
  await page.route(API_PATH, (route) => {
    if (route.request().method() !== "GET") return route.fallback()
    const match = new URL(route.request().url()).pathname.match(API_PATH)
    if (match === null) return route.fallback()
    const [, sub, matchId] = match
    if (sub === undefined) return json(route, 200, tournament)
    if (sub === "/bracket") return json(route, 200, bracket)
    const detail = matchDetailFromBracket(bracket, decodeURIComponent(matchId))
    return detail
      ? json(route, 200, detail)
      : json(route, 404, {
          detail: { code: "MATCH_NOT_FOUND", message: "找不到這個場次。" },
        })
  })
}

test(
  "賽事結束：S2、S3 顯示頒獎台，點冠軍進入最後一場的 S4",
  {
    tag: ["@story-5.6", "@FR-21", "@FR-35"],
  },
  async ({ page }, testInfo) => {
    const bracket = finishedBracket()
    await mockFinishedTournament(page, bracket)
    const podium = page.getByRole("region", { name: "賽事名次" })
    const rows = podium.locator("[data-slot=podium-row]")
    const championName = bracket.podium?.champion?.name ?? ""

    await test.step("S2 最上方顯示頒獎台", async () => {
      await page.goto(`/tournaments/${TOURNAMENT_ID}`)
      await expect(rows).toHaveCount(3)
      await expect(podium.getByText(championName)).toBeVisible()
      await expectNoHorizontalScroll(page)
      await page.screenshot({ path: testInfo.outputPath("s2-podium.png") })
    })

    await test.step("S3 對戰樹上方顯示頒獎台，決賽卡有名次標記", async () => {
      await page.goto(`/tournaments/${TOURNAMENT_ID}/bracket`)
      await expect(rows).toHaveCount(3)
      await expect(
        page.locator("[data-slot=bracket-mark-tag][data-tone=brand]").nth(1),
      ).toHaveText("冠軍")
      await expectNoHorizontalScroll(page)

      const first = await rows.nth(0).boundingBox()
      const second = await rows.nth(1).boundingBox()
      expect(first).not.toBeNull()
      expect(second).not.toBeNull()
      if (isNarrowViewport(page)) {
        // 手機直排
        expect(second?.y ?? 0).toBeGreaterThan(first?.y ?? 0)
      } else {
        // 桌機三欄並列
        expect(second?.x ?? 0).toBeGreaterThan(first?.x ?? 0)
      }
      await page.screenshot({ path: testInfo.outputPath("s3-podium.png") })
    })

    await test.step("點冠軍進入該隊最後一場", async () => {
      await podium.getByRole("link", { name: championName }).click()
      await expect(page).toHaveURL(
        new RegExp(`/tournaments/${TOURNAMENT_ID}/matches/`),
      )
      await expect(page.getByRole("heading", { level: 1 })).toContainText(
        "決賽",
      )
    })
  },
)
