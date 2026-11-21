import { describe, expect, it } from "vitest"

import {
  formatRelativeTime,
  formatShortDateTime,
  isoToTaipeiLocal,
  taipeiLocalToIso,
} from "@/lib/datetime"

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

describe("formatShortDateTime", () => {
  it("台北時間的月日、星期與時分", () => {
    // 2026-10-18 是星期日；UTC 11:00 = 台北 19:00
    expect(formatShortDateTime("2026-10-18T11:00:00Z")).toBe("10/18（日）19:00")
    expect(formatShortDateTime("2026-10-17T11:00:00Z")).toBe("10/17（六）19:00")
    // 跨日：UTC 前一天 16:30 = 台北隔天 00:30
    expect(formatShortDateTime("2026-12-31T16:30:00Z")).toBe("01/01（五）00:30")
  })

  it("無法解析時回傳空字串", () => {
    expect(formatShortDateTime("不是時間")).toBe("")
  })
})

describe("formatRelativeTime", () => {
  const now = new Date("2026-10-18T11:00:00Z")

  it("依時間差顯示剛剛、分鐘、小時、天", () => {
    expect(formatRelativeTime("2026-10-18T10:59:30Z", now)).toBe("剛剛")
    expect(formatRelativeTime("2026-10-18T10:57:00Z", now)).toBe("3 分鐘前")
    expect(formatRelativeTime("2026-10-18T10:00:01Z", now)).toBe("59 分鐘前")
    expect(formatRelativeTime("2026-10-18T09:00:00Z", now)).toBe("2 小時前")
    expect(formatRelativeTime("2026-10-13T11:00:00Z", now)).toBe("5 天前")
  })

  it("未來的時間顯示剛剛，無法解析時回傳空字串", () => {
    expect(formatRelativeTime("2026-10-18T11:05:00Z", now)).toBe("剛剛")
    expect(formatRelativeTime("不是時間", now)).toBe("")
  })
})
