// UJ-4（期中版）：觀眾不登入瀏覽對戰樹與場次頁。
// 4.6 第二階段已接上真的 S3 並刪除 /dev/bracket，但還沒有已抽籤的真賽事可看，單場 API（#21）也還沒合併：
// 場次頁先直接開開發模式的假資料（tournament-fixture，32 隊「進行中」）；
// 從 S3 點場次卡進入的步驟以 test.fixme 列出，等示範資料有已抽籤的賽事、5.8 第二階段接上單場 API 後再接上。
import { identitySwitcher } from "./support/accounts"
import { expect, test } from "./support/fixtures"
import { expectNoHorizontalScroll } from "./support/layout"

/** 假資料的賽事 id（frontend/src/features/competition/match-source.ts） */
const FIXTURE_TOURNAMENT_ID = "tournament-fixture"
/** 打開的場次：第二輪（16 強）進行中的一場；假資料的場次 id 是「match-<代碼>」 */
const MATCH_CODE = "M17"

test("未登入的觀眾開啟場次頁、換到同輪另一場，返回連結指向賽事的對戰表", {
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

test.fixme("未登入的觀眾在 S3 對戰表點場次卡進入場次頁，再回到對戰表（等示範資料的已抽籤賽事與 #21）", {
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
