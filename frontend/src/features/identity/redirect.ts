/** 控制字元（U+0000～U+001F、U+007F）或任何空白：瀏覽器解析網址時會刪掉 tab、換行。 */
function hasControlOrWhitespace(value: string): boolean {
  for (const char of value) {
    const code = char.codePointAt(0) ?? 0
    if (code < 0x20 || code === 0x7f || /\s/u.test(char)) return true
  }
  return false
}

/**
 * 驗證完成後「繼續」要回到的頁面：只接受站內路徑（/ 開頭，不是 // 或含反斜線），
 * 避免被帶到外部網站。控制字元與空白一律拒絕，否則 `/\t/evil.com` 會被瀏覽器
 * 解析成 `//evil.com`。不合格時回傳 undefined。
 */
export function safeRedirect(value: unknown): string | undefined {
  if (typeof value !== "string" || value.length === 0 || value.length > 2000) {
    return undefined
  }
  if (
    !value.startsWith("/") ||
    value.startsWith("//") ||
    value.includes("\\") ||
    hasControlOrWhitespace(value)
  ) {
    return undefined
  }
  return value
}
