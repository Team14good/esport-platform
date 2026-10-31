// UJ-1 前半：訪客註冊、從 Mailpit 取信驗證、登入、申請主辦方，平台管理員核准後成為主辦方。
// 申請人與平台管理員各用一個 browser context（各自的登入狀態）。
import type { Page } from "@playwright/test"

import {
  identitySwitcher,
  logIn,
  newTestAccount,
  platformAdmin,
  signUp,
  uniqueSuffix,
  verifyEmail,
} from "./support/accounts"
import { expect, test } from "./support/fixtures"
import { expectNoHorizontalScroll } from "./support/layout"

const SCHOOL = "國立政治大學"

/** S35 找到這個 Email 的待審核申請並核准；申請依送出時間由舊到新排，可能在後面的頁。 */
async function approveApplication(page: Page, applicantEmail: string) {
  await page.goto("/admin/applications")
  await expect(
    page.getByRole("heading", { name: "主辦方申請", level: 1 }),
  ).toBeVisible()
  // 桌機是表格的一列，窄螢幕是卡片清單的一項；只取看得到的那一個
  const row = page
    .locator(
      "[data-slot=data-table] tbody tr, [data-slot=data-table-cards] > li",
    )
    .filter({ hasText: applicantEmail })
    .filter({ visible: true })
  for (;;) {
    await expect(page.locator("[aria-busy=true]")).toHaveCount(0)
    if ((await row.count()) > 0) break
    const next = page.getByRole("button", { name: "下一頁" })
    if (!(await next.isVisible()) || (await next.isDisabled())) {
      throw new Error(`待審核清單裡找不到 ${applicantEmail} 的主辦方申請`)
    }
    await next.click()
  }
  await expectNoHorizontalScroll(page)
  await row.getByRole("button", { name: "核准", exact: true }).click()
  const dialog = page.getByRole("alertdialog", { name: "核准主辦方申請" })
  await expect(dialog).toBeVisible()
  await dialog.getByRole("button", { name: "核准", exact: true }).click()
  await expect(dialog).toBeHidden()
  // 核准後這筆不再是待審核
  await expect(row).toHaveCount(0)
}

test("訪客註冊並驗證 Email、申請主辦方，平台管理員核准後可進入主辦方後台", {
  tag: [
    "@story-1.3",
    "@story-1.4",
    "@story-1.7",
    "@story-1.8",
    "@FR-1",
    "@FR-2",
    "@FR-3",
    "@FR-5",
    "@NFR-2",
    "@NFR-7",
  ],
}, async ({ newRoleContext }) => {
  // 驗證信由 worker 輪詢寄出（預設每 20 秒），最多等 60 秒
  test.setTimeout(180_000)
  const applicant = newTestAccount("organizer")
  const clubName = `E2E 電競社 ${uniqueSuffix()}`
  const applicantPage = await (await newRoleContext("申請人")).newPage()

  await test.step("訪客註冊帳號", async () => {
    await signUp(applicantPage, applicant, { school: SCHOOL })
  })

  await test.step("從 Mailpit 取得驗證信並完成驗證", async () => {
    await verifyEmail(applicantPage, applicant)
  })

  await test.step("登入", async () => {
    await logIn(applicantPage, applicant)
  })

  await test.step("申請成為主辦方", async () => {
    await applicantPage.goto("/organizer/apply")
    await expect(
      applicantPage.getByRole("heading", { name: "申請成為主辦方", level: 1 }),
    ).toBeVisible()
    await expectNoHorizontalScroll(applicantPage)
    await applicantPage.getByLabel("社團名稱", { exact: true }).fill(clubName)
    // 學校預設帶入帳號的學校
    await expect(
      applicantPage.getByRole("combobox", { name: "學校", exact: true }),
    ).toHaveText(SCHOOL)
    await applicantPage.getByRole("button", { name: "送出申請" }).click()
    await expect(
      applicantPage.getByRole("heading", { name: "主辦方申請", level: 1 }),
    ).toBeVisible()
    await expect(
      applicantPage.getByText("待審核", { exact: true }),
    ).toBeVisible()
    await expect(applicantPage.getByText(clubName)).toBeVisible()
    await expectNoHorizontalScroll(applicantPage)
  })

  await test.step("平台管理員核准申請", async () => {
    const adminPage = await (await newRoleContext("平台管理員")).newPage()
    await logIn(adminPage, platformAdmin())
    await approveApplication(adminPage, applicant.email)
  })

  await test.step("申請人重新整理後成為主辦方", async () => {
    await applicantPage.reload()
    await expect(applicantPage.getByText("核准", { exact: true })).toBeVisible()
    await expect(
      applicantPage.getByRole("link", { name: "前往主辦方後台" }),
    ).toBeVisible()
    await identitySwitcher(applicantPage).click()
    await applicantPage.getByRole("menuitem", { name: "主辦方後台" }).click()
    await expect(applicantPage).toHaveURL(/\/organizer$/)
    await expect(
      applicantPage.getByRole("heading", { name: "我的賽事", level: 1 }),
    ).toBeVisible()
    await expect(identitySwitcher(applicantPage)).toHaveAccessibleName(
      "切換身分（目前：主辦方後台）",
    )
    await expectNoHorizontalScroll(applicantPage)
  })
})
