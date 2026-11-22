// Story 4.5：隊長在抽籤後於 S17 退賽，候補第 1 位遞補，觀眾在 S3 對戰樹看到新隊名。
// 主辦方、遊戲、賽事與隊伍走公開 API 準備（support/withdraw.ts、support/bulk.ts），
// 優先期結束改資料庫後由真的 worker 結算；被測的退賽操作與畫面檢查都走瀏覽器。
import type { Page } from "@playwright/test"

import { uniqueSuffix } from "./support/accounts"
import {
  type BulkTeam,
  createRegisteredTeams,
  fetchBracket,
  fetchRegistrationStatus,
  findTeam,
  teamsOf,
} from "./support/bulk"
import { endPriorityWindow } from "./support/db"
import { rolePage } from "./support/drawn"
import { expect, test } from "./support/fixtures"
import { FICTIONAL_GAME } from "./support/games"
import { expectNoHorizontalScroll } from "./support/layout"
import { bracketCardsOf } from "./support/matchday"
import {
  apiDrawBracket,
  apiSubmitRegistration,
  createOpenTournamentWithOrganizerByApi,
} from "./support/withdraw"

const RETIRE_TEXT = "退賽"
const RETIRE_DESCRIPTION =
  "退賽後無法恢復。有候補隊伍時，由候補第 1 位接手你們在對戰表上的位置；沒有候補時，對手以輪空晉級。"

/** S17 標題列的報名狀態徽章 */
function teamHeaderBadge(page: Page, teamName: string) {
  return page
    .locator("header")
    .filter({
      has: page.getByRole("heading", { name: teamName, level: 1 }),
    })
    .locator("[data-slot=status-badge]")
}

async function openTeamPage(page: Page, team: BulkTeam) {
  await page.goto(`/teams/${team.id}`)
  await expect(
    page.getByRole("heading", { name: team.name, level: 1 }),
  ).toBeVisible()
}

test(
  "抽籤後隊長退賽：候補遞補接手位置，S17 徽章與 S3 對戰樹跟著更新",
  {
    tag: ["@story-4.5", "@FR-17", "@NFR-7"],
  },
  async ({ newRoleContext }, testInfo) => {
    // 優先期結束後要等 worker 結算（輪詢最久約 90 秒）
    test.setTimeout(8 * 60_000)
    // 名額 4、5 隊報名：第 2～5 隊在優先期送出而成為正取，第 1 隊先搶期送出成為候補
    const suffix = uniqueSuffix()
    const game = { ...FICTIONAL_GAME, teamCount: 5 }
    const { tournamentId, organizer } =
      await createOpenTournamentWithOrganizerByApi(game, suffix, 4)
    const teams = await createRegisteredTeams(tournamentId, game, suffix)
    const [backup, ...starters] = teams

    await test.step("優先期結束後 worker 結算，四隊正取；第 1 隊送出後成為候補", async () => {
      await endPriorityWindow(tournamentId)
      for (const team of starters) {
        await expect
          .poll(() => fetchRegistrationStatus(team), {
            timeout: 90_000,
            intervals: [2_000],
          })
          .toBe("accepted")
      }
      await apiSubmitRegistration(backup)
      expect(await fetchRegistrationStatus(backup)).toBe("waitlisted")
    })

    await test.step("主辦方抽籤：四隊成為已參賽，候補仍是候補", async () => {
      await apiDrawBracket(tournamentId, organizer)
      for (const team of starters) {
        expect(await fetchRegistrationStatus(team)).toBe("drawn")
      }
      expect(await fetchRegistrationStatus(backup)).toBe("waitlisted")
    })

    // 退賽的是 M1 的 a 方（第一場待開打、沒有人報到）
    const bracket = await fetchBracket(tournamentId)
    const m1 = bracket.matches.find((match) => match.code === "M1")
    if (!m1) throw new Error("找不到 M1")
    const retiring = findTeam(teams, teamsOf(m1).teamA.id)
    const opponent = findTeam(teams, teamsOf(m1).teamB.id)

    const captain = await rolePage(
      newRoleContext,
      "退賽隊長",
      retiring.captain.account,
    )
    await test.step("S17 徽章是「已參賽」，有「退賽」按鈕；對話框的標題、內文與按鈕", async () => {
      await openTeamPage(captain, retiring)
      await expect(teamHeaderBadge(captain, retiring.name)).toHaveText("已參賽")
      await captain
        .getByRole("button", { name: RETIRE_TEXT, exact: true })
        .click()
      const dialog = captain.getByRole("alertdialog", { name: RETIRE_TEXT })
      await expect(dialog).toBeVisible()
      await expect(dialog.getByText(RETIRE_DESCRIPTION)).toBeVisible()
      await expectNoHorizontalScroll(captain)
      await captain.screenshot({ path: testInfo.outputPath("s17-retire.png") })
      await dialog.getByRole("button", { name: "取消", exact: true }).click()
      await expect(dialog).toBeHidden()
      await expect(teamHeaderBadge(captain, retiring.name)).toHaveText("已參賽")
    })

    await test.step("確認退賽：Toast「已退賽」、徽章變「退賽」、按鈕消失", async () => {
      await captain
        .getByRole("button", { name: RETIRE_TEXT, exact: true })
        .click()
      const dialog = captain.getByRole("alertdialog", { name: RETIRE_TEXT })
      await dialog
        .getByRole("button", { name: RETIRE_TEXT, exact: true })
        .click()
      await expect(dialog).toBeHidden()
      await expect(captain.getByText("已退賽", { exact: true })).toBeVisible()
      await expect(teamHeaderBadge(captain, retiring.name)).toHaveText("退賽")
      await expect(
        captain.getByRole("button", { name: RETIRE_TEXT, exact: true }),
      ).toHaveCount(0)
      expect(await fetchRegistrationStatus(retiring)).toBe("retired")
      await expectNoHorizontalScroll(captain)
    })

    await test.step("候補遞補：S17 顯示「已參賽」，M1 的位置換成候補隊伍", async () => {
      expect(await fetchRegistrationStatus(backup)).toBe("drawn")
      const backupPage = await rolePage(
        newRoleContext,
        "遞補隊長",
        backup.captain.account,
      )
      await openTeamPage(backupPage, backup)
      await expect(teamHeaderBadge(backupPage, backup.name)).toHaveText(
        "已參賽",
      )
      const refreshed = await fetchBracket(tournamentId)
      const match = refreshed.matches.find((m) => m.code === "M1")
      expect(match?.team_a?.id).toBe(backup.id)
      expect(match?.team_b?.id).toBe(opponent.id)
    })

    await test.step("觀眾在 S3 對戰樹看到遞補隊名，退賽隊名消失", async () => {
      const spectator = await (await newRoleContext("觀眾")).newPage()
      await spectator.goto(`/tournaments/${tournamentId}/bracket`)
      await expect(bracketCardsOf(spectator, backup.name).first()).toBeVisible()
      await expect(bracketCardsOf(spectator, retiring.name)).toHaveCount(0)
      await expectNoHorizontalScroll(spectator)
    })
  },
)
