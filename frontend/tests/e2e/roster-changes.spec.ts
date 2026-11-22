// Story 3.11：名單鎖定前，隊長在 S17 移除隊員、轉讓隊長，隊員退出，最後隊長解散隊伍。
// 主辦方、遊戲、賽事與隊伍走公開 API 準備（support/withdraw.ts、support/bulk.ts）；
// 被測的四個操作與畫面檢查都走瀏覽器（desktop 與 mobile-375 兩個 project 各跑一次）。
import type { Page } from "@playwright/test"

import { uniqueSuffix } from "./support/accounts"
import { createFormingTeamWithMembers, type FormingTeam } from "./support/bulk"
import { rolePage } from "./support/drawn"
import { expect, test } from "./support/fixtures"
import { FICTIONAL_GAME } from "./support/games"
import { expectNoHorizontalScroll } from "./support/layout"
import { createOpenTournamentByApi } from "./support/withdraw"

const DISBAND_TEXT = "解散隊伍"

function roster(page: Page) {
  return page.getByRole("list", { name: "隊伍名單" })
}

async function openTeamPage(page: Page, team: FormingTeam) {
  await page.goto(`/teams/${team.id}`)
  await expect(
    page.getByRole("heading", { name: team.name, level: 1 }),
  ).toBeVisible()
}

/** 開某位隊員那列的選單、點選項目，回傳確認對話框（已檢查標題與內文）。 */
async function chooseMemberAction(
  page: Page,
  memberName: string,
  item: string,
  description: string,
) {
  await page.getByRole("button", { name: `${memberName}的操作` }).click()
  await page.getByRole("menuitem", { name: item }).click()
  return expectDialog(page, item, description)
}

async function expectDialog(page: Page, title: string, description: string) {
  const dialog = page.getByRole("alertdialog", { name: title })
  await expect(dialog).toBeVisible()
  await expect(dialog.getByText(description)).toBeVisible()
  await expectNoHorizontalScroll(page)
  return dialog
}

async function confirm(page: Page, title: string) {
  const dialog = page.getByRole("alertdialog", { name: title })
  await dialog.getByRole("button", { name: title, exact: true }).click()
  await expect(dialog).toBeHidden()
}

test(
  "名單鎖定前：隊長移除隊員、轉讓隊長，隊員退出，隊長解散後原隊員看到唯讀頁",
  { tag: ["@story-3.11", "@FR-41", "@NFR-7"] },
  async ({ newRoleContext }, testInfo) => {
    test.setTimeout(5 * 60_000)
    const suffix = uniqueSuffix()
    const tournamentId = await createOpenTournamentByApi(
      FICTIONAL_GAME,
      suffix,
      4,
    )
    // FICTIONAL_GAME 先發 3、替補 0，一隊最多 3 人：3 人隊即為額滿
    const team = await createFormingTeamWithMembers(tournamentId, 3, suffix)
    const [a, b, c] = team.members
    const captainPage = await rolePage(newRoleContext, "隊長", a.account)

    await test.step("隊長在 S17 看到每列選單與「解散隊伍」；邀請連結因額滿失效", async () => {
      await openTeamPage(captainPage, team)
      await expect(captainPage.getByText("隊伍已滿")).toBeVisible()
      await expect(
        captainPage.getByRole("button", { name: DISBAND_TEXT, exact: true }),
      ).toBeVisible()
      await captainPage
        .getByRole("button", { name: `${a.account.displayName}的操作` })
        .click()
      const own = captainPage.getByRole("menuitem", {
        name: "先轉讓隊長才能退出",
      })
      await expect(own).toBeVisible()
      await expect(own).toHaveAttribute("aria-disabled", "true")
      await captainPage.keyboard.press("Escape")
      await expectNoHorizontalScroll(captainPage)
    })

    await test.step("移除隊員：Toast、名單少一人、邀請連結恢復有效", async () => {
      await chooseMemberAction(
        captainPage,
        b.account.displayName,
        "移除隊員",
        `${b.account.displayName}會離開隊伍，參賽資料一併刪除；之後仍可經邀請連結重新加入。`,
      )
      await captainPage.screenshot({
        path: testInfo.outputPath("s17-remove-member.png"),
      })
      await confirm(captainPage, "移除隊員")
      await expect(
        captainPage.getByText("已移除隊員", { exact: true }),
      ).toBeVisible()
      await expect(
        roster(captainPage).getByText(b.account.displayName),
      ).toHaveCount(0)
      await expect(captainPage.getByText("隊伍已滿")).toHaveCount(0)
    })

    await test.step("轉讓隊長：自己成為一般隊員，「解散隊伍」消失", async () => {
      await chooseMemberAction(
        captainPage,
        c.account.displayName,
        "轉讓隊長",
        `轉讓後${c.account.displayName}成為隊長，你會成為一般隊員，不能再送出報名或管理隊員。`,
      )
      await confirm(captainPage, "轉讓隊長")
      await expect(
        captainPage.getByText("已轉讓隊長", { exact: true }),
      ).toBeVisible()
      await expect(
        captainPage.getByRole("button", { name: DISBAND_TEXT, exact: true }),
      ).toHaveCount(0)
      await expect(
        captainPage.getByRole("button", {
          name: `${c.account.displayName}的操作`,
        }),
      ).toHaveCount(0)
    })

    await test.step("原隊長退出隊伍：導向我的隊伍、Toast", async () => {
      await chooseMemberAction(
        captainPage,
        a.account.displayName,
        "退出隊伍",
        "退出後你的參賽資料會一併刪除，之後可以加入這場賽事的其他隊伍。",
      )
      await confirm(captainPage, "退出隊伍")
      await expect(captainPage).toHaveURL(/\/me\/teams$/)
      await expect(
        captainPage.getByText("已退出隊伍", { exact: true }),
      ).toBeVisible()
      await expect(
        captainPage.getByRole("link").filter({ hasText: team.name }),
      ).toHaveCount(0)
    })

    const newCaptainPage = await rolePage(newRoleContext, "新隊長", c.account)
    await test.step("新隊長解散隊伍：導向我的隊伍，卡片顯示「撤回」", async () => {
      await openTeamPage(newCaptainPage, team)
      await newCaptainPage
        .getByRole("button", { name: DISBAND_TEXT, exact: true })
        .click()
      await expectDialog(
        newCaptainPage,
        DISBAND_TEXT,
        "解散後所有隊員都會離開隊伍、報名改為撤回，邀請連結失效，無法復原。",
      )
      await confirm(newCaptainPage, DISBAND_TEXT)
      await expect(newCaptainPage).toHaveURL(/\/me\/teams$/)
      await expect(
        newCaptainPage.getByText("已解散隊伍", { exact: true }),
      ).toBeVisible()
      await expect(
        newCaptainPage
          .getByRole("link")
          .filter({ hasText: team.name })
          .locator("[data-slot=status-badge]"),
      ).toHaveText("撤回")
      await expectNoHorizontalScroll(newCaptainPage)
    })

    await test.step("解散後的 S17 唯讀頁：說明與原隊員，沒有任何操作", async () => {
      await openTeamPage(newCaptainPage, team)
      await expect(
        newCaptainPage.getByText("這支隊伍已由隊長解散。"),
      ).toBeVisible()
      await expect(
        roster(newCaptainPage).getByText(c.account.displayName),
      ).toBeVisible()
      await expect(
        newCaptainPage.getByRole("heading", { name: "邀請隊友" }),
      ).toHaveCount(0)
      await expect(
        newCaptainPage.getByRole("button", { name: /的操作$/ }),
      ).toHaveCount(0)
      await expect(
        newCaptainPage.getByRole("button", { name: DISBAND_TEXT, exact: true }),
      ).toHaveCount(0)
      await newCaptainPage.screenshot({
        path: testInfo.outputPath("s17-disbanded.png"),
      })
      await expectNoHorizontalScroll(newCaptainPage)
    })

    await test.step("S19：原邀請連結顯示「連結已失效：隊伍已解散。」", async () => {
      await newCaptainPage.goto(`/join/${team.inviteToken}`)
      await expect(
        newCaptainPage.getByText("連結已失效：隊伍已解散。"),
      ).toBeVisible()
    })
  },
)
