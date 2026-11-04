import { describe, expect, it } from "vitest"

import { roundName } from "@/features/competition/round-name"

describe("roundName", () => {
  it("5 輪：32 強、16 強、8 強、4 強、決賽", () => {
    expect([1, 2, 3, 4, 5].map((n) => roundName(n, 5))).toEqual([
      "32 強",
      "16 強",
      "8 強",
      "4 強",
      "決賽",
    ])
  })

  it("只有 1 輪：決賽", () => {
    expect(roundName(1, 1)).toBe("決賽")
  })
})
