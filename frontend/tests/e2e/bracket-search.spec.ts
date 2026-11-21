// Story 4.7：S3 對戰樹的隊伍搜尋與晉級路徑。以 page.route 回傳 32 隊「進行中」的假對戰樹
// （support/match-api.ts），中興 Titan 第一輪 M1 已勝、第二輪 M17 進行中，第三輪 M25 A 方等它。
import { expect, test } from "./support/fixtures"
import {
  BRACKET_TREE_SELECTOR,
  expectNoHorizontalScroll,
  isNarrowViewport,
} from "./support/layout"
import {
  FIXTURE_TOURNAMENT_ID,
  mockFixtureTournament,
} from "./support/match-api"

const BRACKET_PATH = `/tournaments/${FIXTURE_TOURNAMENT_ID}/bracket`
const NOT_FOUND_TEXT =
  "對戰表上沒有符合的隊伍。候補、已撤回或被退回的隊伍不會出現在對戰表上。"

test.beforeEach(async ({ page }) => {
  await mockFixtureTournament(page)
})

test("觀眾搜尋隊名看到晉級路徑；捲動時搜尋列固定在頂端；找不到時顯示說明", {
  tag: ["@story-4.7", "@FR-35", "@NFR-6", "@NFR-7"],
}, async ({ page }) => {
  const tree = page.locator(BRACKET_TREE_SELECTOR)
  const search = page.getByRole("searchbox", { name: "搜尋隊名" })
  const count = page.locator("[data-slot=bracket-team-search-count]")
  const toolbar = page.locator("[data-slot=bracket-toolbar]")
  const heads = page.locator("[data-slot=bracket-round-heads-viewport]")

  await test.step("輸入部分隊名（大小寫不同）即篩選並高亮晉級路徑，網址不變", async () => {
    await page.goto(BRACKET_PATH)
    await expect(tree).toBeVisible()
    await search.pressSequentially("TITAN")

    await expect(count).toHaveText("找到 1 隊")
    await expect(tree.locator("[data-search-hit]")).toHaveCount(2)
    await expect(
      tree.locator('[data-match-id="match-M25"] [data-search-pending]'),
    ).toHaveText("M17 勝者")
    await expect(
      tree.locator("[data-slot=bracket-search-connectors]"),
    ).toHaveCount(1)
    expect(new URL(page.url()).pathname).toBe(BRACKET_PATH)
    expect(new URL(page.url()).search).toBe("")
    await expectNoHorizontalScroll(page)
    await page.screenshot({ path: test.info().outputPath("s3-search-hit.png") })
  })

  await test.step("搜尋框不在橫向捲動容器內；窄螢幕自動捲到該隊最遠的一輪", async () => {
    expect(await tree.locator("input").count()).toBe(0)
    if (isNarrowViewport(page)) {
      // 最遠是第二輪（16 強），容器會往右捲
      await expect
        .poll(() => tree.evaluate((element) => element.scrollLeft))
        .toBeGreaterThan(0)
      // 欄頭跟著對戰樹位移
      await expect(
        page.locator("[data-slot=bracket-round-heads]"),
      ).toHaveAttribute("style", /translateX\(-\d/)
    }
  })

  await test.step("往下捲動時搜尋列與輪次欄頭固定在視窗頂端，頂欄被蓋住", async () => {
    await page.evaluate(() => window.scrollTo(0, 900))
    await expect
      .poll(async () => (await toolbar.boundingBox())?.y)
      .toBeCloseTo(0, 0)
    const bar = await toolbar.boundingBox()
    const headsBox = await heads.boundingBox()
    expect(headsBox?.y).toBeCloseTo((bar?.y ?? 0) + (bar?.height ?? 0), 0)
    // 頂欄的位置被搜尋列蓋住，分頁列已捲走
    const covered = await page.evaluate(() => {
      const hit = document.elementFromPoint(window.innerWidth / 2, 20)
      return hit?.closest("[data-slot=bracket-toolbar]") !== null
    })
    expect(covered, "頂欄位置應被固定的搜尋列蓋住").toBe(true)
    // 搜尋列的底色延伸到視窗左右兩端：最上面一列像素，兩端要和中間（搜尋列底色）一樣，
    // 不能露出頂欄。box-shadow 不參與 elementFromPoint，所以直接比對截圖像素。
    const strip = await page.screenshot({
      clip: { x: 0, y: 0, width: page.viewportSize()?.width ?? 0, height: 4 },
    })
    const edges = await page.evaluate(async (base64) => {
      const image = new Image()
      image.src = `data:image/png;base64,${base64}`
      await image.decode()
      const canvas = document.createElement("canvas")
      canvas.width = image.width
      canvas.height = image.height
      const context = canvas.getContext("2d")!
      context.drawImage(image, 0, 0)
      const pixel = (x: number) =>
        [...context.getImageData(x, 1, 1, 1).data].join(",")
      return {
        left: pixel(1),
        center: pixel(Math.floor(image.width / 2)),
        right: pixel(image.width - 2),
      }
    }, strip.toString("base64"))
    expect(edges.left, "左側不應露出頂欄").toBe(edges.center)
    expect(edges.right, "右側不應露出頂欄").toBe(edges.center)
    await expect(page.getByRole("tablist")).not.toBeInViewport()

    // 左右捲動對戰樹：搜尋框不動
    const before = await search.boundingBox()
    await tree.evaluate((element) => {
      element.scrollLeft += 200
    })
    const after = await search.boundingBox()
    expect(after?.x).toBe(before?.x)
    await expectNoHorizontalScroll(page)
    await page.screenshot({
      path: test.info().outputPath("s3-search-sticky.png"),
    })
  })

  await test.step("零結果：「找到 0 隊」、說明文字、不清除輸入", async () => {
    await page.evaluate(() => window.scrollTo(0, 0))
    await search.fill("不存在的隊伍")

    await expect(count).toHaveText("找到 0 隊")
    await expect(page.getByText(NOT_FOUND_TEXT)).toBeVisible()
    await expect(search).toHaveValue("不存在的隊伍")
    await expect(tree.locator("[data-search-hit]")).toHaveCount(0)
    await expectNoHorizontalScroll(page)
    await page.screenshot({
      path: test.info().outputPath("s3-search-empty.png"),
    })
  })

  await test.step("清除：回到完整對戰樹", async () => {
    await page.getByRole("button", { name: "清除搜尋" }).click()
    await expect(search).toHaveValue("")
    await expect(search).toBeFocused()
    await expect(count).toHaveText("")
    await expect(page.getByText(NOT_FOUND_TEXT)).toHaveCount(0)
  })
})
