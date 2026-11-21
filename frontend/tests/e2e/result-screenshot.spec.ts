// Story 5.7：勝隊隊長在 S4 上傳結算截圖，未登入的觀眾在同一頁看到縮圖並放大。
// 走真 API：建立並抽籤一場 8 隊賽事（support/drawn.ts），第一輪一場由主辦方代為登錄並送出結果
// （兩隊報到與比分走公開 API），之後的上傳、更換與檢視都走畫面。
import type { Page } from "@playwright/test"

import {
  apiLogin,
  fetchBracket,
  findTeam,
  playableMatches,
  playMatchByApi,
  teamsOf,
} from "./support/bulk"
import { openCheckIn } from "./support/db"
import { rolePage, setUpDrawnTournament } from "./support/drawn"
import { expect, test } from "./support/fixtures"
import { FICTIONAL_GAME } from "./support/games"
import { expectNoHorizontalScroll } from "./support/layout"

/** 2×1 的 PNG（紅、藍各一格）與 1×1 的 PNG：檔頭是 PNG 的 magic bytes，瀏覽器也能解碼 */
const FIRST_PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAIAAAABCAYAAAD0In+KAAAADklEQVR4nGP4z8AAQv8BD/kD/YURmXYAAAAASUVORK5CYII=",
  "base64",
)
const SECOND_PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
  "base64",
)

const card = (page: Page) => page.locator("[data-slot=result-screenshot]")
const thumbnail = (page: Page) =>
  card(page).getByRole("button", { name: "放大結算截圖" })

/** 縮圖已解碼成功，回傳圖片的原始寬度 */
async function loadedImageWidth(page: Page): Promise<number> {
  const image = thumbnail(page).getByRole("img")
  await expect
    .poll(() => image.evaluate((el: HTMLImageElement) => el.naturalWidth))
    .toBeGreaterThan(0)
  return image.evaluate((el: HTMLImageElement) => el.naturalWidth)
}

test("勝隊隊長上傳並更換結算截圖，未登入的觀眾在場次頁看到縮圖並放大", {
  tag: ["@story-5.7", "@FR-28", "@FR-36", "@NFR-7"],
}, async ({ newRoleContext }) => {
  // 建立賽事、8 隊報名並等 worker 分配（優先期結束後的輪詢最久約 90 秒）
  test.setTimeout(15 * 60_000)
  const { tournamentId, teams, organizer } = await setUpDrawnTournament(
    FICTIONAL_GAME,
    newRoleContext,
  )
  const match = playableMatches(await fetchBracket(tournamentId), 1)[0]
  const { teamA, teamB } = teamsOf(match)
  const matchUrl = `/tournaments/${tournamentId}/matches/${match.id}`
  const spectator = await (await newRoleContext("觀眾")).newPage()

  await test.step("系列結果送出前，場次頁沒有結算截圖區塊", async () => {
    await spectator.goto(matchUrl)
    await expect(spectator.getByRole("heading", { level: 1 })).toContainText(
      match.code,
    )
    await expect(card(spectator)).toHaveCount(0)
  })

  await test.step("兩隊報到，主辦方代為登錄並送出系列結果（A 隊獲勝）", async () => {
    await openCheckIn([match.id])
    await playMatchByApi({
      tournamentId,
      game: FICTIONAL_GAME,
      match,
      teams,
      scorerToken: await apiLogin(organizer),
      winner: "a",
    })
  })

  await test.step("觀眾（輪詢）看到區塊與「勝隊尚未上傳結算截圖」，沒有上傳區", async () => {
    await expect(card(spectator)).toBeVisible({ timeout: 15_000 })
    await expect(
      card(spectator).getByRole("heading", { name: "結算截圖" }),
    ).toBeVisible()
    await expect(
      card(spectator).getByText("勝隊尚未上傳結算截圖", { exact: true }),
    ).toBeVisible()
    await expect(card(spectator).locator("input[type=file]")).toHaveCount(0)
    await expectNoHorizontalScroll(spectator)
  })

  await test.step("敗隊隊長看得到區塊，但沒有上傳區", async () => {
    const loser = await rolePage(
      newRoleContext,
      "敗隊隊長",
      findTeam(teams, teamB.id).captain.account,
    )
    // 等「能否上傳」的回應回來並確認是 false，之後的「沒有上傳區」才不是因為還沒載入
    const stateResponse = loser.waitForResponse(
      (response) =>
        response.url().endsWith("/result-screenshot-state") &&
        response.request().method() === "GET",
    )
    await loser.goto(matchUrl)
    await expect(
      card(loser).getByText("勝隊尚未上傳結算截圖", { exact: true }),
    ).toBeVisible()
    expect(await (await stateResponse).json()).toEqual({
      can_upload: false,
      reason: "not_winning_captain",
    })
    // 兩隊隊長都有「提出申訴」：確認這一頁是以隊長身分載入的
    await expect(
      loser.getByRole("button", { name: "提出申訴", exact: true }),
    ).toBeVisible()
    await expect(card(loser).locator("input[type=file]")).toHaveCount(0)
    await expect(
      card(loser).getByRole("button", { name: "選擇圖片", exact: true }),
    ).toHaveCount(0)
    await loser.close()
  })

  const winner = await rolePage(
    newRoleContext,
    "勝隊隊長",
    findTeam(teams, teamA.id).captain.account,
  )

  await test.step("勝隊隊長選檔、預覽後按「上傳截圖」", async () => {
    await winner.goto(matchUrl)
    await expect(
      card(winner).getByRole("button", { name: "選擇圖片", exact: true }),
    ).toBeVisible()
    await expectNoHorizontalScroll(winner)
    await card(winner).locator("input[type=file]").setInputFiles({
      name: "result.png",
      mimeType: "image/png",
      buffer: FIRST_PNG,
    })
    await expect(
      card(winner).getByText("result.png", { exact: true }),
    ).toBeVisible()
    await expectNoHorizontalScroll(winner)
    await card(winner)
      .getByRole("button", { name: "上傳截圖", exact: true })
      .click()
    await expect(
      winner.getByText("結算截圖已上傳。", { exact: true }),
    ).toBeVisible()
    await expect(thumbnail(winner)).toBeVisible()
    expect(await loadedImageWidth(winner)).toBe(2)
    await expectNoHorizontalScroll(winner)
  })

  await test.step("觀眾不重新整理，10 秒內看到縮圖（最大寬 320px），點擊放大", async () => {
    await expect(thumbnail(spectator)).toBeVisible({ timeout: 10_000 })
    expect(await loadedImageWidth(spectator)).toBe(2)
    const box = await thumbnail(spectator).boundingBox()
    expect(box?.width ?? 0).toBeLessThanOrEqual(320)
    await expect(
      card(spectator).getByText("勝隊尚未上傳結算截圖", { exact: true }),
    ).toHaveCount(0)
    await expectNoHorizontalScroll(spectator)

    await thumbnail(spectator).click()
    const dialog = spectator.getByRole("dialog", { name: "結算截圖" })
    await expect(dialog).toBeVisible()
    await expect(dialog.getByRole("img", { name: "結算截圖" })).toBeVisible()
    await expectNoHorizontalScroll(spectator)
    await spectator.keyboard.press("Escape")
    await expect(dialog).toBeHidden()
  })

  await test.step("勝隊隊長更換截圖，觀眾看到新的圖", async () => {
    await card(winner).locator("input[type=file]").setInputFiles({
      name: "result-2.png",
      mimeType: "image/png",
      buffer: SECOND_PNG,
    })
    await card(winner)
      .getByRole("button", { name: "更換截圖", exact: true })
      .click()
    await expect
      .poll(() => loadedImageWidth(winner), { timeout: 10_000 })
      .toBe(1)
    await expect
      .poll(() => loadedImageWidth(spectator), { timeout: 15_000 })
      .toBe(1)
  })
})
