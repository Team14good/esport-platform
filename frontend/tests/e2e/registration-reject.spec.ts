// Story 3.8：主辦方在 S29 檢視段位截圖並退回正取，候補遞補；被退回的隊長在 S17 看到原因、
// 修正後重新送出。主辦方、遊戲、賽事與隊伍走公開 API 準備（support/withdraw.ts、
// support/bulk.ts），優先期結束改資料庫後由真的 worker 結算；被測的檢視、退回與重送走瀏覽器。
import type { Page } from "@playwright/test"

import { uniqueSuffix } from "./support/accounts"
import {
  type BulkTeam,
  createRegisteredTeams,
  fetchRegistrationStatus,
} from "./support/bulk"
import { endPriorityWindow } from "./support/db"
import { rolePage } from "./support/drawn"
import { expect, test } from "./support/fixtures"
import { FICTIONAL_GAME } from "./support/games"
import { expectNoHorizontalScroll } from "./support/layout"
import {
  apiSubmitRegistration,
  createOpenTournamentWithOrganizerByApi,
} from "./support/withdraw"

const REJECT_TEXT = "退回報名"
const REJECT_DESCRIPTION_OPEN =
  "退回後隊伍名單會解鎖，隊伍可在報名截止前修正後重新送出。若隊伍是正取，名額會由候補遞補。"
const REASON = "段位截圖與申報段位不符，請重新上傳"
const DEPARTED_REPRESENTATIVE = "本校代表隊已退出，由本校遞補"

/** S29 表格（桌機）或卡片清單（手機）裡這支隊伍的那一列／卡片 */
function registrationRow(page: Page, teamName: string) {
  return page
    .locator("[data-slot=data-table] tr, [data-slot=data-table-cards] li")
    .filter({ hasText: teamName })
    .filter({ visible: true })
}

/** S17 標題列（隊名 h1 與報名狀態徽章） */
function teamHeaderBadge(page: Page, teamName: string) {
  return page
    .locator("header")
    .filter({
      has: page.getByRole("heading", { name: teamName, level: 1 }),
    })
    .locator("[data-slot=status-badge]")
}

async function openTeamPage(page: Page, team: BulkTeam) {
  await page.goto(`/teams/${team.id}`)
  await expect(
    page.getByRole("heading", { name: team.name, level: 1 }),
  ).toBeVisible()
}

test(
  "主辦方在 S29 看段位截圖、退回正取，候補遞補；隊長看到原因並修正後重新送出",
  {
    tag: ["@story-3.8", "@FR-18", "@FR-17", "@FR-36", "@NFR-7"],
  },
  async ({ newRoleContext }, testInfo) => {
    // 優先期結束後要等 worker 結算（輪詢最久約 90 秒）
    test.setTimeout(8 * 60_000)
    const suffix = uniqueSuffix()
    const game = { ...FICTIONAL_GAME, teamCount: 3 }
    const { tournamentId, organizer } =
      await createOpenTournamentWithOrganizerByApi(game, suffix, 2)
    // 第 2、3 隊（不同校）在優先期送出，結算後都是正取；第 1 隊在先搶期送出時名額已滿而候補
    const [backup, rejected, staying] = await createRegisteredTeams(
      tournamentId,
      game,
      suffix,
    )

    await test.step("優先期結束後 worker 結算，兩隊正取；第 1 隊先搶期送出成為候補", async () => {
      await endPriorityWindow(tournamentId)
      for (const team of [rejected, staying]) {
        await expect
          .poll(() => fetchRegistrationStatus(team), {
            timeout: 90_000,
            intervals: [2_000],
          })
          .toBe("accepted")
      }
      await apiSubmitRegistration(backup)
      expect(await fetchRegistrationStatus(backup)).toBe("waitlisted")
    })

    const organizerPage = await rolePage(newRoleContext, "主辦方", organizer)

    await test.step("開 S29：列出三隊與分配結果", async () => {
      await organizerPage.goto(
        `/organizer/tournaments/${tournamentId}/registrations`,
      )
      await expect(
        organizerPage.getByRole("heading", { name: "報名清單", level: 1 }),
      ).toBeVisible()
      await expect(
        registrationRow(organizerPage, rejected.name).getByText("正取", {
          exact: true,
        }),
      ).toBeVisible()
      await expect(
        registrationRow(organizerPage, backup.name).getByText("候補第 1 位"),
      ).toBeVisible()
      await expectNoHorizontalScroll(organizerPage)
    })

    await test.step("段位截圖檢視器：第一位是隊長、經授權載入圖片，可翻到下一位", async () => {
      await registrationRow(organizerPage, rejected.name)
        .getByRole("button", { name: "段位截圖" })
        .click()
      const viewer = organizerPage.getByRole("dialog", {
        name: `${rejected.name}・段位截圖`,
      })
      await expect(viewer).toBeVisible()
      await expect(
        viewer.getByText(rejected.captain.account.displayName),
      ).toBeVisible()
      await expect(
        viewer.locator("[data-slot=rank-screenshot-image]"),
      ).toBeVisible()
      await expect(viewer.getByText(`1／${game.starters}`)).toBeVisible()
      await expect(
        viewer.getByRole("button", { name: "上一位" }),
      ).toBeDisabled()
      await viewer.getByRole("button", { name: "下一位" }).click()
      await expect(viewer.getByText(`2／${game.starters}`)).toBeVisible()
      await expect(
        viewer.locator("[data-slot=rank-screenshot-image]"),
      ).toBeVisible()
      await organizerPage.screenshot({
        path: testInfo.outputPath("s29-rank-screenshot-viewer.png"),
      })

      await test.step("按「退回報名」：先關閉檢視器再開確認對話框，原因必填", async () => {
        await viewer.getByRole("button", { name: REJECT_TEXT }).click()
        const dialog = organizerPage.getByRole("alertdialog", {
          name: REJECT_TEXT,
        })
        await expect(dialog).toBeVisible()
        await expect(viewer).toBeHidden()
        await expect(dialog.getByText(REJECT_DESCRIPTION_OPEN)).toBeVisible()
        const confirm = dialog.getByRole("button", { name: REJECT_TEXT })
        await expect(confirm).toBeDisabled()
        await dialog.getByLabel("退回原因").fill(REASON)
        await expectNoHorizontalScroll(organizerPage)
        await confirm.click()
        await expect(dialog).toBeHidden()
        await expect(
          organizerPage.getByText("已退回報名", { exact: true }),
        ).toBeVisible()
      })
    })

    await test.step("S29 更新：被退回的隊伍顯示「退回」與原因，候補遞補為正取", async () => {
      await expect(
        registrationRow(organizerPage, rejected.name).getByText("退回", {
          exact: true,
        }),
      ).toBeVisible()
      await expect(
        registrationRow(organizerPage, rejected.name).getByText(
          `退回原因：${REASON}`,
        ),
      ).toBeVisible()
      await expect(
        registrationRow(organizerPage, backup.name).getByText("已遞補為正取"),
      ).toBeVisible()
      expect(await fetchRegistrationStatus(rejected)).toBe("rejected")
      expect(await fetchRegistrationStatus(backup)).toBe("accepted")
      expect(await fetchRegistrationStatus(staying)).toBe("accepted")
    })

    const captainPage = await rolePage(
      newRoleContext,
      "被退回的隊長",
      rejected.captain.account,
    )

    await test.step("隊長在 S17 看到「退回」與原因，名單解鎖、可重新送出", async () => {
      await openTeamPage(captainPage, rejected)
      await expect(teamHeaderBadge(captainPage, rejected.name)).toHaveText(
        "退回",
      )
      await expect(captainPage.getByText(`退回原因：${REASON}`)).toBeVisible()
      await expect(
        captainPage.getByRole("button", { name: "送出報名" }),
      ).toBeEnabled()
      await expectNoHorizontalScroll(captainPage)
      await captainPage.screenshot({
        path: testInfo.outputPath("s17-rejected.png"),
      })
    })

    await test.step("修正後重新送出：先搶期當下判定，代表隊已退出的學校由本校遞補排第 1 位", async () => {
      await captainPage.getByRole("button", { name: "送出報名" }).click()
      const dialog = captainPage.getByRole("alertdialog", { name: "送出報名" })
      await dialog.getByRole("button", { name: "送出報名" }).click()
      await expect(dialog).toBeHidden()
      await expect(teamHeaderBadge(captainPage, rejected.name)).toHaveText(
        "候補第 1 位",
      )
      await expect(captainPage.getByText(DEPARTED_REPRESENTATIVE)).toBeVisible()
      await expect(captainPage.getByText(`退回原因：${REASON}`)).toHaveCount(0)
      expect(await fetchRegistrationStatus(rejected)).toBe("waitlisted")
      await expectNoHorizontalScroll(captainPage)
    })
  },
)
