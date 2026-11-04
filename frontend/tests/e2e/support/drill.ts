// 完整賽事演練的共用步驟（Story 2.1、2.2、2.4、3.1、3.2 的畫面）。
// 每一步只讀 GameConfig 的設定，不依遊戲名稱寫分支；名稱一律由呼叫端加上本次執行的後綴。
import { expect, type Page } from "@playwright/test"

import type { GameConfig, ScoreType } from "./games"
import { expectNoHorizontalScroll } from "./layout"

/** S36 比分型態下拉的選項文字（features/tournaments/admin-games.ts 的 SCORE_TYPE_LABELS） */
const SCORE_TYPE_OPTIONS: Record<ScoreType, string> = {
  win_loss: "只記勝負",
  rounds: "記回合比分",
}

/** S26 建立賽事時，棄權時限與申訴期使用表單的預設值（分鐘） */
const DEFAULT_FORFEIT_MINUTES = 15
const DEFAULT_APPEAL_MINUTES = 30

const HOUR_MS = 3_600_000
const DAY_MS = 24 * HOUR_MS
const TAIPEI_OFFSET_MS = 8 * HOUR_MS

/** 現在加上 `offsetMs` 的台北時間，格式是 `datetime-local` 的 `YYYY-MM-DDTHH:mm`。 */
export function taipeiDateTimeLocal(offsetMs: number): string {
  return new Date(Date.now() + offsetMs + TAIPEI_OFFSET_MS)
    .toISOString()
    .slice(0, 16)
}

/** 每輪間隔的下限：棄權時限＋BO × 每局預估時間＋申訴期（與 S26 的提示相同）。 */
export function minRoundIntervalMinutes(game: GameConfig): number {
  return (
    DEFAULT_FORFEIT_MINUTES +
    game.defaultBestOf * game.minutesPerGame +
    DEFAULT_APPEAL_MINUTES
  )
}

/** Radix Select：點開 combobox 後選擇選項，並確認 combobox 顯示選到的值。 */
async function pickOption(page: Page, combobox: string, option: string) {
  const trigger = page.getByRole("combobox", { name: combobox, exact: true })
  await trigger.click()
  await page.getByRole("option", { name: option, exact: true }).click()
  await expect(trigger).toHaveText(option)
}

/**
 * S36 平台管理員依 GameConfig 新增遊戲（名稱用 `gameName`），成功後回到列表，
 * 並在列表（每頁 20 筆，依名稱排序）找到這款遊戲。
 */
export async function addGame(page: Page, game: GameConfig, gameName: string) {
  await page.goto("/admin/games/new")
  await expect(
    page.getByRole("heading", { name: "新增遊戲", level: 1 }),
  ).toBeVisible()
  await page.getByLabel("遊戲名稱", { exact: true }).fill(gameName)
  await page.getByLabel("先發人數", { exact: true }).fill(String(game.starters))
  await page
    .getByLabel("替補人數", { exact: true })
    .fill(String(game.substitutes))
  await pickOption(page, "預設 BO 數", `BO${game.defaultBestOf}`)
  await page
    .getByLabel("每局預估時間（分鐘）", { exact: true })
    .fill(String(game.minutesPerGame))
  await pickOption(page, "比分型態", SCORE_TYPE_OPTIONS[game.scoreType])
  // 表單一開始有一列空白段位，其餘每筆先按「新增段位」
  for (const [index, rank] of game.ranks.entries()) {
    if (index > 0) await page.getByRole("button", { name: "新增段位" }).click()
    await page
      .getByLabel(`第 ${index + 1} 筆段位名稱`, { exact: true })
      .fill(rank.name)
    await page
      .getByLabel(`第 ${index + 1} 筆積分`, { exact: true })
      .fill(String(rank.points))
  }
  await expectNoHorizontalScroll(page)
  await page.getByRole("button", { name: "新增遊戲", exact: true }).click()
  await expect(page.getByText("已新增遊戲", { exact: true })).toBeVisible()
  await expect(page).toHaveURL(/\/admin\/games$/)

  // 列表在前端分頁：找不到就按「下一頁」，直到最後一頁
  const link = page
    .getByRole("link", { name: gameName, exact: true })
    .filter({ visible: true })
  await expect(
    page.getByRole("heading", { name: "遊戲設定", level: 1 }),
  ).toBeVisible()
  // 等列表載入（表格或卡片清單出現）
  await expect(
    page
      .locator("[data-slot=data-table], [data-slot=data-table-cards]")
      .filter({ visible: true }),
  ).toBeVisible()
  for (let current = 1; ; current += 1) {
    if ((await link.count()) > 0) break
    const next = page.getByRole("button", { name: "下一頁" })
    if ((await next.count()) === 0 || (await next.isDisabled())) {
      throw new Error(`遊戲列表裡找不到「${gameName}」`)
    }
    // 用鍵盤按：開發模式的 TanStack Query 開發工具按鈕固定在右下角，會擋住滑鼠點擊
    await next.press("Enter")
    // 等換到下一頁再找（「第 n／N 頁」只在窄螢幕顯示，但一直在 DOM 裡）
    await expect(
      page.getByText(new RegExp(`^第 ${current + 1}／[0-9]+ 頁$`)),
    ).toHaveCount(1)
  }
  await expect(link).toBeVisible()
  await expectNoHorizontalScroll(page)
}

/**
 * S26 主辦方以 `gameName` 建立賽事（報名開始＝現在前 1 小時，所以建立後就是「開放報名」），
 * 確認先發、替補、BO 自動帶入遊戲預設值；建立後停在 S27，回傳賽事 id。
 */
export async function createTournament(
  page: Page,
  game: GameConfig,
  options: { gameName: string; tournamentName: string },
): Promise<string> {
  await page.goto("/organizer/tournaments/new")
  await expect(
    page.getByRole("heading", { name: "建立賽事", level: 1 }),
  ).toBeVisible()
  await page
    .getByLabel("賽事名稱", { exact: true })
    .fill(options.tournamentName)
  await pickOption(page, "遊戲", options.gameName)
  // 選遊戲後自動帶入該遊戲的預設值（FR-7）
  await expect(page.getByLabel("先發人數", { exact: true })).toHaveValue(
    String(game.starters),
  )
  await expect(page.getByLabel("替補人數", { exact: true })).toHaveValue(
    String(game.substitutes),
  )
  await expect(
    page.getByRole("combobox", { name: "BO", exact: true }),
  ).toHaveText(`BO${game.defaultBestOf}`)
  await page.getByLabel("名額", { exact: true }).fill(String(game.teamCount))
  await page
    .getByLabel("報名開始", { exact: true })
    .fill(taipeiDateTimeLocal(-HOUR_MS))
  await page
    .getByLabel("報名截止", { exact: true })
    .fill(taipeiDateTimeLocal(7 * DAY_MS))
  await page
    .getByLabel("開賽時間", { exact: true })
    .fill(taipeiDateTimeLocal(8 * DAY_MS))
  const minimum = minRoundIntervalMinutes(game)
  await expect(
    page.getByText(`目前的最小間隔：${minimum} 分鐘`, { exact: false }),
  ).toBeVisible()
  await page
    .getByLabel("每輪間隔（分鐘）", { exact: true })
    .fill(String(minimum))
  await expectNoHorizontalScroll(page)
  await page.getByRole("button", { name: "建立賽事", exact: true }).click()

  await expect(page).toHaveURL(/\/organizer\/tournaments\/[^/]+$/)
  const heading = page.getByRole("heading", {
    name: options.tournamentName,
    level: 1,
  })
  await expect(heading).toBeVisible()
  // S27 標題列的狀態徽章與建立時的設定
  await expect(
    page.locator("header").filter({ has: heading }).getByText("開放報名"),
  ).toBeVisible()
  await expect(
    page.getByText(`先發 ${game.starters} 人／替補 ${game.substitutes} 人`, {
      exact: true,
    }),
  ).toBeVisible()
  await expect(
    page.getByText(`BO${game.defaultBestOf}`, { exact: true }),
  ).toBeVisible()
  await expectNoHorizontalScroll(page)
  const id = new URL(page.url()).pathname.split("/").pop()
  if (!id) throw new Error(`無法從 ${page.url()} 取得賽事 id`)
  return id
}

/** S1→S2 未登入的觀眾在「開放報名」分組找到這場賽事，點進賽事頁。 */
export async function browseOpenTournament(
  page: Page,
  tournamentName: string,
  tournamentId: string,
) {
  await page.goto("/")
  await expect(
    page.getByRole("heading", { name: "賽事", level: 1 }),
  ).toBeVisible()
  const card = page
    .locator('section[aria-label="開放報名"]')
    .getByRole("link", { name: tournamentName })
  await expect(card).toBeVisible()
  await expectNoHorizontalScroll(page)
  await card.click()
  await expect(page).toHaveURL(new RegExp(`/tournaments/${tournamentId}$`))
  await expect(
    page.getByRole("heading", { name: tournamentName, level: 1 }),
  ).toBeVisible()
  await expectNoHorizontalScroll(page)
}

/** S2 隊長建立隊伍，停在 S17，回傳隊伍邀請連結（`…/join/{token}`）。 */
export async function createTeam(
  page: Page,
  tournamentId: string,
  teamName: string,
): Promise<string> {
  await page.goto(`/tournaments/${tournamentId}`)
  await page.getByRole("button", { name: "建立隊伍", exact: true }).click()
  const dialog = page.getByRole("dialog", { name: "建立隊伍" })
  await expect(dialog).toBeVisible()
  await dialog.getByLabel("隊名", { exact: true }).fill(teamName)
  await dialog.getByRole("button", { name: "建立隊伍", exact: true }).click()
  await expect(page).toHaveURL(/\/teams\/[^/]+$/)
  await expect(
    page.getByRole("heading", { name: teamName, level: 1 }),
  ).toBeVisible()
  await expectNoHorizontalScroll(page)
  const inviteUrl = await page
    .getByLabel("隊伍邀請連結", { exact: true })
    .inputValue()
  expect(inviteUrl).toMatch(/\/join\/[^/]+$/)
  return inviteUrl
}

/** S19 已登入的帳號打開邀請連結並加入隊伍，停在 S17。 */
export async function joinTeam(
  page: Page,
  inviteUrl: string,
  teamName: string,
) {
  await page.goto(inviteUrl)
  await expect(
    page.getByRole("heading", { name: "加入隊伍", level: 1 }),
  ).toBeVisible()
  await expect(page.getByText(teamName, { exact: true })).toBeVisible()
  await expectNoHorizontalScroll(page)
  await page.getByRole("button", { name: "加入隊伍", exact: true }).click()
  await expect(page).toHaveURL(/\/teams\/[^/]+$/)
  await expect(
    page.getByRole("heading", { name: teamName, level: 1 }),
  ).toBeVisible()
}

/** 1×1 的 PNG（檔頭是 PNG 的 magic bytes，後端會檢查） */
const TINY_PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
  "base64",
)

/** S17→S18 在自己那列「填寫我的資料」：遊戲 ID、段位、段位截圖，儲存後那列顯示「資料完成」。 */
export async function fillPlayerProfile(
  page: Page,
  profile: { displayName: string; gameAccountId: string; rankName: string },
) {
  await page.getByRole("button", { name: "填寫我的資料", exact: true }).click()
  // 桌機是 Dialog、窄螢幕是 Sheet，兩者都是 dialog role
  const dialog = page.getByRole("dialog", { name: "我的參賽資料" })
  await expect(dialog).toBeVisible()
  await dialog
    .getByLabel("遊戲 ID", { exact: true })
    .fill(profile.gameAccountId)
  await dialog.getByRole("combobox", { name: "段位", exact: true }).click()
  await page
    .getByRole("option", { name: profile.rankName, exact: true })
    .click()
  await expect(
    dialog.getByRole("combobox", { name: "段位", exact: true }),
  ).toHaveText(profile.rankName)
  await dialog.getByLabel("段位截圖", { exact: true }).setInputFiles({
    name: "rank.png",
    mimeType: "image/png",
    buffer: TINY_PNG,
  })
  await expect(dialog.getByText("rank.png", { exact: true })).toBeVisible()
  await expectNoHorizontalScroll(page)
  await dialog.getByRole("button", { name: "儲存資料", exact: true }).click()
  await expect(dialog).toBeHidden()
  const myRow = page
    .locator('ul[aria-label="隊伍名單"] > li')
    .filter({ hasText: profile.displayName })
  await expect(myRow.getByText("資料完成", { exact: true })).toBeVisible()
  await expect(myRow).toContainText(profile.gameAccountId)
  await expect(myRow).toContainText(profile.rankName)
}

/**
 * 名單下方應顯示的平均段位積分文字（全員已填）：與後端相同，四捨五入取到小數第二位。
 * 積分都是整數，`sum × 100 ÷ n` 剛好是 .5 時可以精確表示，`Math.round` 即為四捨五入。
 */
export function expectedAveragePoints(points: number[]): string {
  const sum = points.reduce((total, value) => total + value, 0)
  const cents = Math.round((sum * 100) / points.length)
  return `平均段位積分 ${(cents / 100).toFixed(2)}`
}
