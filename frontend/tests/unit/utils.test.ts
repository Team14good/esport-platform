import { describe, expect, it } from "vitest"

import { cn } from "@/lib/utils"

describe("cn（tailwind-merge 認得 FLOW 自訂 token）", () => {
  it("具名間距與預設間距互相覆蓋", () => {
    expect(cn("h-9", "h-touch-target")).toBe("h-touch-target")
  })

  it("自訂字級不會被當成文字顏色", () => {
    const classes = cn("text-label", "text-muted-foreground").split(" ")
    expect(classes).toContain("text-label")
    expect(classes).toContain("text-muted-foreground")
  })

  it("自訂陰影與預設陰影互相覆蓋", () => {
    expect(cn("shadow-xs", "shadow-primary-glow")).toBe("shadow-primary-glow")
  })
})
