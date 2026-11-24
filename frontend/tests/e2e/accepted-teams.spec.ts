// Story 3.9：觀眾在 S2「正取隊伍」分頁看名單；校園賽優先期內顯示空狀態與倒數。
// 公開 API 以 page.route 回傳假資料，只驗證畫面流程與版面（desktop、mobile-375）；
// 走真 API 的版本在 spectator.spec.ts（抽籤後觀眾看到所有隊伍）。
import type { Page, Route } from "@playwright/test"

import type { PublicAcceptedTeams, PublicTournament } from "../../src/client"
import { expect, test } from "./support/fixtures"
import { expectNoHorizontalScroll } from "./support/layout"

const TOURNAMENT_ID = "tournament-accepted-teams"
const API_PATH = new RegExp(
  `/api/v1/tournaments/${TOURNAMENT_ID}(/accepted-teams)?/?(\\?.*)?$`,
)

// 隊名最長 30 字：放一個很長的隊名，確認手機不出現橫向捲動
const TEAMS = [
  { id: "team-1", name: "北極星電競社" },
  { id: "team-2", name: "夜貓隊" },
  { id: "team-3", name: `政大資科一隊${"長".repeat(24)}` },
  { id: "team-4", name: "Thunder Owls" },
]

function tournament(): PublicTournament {
  const day = 24 * 60 * 60 * 1000
  const now = Date.now()
  return {
    id: TOURNAMENT_ID,
    name: "正取名單測試盃",
    status: "open",
    mode: "campus",
    game_name: "特戰英豪",
    capacity: 16,
    registration_start: new Date(now - day).toISOString(),
    priority_end: new Date(now + day).toISOString(),
    registration_end: new Date(now + 5 * day).toISOString(),
    start_at: new Date(now + 6 * day).toISOString(),
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

async function mockTournament(page: Page, accepted: PublicAcceptedTeams) {
  const data = tournament()
  await page.route(API_PATH, (route) => {
    if (route.request().method() !== "GET") return route.fallback()
    const match = new URL(route.request().url()).pathname.match(API_PATH)
    if (match === null) return route.fallback()
    return json(route, 200, match[1] === undefined ? data : accepted)
  })
}

test(
  "未登入的觀眾從 S2 總覽切到「正取隊伍」看到隊名",
  { tag: ["@story-3.9", "@FR-34", "@NFR-7"] },
  async ({ page }, testInfo) => {
    await mockTournament(page, { announce_at: null, teams: TEAMS })

    await test.step("S2 總覽顯示已正取隊數", async () => {
      await page.goto(`/tournaments/${TOURNAMENT_ID}`)
      await expect(page.getByText("已正取 4／16 隊")).toBeVisible()
      await expectNoHorizontalScroll(page)
    })

    await test.step("切到「正取隊伍」分頁，依序看到隊名、沒有「檢舉」", async () => {
      await page.getByRole("tab", { name: "正取隊伍" }).click()
      await expect(page).toHaveURL(
        new RegExp(`/tournaments/${TOURNAMENT_ID}/teams$`),
      )
      const items = page.locator("[data-slot=accepted-teams] > li")
      await expect(items).toHaveText(TEAMS.map((team) => team.name))
      await expect(page.getByRole("button", { name: "檢舉" })).toHaveCount(0)
      await expectNoHorizontalScroll(page)
      await page.screenshot({
        path: testInfo.outputPath("s2-accepted-teams.png"),
        fullPage: true,
      })
    })
  },
)

test(
  "校園賽優先期內：「優先期結束後公布正取隊伍。」與優先期結束倒數",
  { tag: ["@story-3.9", "@FR-34", "@NFR-7"] },
  async ({ page }, testInfo) => {
    const announceAt = new Date(Date.now() + 2 * 60 * 60 * 1000).toISOString()
    await mockTournament(page, { announce_at: announceAt, teams: [] })

    await page.goto(`/tournaments/${TOURNAMENT_ID}/teams`)
    await expect(page.getByText("優先期結束後公布正取隊伍。")).toBeVisible()
    const countdown = page.locator("[data-slot=countdown]")
    await expect(countdown).toContainText("優先期結束")
    await expect(countdown).toHaveAttribute("data-variant", "muted")
    await expect(page.locator("[data-slot=accepted-teams]")).toHaveCount(0)
    await expectNoHorizontalScroll(page)
    await page.screenshot({
      path: testInfo.outputPath("s2-accepted-teams-priority.png"),
      fullPage: true,
    })
  },
)
