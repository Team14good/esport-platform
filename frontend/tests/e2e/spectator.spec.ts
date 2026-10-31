// UJ-4（期中版）：觀眾不登入瀏覽對戰樹與場次頁。
// 公開對戰樹（S3）與單場 API 還沒合併，先用開發模式的假資料頁 /dev/bracket（32 隊「進行中」）；
// 4.6 第二階段接上 S3 後，改從真正的賽事頁進入。
import { identitySwitcher } from "./support/accounts"
import { expect, test } from "./support/fixtures"
import {
  BRACKET_TREE_SELECTOR,
  expectNoHorizontalScroll,
  isNarrowViewport,
} from "./support/layout"

/** 假資料的賽事 id（frontend/src/features/competition/match-source.ts） */
const FIXTURE_TOURNAMENT_ID = "tournament-fixture"
/** 點進去的場次：第二輪（16 強）進行中的一場 */
const MATCH_CODE = "M17"

test("未登入的觀眾從對戰樹點場次卡進入場次頁，再回到賽事", {
  tag: [
    "@story-4.6",
    "@story-5.8",
    "@FR-5",
    "@FR-35",
    "@FR-36",
    "@NFR-2",
    "@NFR-7",
  ],
}, async ({ page }) => {
  await test.step("開啟對戰樹", async () => {
    await page.goto("/dev/bracket")
    await expect(
      page.getByRole("heading", { name: "對戰樹預覽", level: 1 }),
    ).toBeVisible()
    // 未登入：頂欄沒有身分切換器
    await expect(identitySwitcher(page)).toHaveCount(0)
    const tree = page.locator(BRACKET_TREE_SELECTOR)
    // 32 隊：31 場淘汰賽＋季軍賽
    await expect(tree.locator("[data-slot=bracket-match-card]")).toHaveCount(32)
    await expectNoHorizontalScroll(page)
    if (isNarrowViewport(page)) {
      // 手機上對戰樹放不下，要能在容器內左右捲動
      const scrollable = await tree.evaluate(
        (element) => element.scrollWidth > element.clientWidth,
      )
      expect(scrollable, "375 px 時對戰樹應可左右捲動").toBe(true)
    }
  })

  await test.step("點場次卡進入場次頁", async () => {
    await page
      .locator(BRACKET_TREE_SELECTOR)
      .locator("a[data-slot=bracket-match-link]")
      .filter({
        has: page.getByRole("article", { name: MATCH_CODE, exact: true }),
      })
      .click()
    await expect(page).toHaveURL(
      new RegExp(`/tournaments/${FIXTURE_TOURNAMENT_ID}/matches/[^/]+$`),
    )
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(
      `16 強 · ${MATCH_CODE}`,
    )
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
    // S3 路由在 4.6 第二階段才建立，這裡只確認連結回到同一個賽事
    const back = page.locator("[data-slot=match-back-link]")
    await expect(back).toBeVisible()
    await expect(back).toHaveAttribute(
      "href",
      `/tournaments/${FIXTURE_TOURNAMENT_ID}/bracket`,
    )
  })
})
