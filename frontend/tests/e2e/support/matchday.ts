// 賽事進行階段走畫面的共用步驟（裁判邀請、抽籤、報到、登錄比分、申訴、檢舉、頒獎台）。
// 每一步只讀 GameConfig 的設定，不依遊戲名稱寫分支。
import { expect, type Locator, type Page } from "@playwright/test"

import type { GameConfig } from "./games"
import { winsNeeded } from "./games"
import { expectNoHorizontalScroll } from "./layout"

/** DataTable 同時渲染表格與窄螢幕卡片，只取看得到的那個 */
const visible = (locator: Locator) => locator.filter({ visible: true })

const matchPath = (tournamentId: string, matchId: string) =>
  `/tournaments/${tournamentId}/matches/${matchId}`

/** S31 產生裁判邀請連結並回傳。 */
export async function createRefereeInvite(
  page: Page,
  tournamentId: string,
): Promise<string> {
  await page.goto(`/organizer/tournaments/${tournamentId}/referees`)
  await page.getByRole("button", { name: "產生邀請連結", exact: true }).click()
  const field = page.getByLabel("裁判邀請連結", { exact: true })
  await expect(field).toHaveValue(/\/referee-invite\//)
  await expectNoHorizontalScroll(page)
  return field.inputValue()
}

/** S23 已登入的帳號接受裁判邀請。 */
export async function acceptRefereeInvite(
  page: Page,
  inviteUrl: string,
  tournamentName: string,
) {
  await page.goto(inviteUrl)
  await page.getByRole("button", { name: "接受邀請", exact: true }).click()
  await expect(
    page.getByText(`你已成為「${tournamentName}」的裁判`),
  ).toBeVisible()
  await expectNoHorizontalScroll(page)
}

/** S17 隊長送出報名，名單鎖定。 */
export async function submitRegistration(page: Page, teamId: string) {
  await page.goto(`/teams/${teamId}`)
  await page.getByRole("button", { name: "送出報名", exact: true }).click()
  const dialog = page.getByRole("alertdialog", { name: "送出報名" })
  await dialog.getByRole("button", { name: "送出報名", exact: true }).click()
  await expect(page.getByText("已送出報名", { exact: true })).toBeVisible()
  await expect(page.getByText("已送出・待分配").first()).toBeVisible()
  await expect(page.getByText("連結已失效：名單已鎖定")).toBeVisible()
  await expectNoHorizontalScroll(page)
}

/** S17 隊長看到 worker 分配後的「正取」。 */
export async function expectRegistrationAccepted(page: Page, teamId: string) {
  await page.goto(`/teams/${teamId}`)
  await expect(page.getByText("正取", { exact: true }).first()).toBeVisible()
  await expectNoHorizontalScroll(page)
}

/** S27 主辦方抽籤；抽籤後按鈕區塊消失。 */
export async function drawBracket(page: Page, tournamentId: string) {
  await page.goto(`/organizer/tournaments/${tournamentId}`)
  const section = page.locator('section[aria-label="抽籤"]')
  await section.getByRole("button", { name: "抽籤", exact: true }).click()
  const dialog = page.getByRole("alertdialog", { name: "抽籤" })
  await dialog.getByRole("button", { name: "抽籤", exact: true }).click()
  await expect(section).toHaveCount(0)
  await expectNoHorizontalScroll(page)
}

/** S30 主辦方把裁判指派到場次（場次在第一頁）。 */
export async function assignRefereeOnPage(
  page: Page,
  tournamentId: string,
  matchCode: string,
  refereeName: string,
) {
  await page.goto(`/organizer/tournaments/${tournamentId}/matches`)
  const select = visible(
    page.getByRole("combobox", { name: `${matchCode}的裁判`, exact: true }),
  )
  await select.click()
  await page.getByRole("option", { name: refereeName, exact: true }).click()
  await expect(select).toHaveText(refereeName)
  await expectNoHorizontalScroll(page)
}

/** S13 裁判看到被指派的場次。 */
export async function expectRefereeSeesMatch(page: Page, matchCode: string) {
  await page.goto("/me/referee")
  await expect(
    visible(page.getByText(matchCode, { exact: true })).first(),
  ).toBeVisible()
  await expectNoHorizontalScroll(page)
}

/** S4 隊長為本隊報到。 */
export async function checkInOnPage(
  page: Page,
  tournamentId: string,
  matchId: string,
  teamName: string,
) {
  await page.goto(matchPath(tournamentId, matchId))
  await page.getByRole("button", { name: "報到", exact: true }).click()
  // 只看本隊那一格：對手先報到時，頁面上已經有對手的「已報到」
  const ownTeam = page
    .getByRole("listitem")
    .filter({ has: page.getByText(teamName, { exact: true }) })
  await expect(ownTeam.getByText(/^已報到/)).toBeVisible()
  await expectNoHorizontalScroll(page)
}

/** S4 裁判逐局登錄（勝方都是 A 隊），分出勝負後送出系列結果。 */
export async function scoreMatchOnPage(
  page: Page,
  tournamentId: string,
  matchId: string,
  game: GameConfig,
  teamA: string,
  teamB: string,
) {
  await page.goto(matchPath(tournamentId, matchId))
  await expect(page.getByText("可開始", { exact: true })).toBeVisible({
    timeout: 15_000,
  })
  const target = winsNeeded(game.defaultBestOf)
  for (let gameNo = 1; gameNo <= target; gameNo += 1) {
    const addGame = page.getByRole("button", { name: "新增一局", exact: true })
    const firstField = game.sampleGameScore
      ? page.getByLabel(`第 ${gameNo} 局 ${teamA} 分數`, { exact: true })
      : page.getByRole("row", { name: new RegExp(`第 ${gameNo} 局`) })
    // 表格一開始可能已有一列可編輯的新局；沒有時才按「新增一局」
    if ((await firstField.count()) === 0) await addGame.click()
    if (game.sampleGameScore) {
      await page
        .getByLabel(`第 ${gameNo} 局 ${teamA} 分數`, { exact: true })
        .fill(String(game.sampleGameScore.winner))
      await page
        .getByLabel(`第 ${gameNo} 局 ${teamB} 分數`, { exact: true })
        .fill(String(game.sampleGameScore.loser))
    } else {
      await page
        .getByRole("row", { name: new RegExp(`第 ${gameNo} 局`) })
        .getByRole("button", { name: teamA, exact: true })
        .click()
    }
    await page.getByRole("button", { name: "登錄", exact: true }).click()
    await expect(
      page.getByRole("button", { name: "登錄", exact: true }),
    ).toHaveCount(0)
  }
  await expectNoHorizontalScroll(page)
  await page.getByRole("button", { name: "送出系列結果", exact: true }).click()
  await page
    .getByRole("alertdialog", { name: "送出系列結果" })
    .getByRole("button", { name: "送出系列結果", exact: true })
    .click()
  await expect(
    page.getByRole("button", { name: "送出系列結果", exact: true }),
  ).toHaveCount(0)
}

/** S4→S21 隊長提出申訴。 */
export async function fileAppeal(
  page: Page,
  tournamentId: string,
  matchId: string,
) {
  await page.goto(matchPath(tournamentId, matchId))
  await page.getByRole("button", { name: "提出申訴", exact: true }).click()
  const dialog = page.getByRole("dialog", { name: "提出申訴" })
  await dialog
    .getByLabel("申訴說明", { exact: true })
    .fill("比分登錄錯誤，請主辦方查證。")
  await expectNoHorizontalScroll(page)
  await dialog.getByRole("button", { name: "送出申訴", exact: true }).click()
  await expect(page.getByText("申訴已送出。", { exact: true })).toBeVisible()
}

/** S32 主辦方更正結果，勝隊改為 B 隊（各局都改成 B 隊贏）。 */
export async function correctAppealToTeamB(
  page: Page,
  tournamentId: string,
  game: GameConfig,
  teamA: string,
  teamB: string,
) {
  await page.goto(`/organizer/tournaments/${tournamentId}/appeals`)
  await visible(
    page.getByRole("button", { name: "更正結果", exact: true }),
  ).click()
  const dialog = page.getByRole("alertdialog", { name: "更正結果" })
  for (let gameNo = 1; gameNo <= winsNeeded(game.defaultBestOf); gameNo += 1) {
    if (game.sampleGameScore) {
      await dialog
        .getByLabel(`第 ${gameNo} 局 ${teamA} 回合數`, { exact: true })
        .fill(String(game.sampleGameScore.loser))
      await dialog
        .getByLabel(`第 ${gameNo} 局 ${teamB} 回合數`, { exact: true })
        .fill(String(game.sampleGameScore.winner))
    } else {
      await dialog
        .getByRole("button", {
          name: `第 ${gameNo} 局 ${teamB} 勝`,
          exact: true,
        })
        .click()
    }
  }
  await dialog
    .getByLabel("處理理由", { exact: true })
    .fill("查證後比分登錄有誤。")
  await dialog.getByRole("button", { name: "更正結果", exact: true }).click()
  await expect(page.getByText("已處理申訴。", { exact: true })).toBeVisible()
  await expectNoHorizontalScroll(page)
}

/** S2 隊長檢舉另一隊。 */
export async function reportTeam(
  page: Page,
  tournamentId: string,
  reportedTeam: string,
) {
  await page.goto(`/tournaments/${tournamentId}`)
  await page.getByRole("button", { name: "檢舉隊伍", exact: true }).click()
  const dialog = page.getByRole("dialog", { name: "提出檢舉" })
  await dialog.getByRole("combobox", { name: "檢舉對象", exact: true }).click()
  await page.getByRole("option", { name: reportedTeam, exact: true }).click()
  await dialog.getByLabel("說明", { exact: true }).fill("對方使用外掛。")
  await expectNoHorizontalScroll(page)
  await dialog.getByRole("button", { name: "送出檢舉", exact: true }).click()
  await expect(page.getByText("已送出檢舉", { exact: true })).toBeVisible()
}

/** S33 主辦方判定檢舉屬實、取消資格。 */
export async function disqualifyReportedTeam(
  page: Page,
  tournamentId: string,
  teamName: string,
) {
  await page.goto(`/organizer/tournaments/${tournamentId}/reports`)
  await visible(
    page.getByRole("button", { name: "取消資格", exact: true }),
  ).click()
  const dialog = page.getByRole("alertdialog", {
    name: `取消 ${teamName} 的資格`,
  })
  await dialog.getByLabel("處理理由", { exact: true }).fill("查證屬實。")
  await dialog.getByRole("button", { name: "取消資格", exact: true }).click()
  await expect(page.getByText("已處理檢舉。", { exact: true })).toBeVisible()
  await expectNoHorizontalScroll(page)
}

/** S3 對戰樹上帶有這支隊伍的場次卡。 */
export function bracketCardsOf(page: Page, teamName: string) {
  return page
    .locator("article[data-slot=bracket-match-card]")
    .filter({ hasText: teamName })
}

/** S3 頒獎台顯示冠亞季軍，賽事狀態為已結束。 */
export async function expectPodium(
  page: Page,
  tournamentId: string,
  names: { champion: string; runnerUp: string; thirdPlace: string },
) {
  await page.goto(`/tournaments/${tournamentId}/bracket`)
  const podium = page.locator("[data-slot=podium]")
  await expect(podium).toBeVisible()
  for (const name of Object.values(names)) {
    await expect(podium).toContainText(name)
  }
  await expect(page.getByText("已結束", { exact: true }).first()).toBeVisible()
  await expectNoHorizontalScroll(page)
}
