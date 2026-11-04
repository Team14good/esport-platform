// UJ-4（期中版）：觀眾不登入瀏覽對戰樹與場次頁。
// 示範資料（7.1）還沒有已抽籤的賽事，公開的賽事、對戰樹、單場 API 先以 page.route 回傳假對戰樹
// （support/match-api.ts，32 隊「進行中」）；7.1 有資料後補一份走真 API 的版本（見 deferred-work.md）。
import { identitySwitcher } from "./support/accounts"
import { expect, test } from "./support/fixtures"
import {
  BRACKET_TREE_SELECTOR,
  expectNoHorizontalScroll,
  isNarrowViewport,
} from "./support/layout"
import {
  FIXTURE_TOURNAMENT_ID,
  fixtureMatchId,
  mockFixtureTournament,
} from "./support/match-api"

/** 打開的場次：第二輪（16 強）進行中的一場 */
const MATCH_CODE = "M17"
const BRACKET_PATH = `/tournaments/${FIXTURE_TOURNAMENT_ID}/bracket`

test.beforeEach(async ({ page }) => {
  await mockFixtureTournament(page)
})

test("未登入的觀眾開啟場次頁、換到同輪另一場，返回連結指向賽事的對戰表", {
  tag: ["@story-5.8", "@story-7.2", "@FR-36", "@NFR-7"],
}, async ({ page }) => {
  await test.step("開啟場次頁", async () => {
    await page.goto(
      `/tournaments/${FIXTURE_TOURNAMENT_ID}/matches/${fixtureMatchId(MATCH_CODE)}`,
    )
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(
      `16 強 · ${MATCH_CODE}`,
    )
    // 未登入：頂欄沒有身分切換器，也沒有報到按鈕
    await expect(identitySwitcher(page)).toHaveCount(0)
    await expect(page.getByRole("button", { name: "報到" })).toHaveCount(0)
    await expectNoHorizontalScroll(page)
  })

  await test.step("從同輪其他場次換到另一場", async () => {
    const sameRound = page.locator("[data-slot=same-round-matches]")
    const link = sameRound.locator("[data-slot=same-round-link]").first()
    // 連結文字是「場次代碼＋狀態徽章」，例如「M18申訴期」
    const otherCode = (await link.textContent())?.match(/M\d+/)?.[0]
    expect(otherCode, "同輪其他場次的連結應有場次代碼").toBeTruthy()
    await link.click()
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(
      `16 強 · ${otherCode}`,
    )
    await expectNoHorizontalScroll(page)
  })

  await test.step("返回連結指向賽事的對戰表", async () => {
    const back = page.locator("[data-slot=match-back-link]")
    await expect(back).toBeVisible()
    await expect(back).toHaveAttribute("href", BRACKET_PATH)
  })
})

test("未登入的觀眾在 S3 對戰表點場次卡進入場次頁，再回到對戰表", {
  tag: ["@story-4.6", "@story-5.8", "@story-7.2", "@FR-35", "@FR-36", "@NFR-7"],
}, async ({ page }) => {
  const tree = page.locator(BRACKET_TREE_SELECTOR)

  await test.step("開啟 S3 對戰表", async () => {
    await page.goto(BRACKET_PATH)
    await expect(tree).toBeVisible()
    await expectNoHorizontalScroll(page)
    if (isNarrowViewport(page)) {
      // 375 px：32 隊的對戰樹比視窗寬，只有對戰樹容器可以左右捲動
      const scrollable = await tree.evaluate(
        (element) => element.scrollWidth > element.clientWidth,
      )
      expect(scrollable, "窄螢幕時對戰樹容器應可左右捲動").toBe(true)
    }
  })

  await test.step("點場次卡進入 S4", async () => {
    const card = tree.locator(
      `a[href="/tournaments/${FIXTURE_TOURNAMENT_ID}/matches/${fixtureMatchId(MATCH_CODE)}"]`,
    )
    await card.scrollIntoViewIfNeeded()
    await card.click()
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(
      `16 強 · ${MATCH_CODE}`,
    )
    await expectNoHorizontalScroll(page)
  })

  await test.step("返回連結回到 S3", async () => {
    await page.locator("[data-slot=match-back-link]").click()
    await expect(page).toHaveURL(new RegExp(`${BRACKET_PATH}$`))
    await expect(tree).toBeVisible()
  })
})
