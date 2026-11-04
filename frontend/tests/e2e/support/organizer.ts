// 主辦方相關的共用步驟：S35 平台管理員核准申請，以及從註冊到核准建立一個主辦方（不依賴示範資料）。
import { expect, type Page } from "@playwright/test"

import {
  newTestAccount,
  registerVerifiedAccount,
  type TestAccount,
  uniqueSuffix,
} from "./accounts"
import { expectNoHorizontalScroll } from "./layout"

/** 申請主辦方與註冊時用的學校（後端內建的學校清單） */
export const ORGANIZER_SCHOOL = "國立政治大學"

/** S35 找到這個 Email 的待審核申請並核准；申請依送出時間由舊到新排，可能在後面的頁。 */
export async function approveApplication(page: Page, applicantEmail: string) {
  // 換頁時列表用 keepPreviousData，不會出現 aria-busy，畫面上的列可能還是上一頁的；
  // 所以改看第 n 頁的 API 回應決定要不要再按「下一頁」
  const listedPage = (n: number) =>
    page
      .waitForResponse((response) => {
        const url = new URL(response.url())
        return (
          response.request().method() === "GET" &&
          response.ok() &&
          url.pathname.endsWith("/admin/organizer-applications") &&
          url.searchParams.get("page") === String(n)
        )
      })
      .then(async (response) => {
        const body = (await response.json()) as {
          items: { applicant_email: string }[]
          total: number
          page_size: number
        }
        return {
          found: body.items.some(
            (item) => item.applicant_email === applicantEmail,
          ),
          lastPage: Math.max(1, Math.ceil(body.total / body.page_size)),
        }
      })

  let current = 1
  let listed = listedPage(current)
  await page.goto("/admin/applications")
  await expect(
    page.getByRole("heading", { name: "主辦方申請", level: 1 }),
  ).toBeVisible()
  for (;;) {
    const { found, lastPage } = await listed
    if (found) break
    if (current >= lastPage) {
      throw new Error(`待審核清單裡找不到 ${applicantEmail} 的主辦方申請`)
    }
    current += 1
    listed = listedPage(current)
    await page.getByRole("button", { name: "下一頁" }).click()
  }
  // 桌機是表格的一列，窄螢幕是卡片清單的一項；只取看得到的那一個
  const row = page
    .locator(
      "[data-slot=data-table] tbody tr, [data-slot=data-table-cards] > li",
    )
    .filter({ hasText: applicantEmail })
    .filter({ visible: true })
  await expect(row).toBeVisible()
  await expectNoHorizontalScroll(page)
  await row.getByRole("button", { name: "核准", exact: true }).click()
  const dialog = page.getByRole("alertdialog", { name: "核准主辦方申請" })
  await expect(dialog).toBeVisible()
  await dialog.getByRole("button", { name: "核准", exact: true }).click()
  await expect(dialog).toBeHidden()
  // 核准後這筆不再是待審核
  await expect(row).toHaveCount(0)
}

/** S12 送出主辦方申請，停在「待審核」。 */
export async function applyForOrganizer(page: Page, clubName: string) {
  await page.goto("/organizer/apply")
  await expect(
    page.getByRole("heading", { name: "申請成為主辦方", level: 1 }),
  ).toBeVisible()
  await page.getByLabel("社團名稱", { exact: true }).fill(clubName)
  await page.getByRole("button", { name: "送出申請" }).click()
  await expect(page.getByText("待審核", { exact: true })).toBeVisible()
}

/**
 * 從頭建立一個主辦方：註冊並驗證 Email、登入、申請主辦方，由平台管理員核准。
 * `organizerPage` 結束時停在已核准的申請頁；`adminPage` 必須已用平台管理員登入。
 */
export async function createOrganizer(
  organizerPage: Page,
  adminPage: Page,
): Promise<TestAccount> {
  const organizer = newTestAccount("organizer")
  await registerVerifiedAccount(organizerPage, organizer, {
    school: ORGANIZER_SCHOOL,
  })
  await applyForOrganizer(organizerPage, `E2E 電競社 ${uniqueSuffix()}`)
  await approveApplication(adminPage, organizer.email)
  await organizerPage.reload()
  await expect(
    organizerPage.getByRole("link", { name: "前往主辦方後台" }),
  ).toBeVisible()
  return organizer
}
