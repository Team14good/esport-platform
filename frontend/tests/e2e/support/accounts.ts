// 帳號相關的共用步驟：每次執行用不重複的 Email，可以對同一個資料庫重複執行。
import { expect, type Page } from "@playwright/test"

import { platformAdminCredentials } from "./env"
import { expectNoHorizontalScroll } from "./layout"
import { waitForVerificationLink } from "./mailpit"

export type TestAccount = {
  email: string
  password: string
  displayName: string
}

const TEST_PASSWORD = "e2e-password-2026"

/** 每次呼叫都不同的短字串（時間＋亂數），用在 Email、社團名稱等需要不重複的欄位。 */
export function uniqueSuffix(): string {
  return `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`
}

/** 新的測試帳號資料（還沒註冊）；`role` 只用來讓 Email 好辨認。 */
export function newTestAccount(role: string): TestAccount {
  const suffix = uniqueSuffix()
  return {
    email: `e2e-${role}-${suffix}@example.com`,
    password: TEST_PASSWORD,
    displayName: `E2E ${role} ${suffix.slice(-6)}`,
  }
}

/** compose 啟動時建立的首位平台管理員 */
export function platformAdmin(): TestAccount {
  const { email, password } = platformAdminCredentials()
  return { email, password, displayName: "平台管理員" }
}

/** 學校下拉（Popover＋Command）：搜尋校名後點選選項。 */
export async function pickSchool(page: Page, school: string) {
  const trigger = page.getByRole("combobox", { name: "學校", exact: true })
  await trigger.click()
  await page.getByPlaceholder("輸入校名搜尋").fill(school)
  await page.getByRole("option", { name: school, exact: true }).click()
  await expect(trigger).toHaveText(school)
}

/** S5 註冊，成功後停在 S7「請收信驗證」。 */
export async function signUp(
  page: Page,
  account: TestAccount,
  options: { school?: string } = {},
) {
  await page.goto("/signup")
  await expect(
    page.getByRole("heading", { name: "註冊帳號", level: 1 }),
  ).toBeVisible()
  await expectNoHorizontalScroll(page)
  await page.getByLabel("Email", { exact: true }).fill(account.email)
  await page.getByLabel("密碼", { exact: true }).fill(account.password)
  await page.getByLabel("顯示名稱", { exact: true }).fill(account.displayName)
  if (options.school) await pickSchool(page, options.school)
  await page.getByRole("button", { name: "註冊帳號" }).click()
  await expect(page).toHaveURL(/\/verify-email/)
  await expect(
    page.getByRole("heading", { name: "請收信驗證", level: 1 }),
  ).toBeVisible()
  await expectNoHorizontalScroll(page)
}

/** 從 Mailpit 取驗證信並打開驗證連結。 */
export async function verifyEmail(page: Page, account: TestAccount) {
  const link = await waitForVerificationLink(account.email)
  await page.goto(link)
  await expect(
    page.getByRole("heading", { name: "Email 驗證完成", level: 1 }),
  ).toBeVisible()
  await expectNoHorizontalScroll(page)
}

/** 頂欄的身分切換器（aria-label 以「切換身分」開頭；窄螢幕只顯示圖示）。 */
export function identitySwitcher(page: Page) {
  return page.getByRole("button", { name: /^切換身分/ })
}

/** S6 登入，成功後頂欄出現身分切換器。 */
export async function logIn(page: Page, account: TestAccount) {
  await page.goto("/login")
  await expect(
    page.getByRole("heading", { name: "登入", level: 1 }),
  ).toBeVisible()
  await expectNoHorizontalScroll(page)
  await page.getByLabel("Email", { exact: true }).fill(account.email)
  await page.getByLabel("密碼", { exact: true }).fill(account.password)
  await page.getByRole("button", { name: "登入", exact: true }).click()
  await expect(identitySwitcher(page)).toBeVisible()
}

/** 註冊、驗證 Email 並登入（之後的 Story 建立隊長、選手、裁判時共用）。 */
export async function registerVerifiedAccount(
  page: Page,
  account: TestAccount,
  options: { school?: string } = {},
) {
  await signUp(page, account, options)
  await verifyEmail(page, account)
  await logIn(page, account)
}
