import { describe, expect, it } from "vitest"

import { isoToTaipeiLocal, taipeiLocalToIso } from "@/lib/datetime"

describe("isoToTaipeiLocal", () => {
  it("UTC 轉台北時間的 datetime-local 值", () => {
    expect(isoToTaipeiLocal("2026-11-10T11:00:00Z")).toBe("2026-11-10T19:00")
    // 跨日
    expect(isoToTaipeiLocal("2025-12-31T19:30:00.000Z")).toBe(
      "2026-01-01T03:30",
    )
    // 秒以下捨去
    expect(isoToTaipeiLocal("2026-11-10T11:00:59.999Z")).toBe(
      "2026-11-10T19:00",
    )
  })

  it("無法解析時回傳空字串", () => {
    expect(isoToTaipeiLocal("")).toBe("")
    expect(isoToTaipeiLocal("不是時間")).toBe("")
  })

  it("與 taipeiLocalToIso 互為反向", () => {
    for (const local of [
      "2026-11-10T19:00",
      "2026-01-01T00:00",
      "2026-12-31T23:59",
    ]) {
      const iso = taipeiLocalToIso(local)
      expect(iso).not.toBeNull()
      expect(isoToTaipeiLocal(iso as string)).toBe(local)
    }
  })
})
