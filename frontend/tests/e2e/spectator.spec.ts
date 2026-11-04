// UJ-4（期中版）：觀眾不登入瀏覽對戰樹與場次頁。
// 5.8 第二階段已把 S4 接上公開單場 API，並移除開發模式的假資料（tournament-fixture）；
// 目前還沒有已抽籤的真賽事可看，所以兩個測試都以 test.fixme 列出，
// 等 7.1 示範資料有已抽籤的賽事後，改成從那場賽事的 S3 進入再接上（見 deferred-work.md 7.2）。
import { identitySwitcher } from "./support/accounts"
import { expect, test } from "./support/fixtures"
import { expectNoHorizontalScroll } from "./support/layout"

/** 原本的開發模式假資料賽事 id；接上時改成示範資料已抽籤賽事的 id */
const FIXTURE_TOURNAMENT_ID = "tournament-fixture"
/** 打開的場次：第二輪（16 強）進行中的一場；接上時改成示範資料的場次 */
const MATCH_CODE = "M17"

test.fixme("未登入的觀眾開啟場次頁、換到同輪另一場，返回連結指向賽事的對戰表（等 7.1 示範資料的已抽籤賽事）", {
  tag: ["@story-5.8", "@story-7.2", "@FR-36", "@NFR-7"],
}, async ({ page }) => {
  await test.step("開啟場次頁", async () => {
    await page.goto(
      `/tournaments/${FIXTURE_TOURNAMENT_ID}/matches/match-${MATCH_CODE}`,
    )
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(
      `16 強 · ${MATCH_CODE}`,
    )
    // 未登入：頂欄沒有身分切換器
    await expect(identitySwitcher(page)).toHaveCount(0)
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
    await expect(back).toHaveAttribute(
      "href",
      `/tournaments/${FIXTURE_TOURNAMENT_ID}/bracket`,
    )
  })
})

test.fixme("未登入的觀眾在 S3 對戰表點場次卡進入場次頁，再回到對戰表（等 7.1 示範資料的已抽籤賽事）", {
  tag: [
    "@story-4.6",
    "@story-5.8",
    "@story-7.2",
    "@FR-5",
    "@FR-35",
    "@FR-36",
    "@NFR-2",
    "@NFR-7",
  ],
}, async () => {
  // 接上時：S2 點「對戰表」分頁，375 px 時對戰樹容器可左右捲動（BRACKET_TREE_SELECTOR），
  // 點場次卡進 S4，返回連結回到 S3
})
