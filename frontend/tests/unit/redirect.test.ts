import { describe, expect, it } from "vitest"

import { safeRedirect } from "@/features/identity/redirect"

describe("safeRedirect", () => {
  it("接受站內路徑（可帶查詢參數與 hash）", () => {
    expect(safeRedirect("/")).toBe("/")
    expect(safeRedirect("/join/x?code=abc#top")).toBe("/join/x?code=abc#top")
  })

  it.each([
    ["外部網址", "https://evil.example.com"],
    ["協定相對網址", "//evil.example.com"],
    ["反斜線", "/\\evil.com"],
    ["tab", "/\t/evil.com"],
    ["換行", "/\n/evil.com"],
    ["歸位", "/\r/evil.com"],
    ["NUL", "/\u0000/evil.com"],
    ["DEL", "/x\u007f"],
    ["空白", "/a b"],
    ["全形空白", "/a　b"],
    ["不是 / 開頭", "evil.com"],
    ["空字串", ""],
  ])("拒絕%s", (_label, value) => {
    expect(safeRedirect(value)).toBeUndefined()
  })

  it("拒絕非字串與過長的值", () => {
    expect(safeRedirect(undefined)).toBeUndefined()
    expect(safeRedirect(123)).toBeUndefined()
    expect(safeRedirect(`/${"a".repeat(2000)}`)).toBeUndefined()
  })
})
