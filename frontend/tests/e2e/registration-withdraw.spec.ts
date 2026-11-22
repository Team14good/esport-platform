// Story 3.7：隊長在抽籤前於 S17 退賽（撤回報名），被遞補的候補隊伍在 S17、S12 看到「已遞補為正取」。
// 主辦方、遊戲、賽事與隊伍走公開 API 準備（support/withdraw.ts、support/bulk.ts），
// 優先期結束改資料庫後由真的 worker 結算；被測的退賽操作與畫面檢查都走瀏覽器。
import type { Page } from "@playwright/test"

import { uniqueSuffix } from "./support/accounts"
import {
  type BulkTeam,
  createRegisteredTeams,
  fetchRegistrationStatus,
} from "./support/bulk"
import { endPriorityWindow } from "./support/db"
import { rolePage } from "./support/drawn"
import { expect, test } from "./support/fixtures"
import { FICTIONAL_GAME, type GameConfig } from "./support/games"
import { expectNoHorizontalScroll } from "./support/layout"
import {
  apiSubmitRegistration,
  apiWithdrawRegistration,
  createOpenTournamentByApi,
} from "./support/withdraw"

const WITHDRAW_TEXT = "退賽"
const WITHDRAW_DESCRIPTION =
  "退賽後這支隊伍的報名會撤回，無法恢復。若隊伍是正取，名額會由候補遞補。"
const NOT_WITHDRAWABLE_MESSAGE = "這支隊伍的報名目前不能撤回。"
const BACKFILLED_LABEL = "已遞補為正取"

/** 每隊 3 人（先發 3、替補 0）的虛構遊戲，`teamCount` 隊 */
function gameWithTeams(teamCount: number): GameConfig {
  return { ...FICTIONAL_GAME, teamCount }
}

/** S17 標題列（隊名 h1 與報名狀態徽章） */
function teamHeaderBadge(page: Page, teamName: string) {
  return page
    .locator("header")
    .filter({
      has: page.getByRole("heading", { name: teamName, level: 1 }),
    })
    .locator("[data-slot=status-badge]")
}

/** S12 我的隊伍裡這支隊伍的卡片徽章 */
function myTeamCardBadge(page: Page, teamName: string) {
  return page
    .getByRole("link")
    .filter({ hasText: teamName })
    .locator("[data-slot=status-badge]")
}

async function openTeamPage(page: Page, team: BulkTeam) {
  await page.goto(`/teams/${team.id}`)
  await expect(
    page.getByRole("heading", { name: team.name, level: 1 }),
  ).toBeVisible()
}

async function openMyTeams(page: Page) {
  await page.goto("/me/teams")
  await expect(
    page.getByRole("heading", { name: "我的隊伍", level: 1 }),
  ).toBeVisible()
}

/** S17 按「退賽」，確認對話框的標題、內文與確認鈕；回傳對話框。 */
async function openWithdrawDialog(page: Page) {
  await page.getByRole("button", { name: WITHDRAW_TEXT, exact: true }).click()
  const dialog = page.getByRole("alertdialog", { name: WITHDRAW_TEXT })
  await expect(dialog).toBeVisible()
  await expect(dialog.getByText(WITHDRAW_DESCRIPTION)).toBeVisible()
  await expect(
    dialog.getByRole("button", { name: WITHDRAW_TEXT, exact: true }),
  ).toBeVisible()
  await expect(
    dialog.getByRole("button", { name: "取消", exact: true }),
  ).toBeVisible()
  await expectNoHorizontalScroll(page)
  return dialog
}

/** 開放報名、優先期內的賽事；第 2 隊起已送出（待分配），第 1 隊仍在組隊中。 */
async function setUpPendingTeams(teamCount: number, capacity: number) {
  const suffix = uniqueSuffix()
  const game = gameWithTeams(teamCount)
  const tournamentId = await createOpenTournamentByApi(game, suffix, capacity)
  const teams = await createRegisteredTeams(tournamentId, game, suffix)
  return { tournamentId, teams }
}

test(
  "隊長在 S17 退賽：確認對話框、徽章變「撤回」、按鈕消失，S12 卡片同步",
  {
    tag: ["@story-3.7", "@FR-9", "@NFR-7"],
  },
  async ({ newRoleContext }, testInfo) => {
    test.setTimeout(5 * 60_000)
    const { teams } = await setUpPendingTeams(2, 4)
    const team = teams[1]
    expect(await fetchRegistrationStatus(team)).toBe("pending")
    const captain = await rolePage(newRoleContext, "隊長", team.captain.account)

    await test.step("S12 卡片與 S17 徽章是「已送出・待分配」，S17 有「退賽」", async () => {
      await openMyTeams(captain)
      await expect(myTeamCardBadge(captain, team.name)).toHaveText(
        "已送出・待分配",
      )
      await openTeamPage(captain, team)
      await expect(teamHeaderBadge(captain, team.name)).toHaveText(
        "已送出・待分配",
      )
      await expect(
        captain.getByRole("button", { name: WITHDRAW_TEXT, exact: true }),
      ).toBeVisible()
      await expectNoHorizontalScroll(captain)
    })

    await test.step("按「退賽」開啟確認對話框，按「取消」不會撤回", async () => {
      const dialog = await openWithdrawDialog(captain)
      await captain.screenshot({
        path: testInfo.outputPath("s17-withdraw.png"),
      })
      await dialog.getByRole("button", { name: "取消", exact: true }).click()
      await expect(dialog).toBeHidden()
      await expect(teamHeaderBadge(captain, team.name)).toHaveText(
        "已送出・待分配",
      )
    })

    await test.step("確認退賽：Toast「已撤回報名」、徽章變「撤回」、「退賽」按鈕消失", async () => {
      const dialog = await openWithdrawDialog(captain)
      await dialog
        .getByRole("button", { name: WITHDRAW_TEXT, exact: true })
        .click()
      await expect(dialog).toBeHidden()
      await expect(
        captain.getByText("已撤回報名", { exact: true }),
      ).toBeVisible()
      await expect(teamHeaderBadge(captain, team.name)).toHaveText("撤回")
      await expect(
        captain.getByRole("button", { name: WITHDRAW_TEXT, exact: true }),
      ).toHaveCount(0)
      expect(await fetchRegistrationStatus(team)).toBe("withdrawn")
      await expectNoHorizontalScroll(captain)
    })

    await test.step("重新整理後仍是「撤回」，S12 卡片顯示「撤回」", async () => {
      await captain.reload()
      await expect(teamHeaderBadge(captain, team.name)).toHaveText("撤回")
      await expect(
        captain.getByRole("button", { name: WITHDRAW_TEXT, exact: true }),
      ).toHaveCount(0)
      await openMyTeams(captain)
      await expect(myTeamCardBadge(captain, team.name)).toHaveText("撤回")
      await expectNoHorizontalScroll(captain)
    })
  },
)

test("確認前報名已被撤回：對話框顯示「這支隊伍的報名目前不能撤回。」", {
  tag: ["@story-3.7", "@FR-9", "@NFR-7"],
}, async ({ newRoleContext }) => {
  test.setTimeout(5 * 60_000)
  const { teams } = await setUpPendingTeams(2, 4)
  const team = teams[1]
  const captain = await rolePage(newRoleContext, "隊長", team.captain.account)
  await openTeamPage(captain, team)

  const dialog = await openWithdrawDialog(captain)

  await test.step("對話框開著時，報名在後端被撤回（同一隊長在另一處先退賽）", async () => {
    await apiWithdrawRegistration(team)
    expect(await fetchRegistrationStatus(team)).toBe("withdrawn")
  })

  await test.step("按確認：對話框內顯示錯誤訊息，報名狀態跟上伺服器", async () => {
    const rejected = captain.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        response.url().endsWith(`/teams/${team.id}/withdrawal`),
    )
    // 被拒後畫面會重新取得隊伍（useWithdrawRegistration 的 onError）；等這次重新取得完成再檢查，
    // 確認錯誤訊息不會隨著「退賽」按鈕消失而一起不見
    const refetched = captain.waitForResponse(
      (response) =>
        response.request().method() === "GET" &&
        new URL(response.url()).pathname.endsWith(`/teams/${team.id}`),
    )
    await dialog
      .getByRole("button", { name: WITHDRAW_TEXT, exact: true })
      .click()
    expect((await rejected).status()).toBe(409)
    await refetched
    await expect(dialog.getByText(NOT_WITHDRAWABLE_MESSAGE)).toBeVisible()
    await expectNoHorizontalScroll(captain)
  })

  await test.step("關閉對話框後，徽章是「撤回」、「退賽」按鈕消失", async () => {
    // 對話框開著時背景為 aria-hidden，關閉後再檢查頁面
    await dialog.getByRole("button", { name: "取消", exact: true }).click()
    await expect(dialog).toBeHidden()
    await expect(teamHeaderBadge(captain, team.name)).toHaveText("撤回")
    await expect(
      captain.getByRole("button", { name: WITHDRAW_TEXT, exact: true }),
    ).toHaveCount(0)
  })
})

test("先搶期正取退賽：原本候補的隊伍在 S17、S12 看到「已遞補為正取」", {
  tag: ["@story-3.7", "@FR-9", "@FR-17", "@NFR-7"],
}, async ({ newRoleContext }) => {
  // 優先期結束後要等 worker 結算（輪詢最久約 90 秒）
  test.setTimeout(8 * 60_000)
  // 名額 2：第 2、3 隊（不同校）在優先期送出，結算後都是正取；
  // 第 1 隊的學校優先期沒有報名，在先搶期送出時名額已滿而成為候補
  const { tournamentId, teams } = await setUpPendingTeams(3, 2)
  const [backup, leaving, staying] = teams

  await test.step("優先期結束後 worker 結算，兩隊正取、名額已滿", async () => {
    await endPriorityWindow(tournamentId)
    for (const team of [leaving, staying]) {
      await expect
        .poll(() => fetchRegistrationStatus(team), {
          timeout: 90_000,
          intervals: [2_000],
        })
        .toBe("accepted")
    }
  })

  await test.step("第 1 隊在先搶期送出，成為候補", async () => {
    await apiSubmitRegistration(backup)
    expect(await fetchRegistrationStatus(backup)).toBe("waitlisted")
  })

  const backupPage = await rolePage(
    newRoleContext,
    "候補隊伍成員",
    backup.captain.account,
  )
  await test.step("候補隊伍在 S17 看到候補順位", async () => {
    await openTeamPage(backupPage, backup)
    await expect(teamHeaderBadge(backupPage, backup.name)).toHaveText(
      "候補第 1 位",
    )
  })

  const leavingPage = await rolePage(
    newRoleContext,
    "正取隊長",
    leaving.captain.account,
  )
  await test.step("正取隊長在 S17 退賽", async () => {
    await openTeamPage(leavingPage, leaving)
    await expect(teamHeaderBadge(leavingPage, leaving.name)).toHaveText("正取")
    const dialog = await openWithdrawDialog(leavingPage)
    await dialog
      .getByRole("button", { name: WITHDRAW_TEXT, exact: true })
      .click()
    await expect(dialog).toBeHidden()
    await expect(
      leavingPage.getByText("已撤回報名", { exact: true }),
    ).toBeVisible()
    await expect(teamHeaderBadge(leavingPage, leaving.name)).toHaveText("撤回")
    await openMyTeams(leavingPage)
    await expect(myTeamCardBadge(leavingPage, leaving.name)).toHaveText("撤回")
  })

  await test.step("候補隊伍遞補為正取：S17 與 S12 顯示「已遞補為正取」", async () => {
    expect(await fetchRegistrationStatus(backup)).toBe("accepted")
    await openTeamPage(backupPage, backup)
    await expect(teamHeaderBadge(backupPage, backup.name)).toHaveText(
      BACKFILLED_LABEL,
    )
    await expectNoHorizontalScroll(backupPage)
    await openMyTeams(backupPage)
    await expect(myTeamCardBadge(backupPage, backup.name)).toHaveText(
      BACKFILLED_LABEL,
    )
    await expectNoHorizontalScroll(backupPage)
  })

  await test.step("另一支正取隊伍仍是正取", async () => {
    expect(await fetchRegistrationStatus(staying)).toBe("accepted")
  })
})
