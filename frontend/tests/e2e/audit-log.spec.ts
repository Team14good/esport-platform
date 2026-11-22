// Story 2.8：主辦方建立賽事後，在賽事後台側欄開啟 S34 操作紀錄，看到「建立賽事」那一筆。
import { logIn, platformAdmin, uniqueSuffix } from "./support/accounts"
import { addGame, createTournament } from "./support/drill"
import { expect, test } from "./support/fixtures"
import { VALORANT } from "./support/games"
import { expectNoHorizontalScroll } from "./support/layout"
import { createOrganizer } from "./support/organizer"

test(
  "主辦方在側欄開啟操作紀錄，看到自己建立賽事的紀錄且沒有編輯操作",
  {
    tag: ["@story-2.8", "@NFR-3", "@NFR-7"],
  },
  async ({ page, newRoleContext }, testInfo) => {
    // 主辦方的驗證信要等 worker 輪詢（預設每 20 秒）
    test.setTimeout(180_000)
    const suffix = uniqueSuffix()
    // 後端遊戲名稱不分大小寫唯一：加上本次執行的後綴，同一個資料庫可以重複執行
    const gameName = `${VALORANT.name} ${suffix}`
    const tournamentName = `E2E 操作紀錄盃 ${suffix}`
    const adminPage = await (await newRoleContext("平台管理員")).newPage()

    await logIn(adminPage, platformAdmin())
    await addGame(adminPage, VALORANT, gameName)
    const organizer = await createOrganizer(page, adminPage)
    const tournamentId = await createTournament(page, VALORANT, {
      gameName,
      tournamentName,
    })

    await test.step("從賽事後台側欄開啟「操作紀錄」", async () => {
      // < lg 側欄收進選單
      const menu = page.getByRole("button", {
        name: `開啟${tournamentName}選單`,
      })
      if (await menu.isVisible()) await menu.click()
      await page
        .getByRole("navigation", { name: tournamentName })
        .filter({ visible: true })
        .getByRole("link", { name: "操作紀錄" })
        .click()
      await expect(page).toHaveURL(
        `/organizer/tournaments/${tournamentId}/audit-log`,
      )
      await expect(
        page.getByRole("heading", { name: "操作紀錄", level: 1 }),
      ).toBeVisible()
    })

    await test.step("列出「建立賽事」，操作者為主辦方，唯讀", async () => {
      // 桌機是表格的一列，窄螢幕是卡片清單的一項；只取看得到的那一個
      const row = page
        .locator(
          "[data-slot=data-table] tbody tr, [data-slot=data-table-cards] > li",
        )
        .filter({ hasText: "建立賽事" })
        .filter({ visible: true })
      await expect(row).toHaveCount(1)
      await expect(row).toContainText(organizer.displayName)
      await expect(row).toContainText(`name：${tournamentName}`)
      const main = page.locator("section").filter({
        has: page.getByRole("heading", { name: "操作紀錄", level: 1 }),
      })
      await expect(
        main.getByRole("button", { name: /新增|修改|刪除|編輯/ }),
      ).toHaveCount(0)
      await expectNoHorizontalScroll(page)
      await page.screenshot({
        path: testInfo.outputPath("s34-audit-log.png"),
        fullPage: true,
      })
    })
  },
)
