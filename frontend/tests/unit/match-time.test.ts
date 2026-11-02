import { describe, expect, it } from "vitest"

import {
  formatClock,
  formatMatchDateTime,
} from "@/features/competition/match-time"

const NOW = new Date("2026-10-29T04:00:00Z")

describe("formatMatchDateTime", () => {
  it("同年：月/日（星期）HH:mm，換算成台北時間", () => {
    expect(formatMatchDateTime("2026-10-17T03:52:00Z", NOW)).toBe(
      "10/17（六）11:52",
    )
  })

  it("帶 +08:00 的輸入也得到同一個結果", () => {
    expect(formatMatchDateTime("2026-10-17T11:52:00+08:00", NOW)).toBe(
      "10/17（六）11:52",
    )
  })

  it("UTC 前一天、台北已過午夜：日期與星期跟著換，時寫 00", () => {
    expect(formatMatchDateTime("2026-10-17T16:30:00Z", NOW)).toBe(
      "10/18（日）00:30",
    )
  })

  it("跨年：前面加年份，月日不補零、時分補零", () => {
    expect(formatMatchDateTime("2027-01-02T01:05:00Z", NOW)).toBe(
      "2027/1/2（六）09:05",
    )
    expect(formatMatchDateTime("2025-10-18T11:00:00Z", NOW)).toBe(
      "2025/10/18（六）19:00",
    )
  })

  it("是否跨年以台北時間的年份比較", () => {
    // 台北 2027/1/1 00:30
    const iso = "2026-12-31T16:30:00Z"
    // now 是台北 2026/12/31 23:00：不同年
    expect(formatMatchDateTime(iso, new Date("2026-12-31T15:00:00Z"))).toBe(
      "2027/1/1（五）00:30",
    )
    // now 的 UTC 年份還是 2026，但台北已是 2027/1/1：同年
    expect(formatMatchDateTime(iso, new Date("2026-12-31T16:00:00Z"))).toBe(
      "1/1（五）00:30",
    )
  })
  it("空字串或格式錯誤：回傳空字串，不拋錯", () => {
    expect(formatMatchDateTime("", NOW)).toBe("")
    expect(formatMatchDateTime("not-a-date", NOW)).toBe("")
  })
})

describe("formatClock", () => {
  it("台北時間的 HH:mm", () => {
    expect(formatClock("2026-10-17T11:32:00Z")).toBe("19:32")
    expect(formatClock("2026-10-17T01:05:00Z")).toBe("09:05")
  })

  it("午夜寫 00，不寫 24", () => {
    expect(formatClock("2026-10-17T16:05:00Z")).toBe("00:05")
  })

  it("空字串或格式錯誤：回傳空字串，不拋錯", () => {
    expect(formatClock("")).toBe("")
    expect(formatClock("2026-13-40T99:00:00Z")).toBe("")
  })
})
