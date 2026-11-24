// Story 3.10 第 2 部分：自訂賽事的賽事報名連結。
// 主辦方在 S26 建立自訂賽事、在 S27 複製連結；隊長經連結建隊、隊友經隊伍邀請連結加入；
// 沒有連結的帳號看到提示；主辦方重設後舊連結失效；未登入開連結先登入再回到原網址。
// 主辦方、遊戲與一般帳號走公開 API 準備（support/withdraw.ts），被測的操作都走瀏覽器。
import type { Page } from "@playwright/test"

import { logIn, type TestAccount, uniqueSuffix } from "./support/accounts"
import { rolePage } from "./support/drawn"
import { minRoundIntervalMinutes, taipeiDateTimeLocal } from "./support/drill"
import { expect, test } from "./support/fixtures"
import { FICTIONAL_GAME } from "./support/games"
import { expectNoHorizontalScroll } from "./support/layout"
import {
  createOrganizerAndGameByApi,
  createVerifiedAccountsByApi,
} from "./support/withdraw"

const HOUR_MS = 3_600_000
const DAY_MS = 24 * HOUR_MS

const LINK_LABEL = "賽事報名連結"
const LINK_DESCRIPTION = "持有這個連結的帳號才能建立隊伍。"
const RESET_TEXT = "重設報名連結"
const RESET_CONFIRM = "重設後舊連結立即失效，已建立的隊伍不受影響。"
const RESET_DONE = "已重設報名連結"
const INVITE_ONLY = "邀請制報名"
const NO_LINK = "這是邀請制賽事，請向主辦方索取報名連結。"
const EXPIRED_LINK = "報名連結已失效，請向主辦方索取新的連結。"
const SIGN_IN_FIRST = "登入後即可建立隊伍。"
const CREATE_TEAM = "建立隊伍"

/** Radix Select：點開 combobox 後選擇選項，並確認 combobox 顯示選到的值。 */
async function pickOption(page: Page, combobox: string, option: string) {
  const trigger = page.getByRole("combobox", { name: combobox, exact: true })
  await trigger.click()
  await page.getByRole("option", { name: option, exact: true }).click()
  await expect(trigger).toHaveText(option)
}

/** S26 建立自訂賽事（報名開始＝現在前 1 小時，建立後就是「開放報名」）；回傳賽事 id。 */
async function createCustomTournament(
  page: Page,
  options: { gameName: string; tournamentName: string },
): Promise<string> {
  const game = FICTIONAL_GAME
  await page.goto("/organizer/tournaments/new")
  await expect(
    page.getByRole("heading", { name: "建立賽事", level: 1 }),
  ).toBeVisible()
  await page
    .getByLabel("賽事名稱", { exact: true })
    .fill(options.tournamentName)
  await pickOption(page, "遊戲", options.gameName)
  await expect(page.getByLabel("優先期（小時）", { exact: true })).toBeVisible()
  // 選「自訂」後優先期欄位消失（自訂賽事沒有優先期）
  await pickOption(page, "賽事模式", "自訂")
  await expect(page.getByLabel("優先期（小時）", { exact: true })).toHaveCount(
    0,
  )
  await page.getByLabel("名額", { exact: true }).fill("4")
  await page
    .getByLabel("報名開始", { exact: true })
    .fill(taipeiDateTimeLocal(-HOUR_MS))
  await page
    .getByLabel("報名截止", { exact: true })
    .fill(taipeiDateTimeLocal(7 * DAY_MS))
  await page
    .getByLabel("開賽時間", { exact: true })
    .fill(taipeiDateTimeLocal(8 * DAY_MS))
  await page
    .getByLabel("每輪間隔（分鐘）", { exact: true })
    .fill(String(minRoundIntervalMinutes(game)))
  await expectNoHorizontalScroll(page)
  await page.getByRole("button", { name: "建立賽事", exact: true }).click()

  await expect(page).toHaveURL(/\/organizer\/tournaments\/[^/]+$/)
  await expect(
    page.getByRole("heading", { name: options.tournamentName, level: 1 }),
  ).toBeVisible()
  const id = new URL(page.url()).pathname.split("/").pop()
  if (!id) throw new Error(`無法從 ${page.url()} 取得賽事 id`)
  return id
}

/** S27 的賽事報名連結輸入框（唯讀）。 */
function linkField(page: Page) {
  return page.getByRole("textbox", { name: LINK_LABEL, exact: true })
}

/** 站內路徑（含 `?invite=`），讓各角色的頁面以 baseURL 開啟。 */
function pathOf(url: string) {
  const parsed = new URL(url)
  return `${parsed.pathname}${parsed.search}`
}

async function openTournament(page: Page, path: string, name: string) {
  await page.goto(path)
  await expect(page.getByRole("heading", { name, level: 1 })).toBeVisible()
}

test(
  "自訂賽事：主辦方建立並分享賽事報名連結，持連結者建隊，重設後舊連結失效",
  {
    tag: ["@story-3.10", "@FR-39", "@FR-11", "@NFR-7"],
  },
  async ({ page, newRoleContext }, testInfo) => {
    test.setTimeout(5 * 60_000)
    const suffix = uniqueSuffix()
    const tournamentName = `E2E 自訂賽 ${suffix}`
    const teamName = `邀請隊 ${suffix.slice(-6)}`
    const { organizer, gameName } = await createOrganizerAndGameByApi(
      FICTIONAL_GAME,
      suffix,
    )
    const [captainAccount, mateAccount, outsiderAccount] =
      await createVerifiedAccountsByApi("custom", 3)

    // 主辦方複製連結要用剪貼簿
    const organizerContext = await newRoleContext("主辦方")
    await organizerContext.grantPermissions([
      "clipboard-read",
      "clipboard-write",
    ])
    const organizerPage = await organizerContext.newPage()
    await logIn(organizerPage, organizer)

    let tournamentId = ""
    let firstLink = ""
    await test.step("主辦方在 S26 選「自訂」建立賽事，S27 顯示賽事報名連結", async () => {
      tournamentId = await createCustomTournament(organizerPage, {
        gameName,
        tournamentName,
      })
      await expect(linkField(organizerPage)).toBeVisible()
      await expect(organizerPage.getByText(LINK_DESCRIPTION)).toBeVisible()
      firstLink = await linkField(organizerPage).inputValue()
      expect(firstLink).toContain(`/tournaments/${tournamentId}?invite=`)
      await organizerPage
        .getByRole("button", { name: "複製連結", exact: true })
        .click()
      await expect(
        organizerPage.getByText("已複製", { exact: true }),
      ).toBeVisible()
      const copied = await organizerPage.evaluate(() =>
        navigator.clipboard.readText(),
      )
      expect(copied).toBe(firstLink)
      await expectNoHorizontalScroll(organizerPage)
      await organizerPage.screenshot({
        path: testInfo.outputPath("s27-registration-link.png"),
      })
    })

    await test.step("S1 卡片標「邀請制報名」", async () => {
      await page.goto("/")
      const card = page.getByRole("link").filter({ hasText: tournamentName })
      await expect(card.getByText(INVITE_ONLY, { exact: true })).toBeVisible()
      await expectNoHorizontalScroll(page)
    })

    let teamInviteUrl = ""
    await test.step("隊長經賽事報名連結看到「建立隊伍」並建隊", async () => {
      const captain = await rolePage(newRoleContext, "隊長", captainAccount)
      await openTournament(captain, pathOf(firstLink), tournamentName)
      await captain
        .getByRole("button", { name: CREATE_TEAM, exact: true })
        .click()
      const dialog = captain.getByRole("dialog", { name: CREATE_TEAM })
      await dialog.getByLabel("隊名", { exact: true }).fill(teamName)
      await dialog
        .getByRole("button", { name: CREATE_TEAM, exact: true })
        .click()
      await expect(
        captain.getByRole("heading", { name: teamName, level: 1 }),
      ).toBeVisible()
      teamInviteUrl = await captain
        .getByRole("textbox", { name: "隊伍邀請連結", exact: true })
        .inputValue()
      await expectNoHorizontalScroll(captain)
    })

    await test.step("隊友經隊伍邀請連結加入，不需要賽事報名連結", async () => {
      const mate = await rolePage(newRoleContext, "隊友", mateAccount)
      await mate.goto(pathOf(teamInviteUrl))
      await mate.getByRole("button", { name: "加入隊伍", exact: true }).click()
      await expect(
        mate.getByRole("heading", { name: teamName, level: 1 }),
      ).toBeVisible()
      await expectNoHorizontalScroll(mate)
    })

    const outsider = await rolePage(
      newRoleContext,
      "沒有連結的帳號",
      outsiderAccount,
    )
    await test.step("沒有連結的帳號開 S2：顯示索取連結的提示，沒有「建立隊伍」", async () => {
      await openTournament(
        outsider,
        `/tournaments/${tournamentId}`,
        tournamentName,
      )
      await expect(outsider.getByText(NO_LINK)).toBeVisible()
      await expect(
        outsider.getByRole("button", { name: CREATE_TEAM, exact: true }),
      ).toHaveCount(0)
      await expectNoHorizontalScroll(outsider)
    })

    let newLink = ""
    await test.step("主辦方重設報名連結：確認框、Toast、連結換新", async () => {
      await organizerPage
        .getByRole("button", { name: RESET_TEXT, exact: true })
        .click()
      const dialog = organizerPage.getByRole("alertdialog", {
        name: RESET_TEXT,
      })
      await expect(dialog.getByText(RESET_CONFIRM)).toBeVisible()
      await expectNoHorizontalScroll(organizerPage)
      await dialog
        .getByRole("button", { name: RESET_TEXT, exact: true })
        .click()
      await expect(dialog).toBeHidden()
      await expect(
        organizerPage.getByText(RESET_DONE, { exact: true }),
      ).toBeVisible()
      await expect(linkField(organizerPage)).not.toHaveValue(firstLink)
      newLink = await linkField(organizerPage).inputValue()
      expect(newLink).toContain(`/tournaments/${tournamentId}?invite=`)
    })

    await test.step("舊連結失效：顯示「報名連結已失效」，沒有「建立隊伍」", async () => {
      await openTournament(outsider, pathOf(firstLink), tournamentName)
      await expect(outsider.getByText(EXPIRED_LINK)).toBeVisible()
      await expect(
        outsider.getByRole("button", { name: CREATE_TEAM, exact: true }),
      ).toHaveCount(0)
      await expectNoHorizontalScroll(outsider)
    })

    await test.step("未登入開新連結：先登入，再回到同一個網址並顯示「建立隊伍」", async () => {
      const guest = await (await newRoleContext("訪客")).newPage()
      const path = pathOf(newLink)
      await openTournament(guest, path, tournamentName)
      await expect(guest.getByText(SIGN_IN_FIRST)).toBeVisible()
      await expectNoHorizontalScroll(guest)
      // 頂欄也有「登入」；點總覽裡帶 redirect 的那一個
      await guest
        .getByRole("tabpanel", { name: "總覽" })
        .getByRole("link", { name: "登入", exact: true })
        .click()
      await expect(
        guest.getByRole("heading", { name: "登入", level: 1 }),
      ).toBeVisible()
      await signInOnCurrentPage(guest, outsiderAccount)
      await expect(guest).toHaveURL(
        (url) => `${url.pathname}${url.search}` === path,
      )
      await expect(
        guest.getByRole("button", { name: CREATE_TEAM, exact: true }),
      ).toBeVisible()
      await expectNoHorizontalScroll(guest)
    })
  },
)

/** 在目前的 S6（保留網址上的 redirect）填入帳密登入。 */
async function signInOnCurrentPage(page: Page, account: TestAccount) {
  await page.getByLabel("Email", { exact: true }).fill(account.email)
  await page.getByLabel("密碼", { exact: true }).fill(account.password)
  await page.getByRole("button", { name: "登入", exact: true }).click()
}
