import { type ClassValue, clsx } from "clsx"
import { extendTailwindMerge } from "tailwind-merge"

// 讓 tailwind-merge 認得 index.css 裡 FLOW 自訂的字級、陰影與具名間距，
// 否則像 `text-label` 會被當成文字顏色，與 `text-muted-foreground` 互相覆蓋。
const twMerge = extendTailwindMerge({
  extend: {
    theme: {
      text: [
        "display",
        "heading-lg",
        "heading-md",
        "body",
        "body-lg",
        "label",
        "caption",
        "overline",
        "score",
        "countdown",
        "bracket-row",
      ],
      shadow: ["primary-glow"],
      spacing: [
        "gutter-mobile",
        "gutter-desktop",
        "content-max",
        "sidebar-width",
        "touch-target",
        "bracket-row-height",
        "bracket-match-gap",
        "bracket-connector-width",
        "bracket-column-min",
        "match-aside-width",
        "match-column-gap",
        "backdrop-grid",
        "screenshot-viewer-max",
      ],
    },
  },
})

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
