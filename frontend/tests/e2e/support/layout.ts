// NFR-7：頁面沒有橫向捲軸；只有對戰樹（[data-slot=bracket-tree]）可以左右捲動。
import { expect, type Page } from "@playwright/test"

export const BRACKET_TREE_SELECTOR = "[data-slot=bracket-tree]"

/** 開發模式才有的 TanStack 開發工具（不是產品介面），不檢查 */
const DEVTOOLS_SELECTOR = ".TanStackRouterDevtools, .tsqd-parent-container"

type LayoutReport = {
  /** document 比視窗寬多少 px（> 0 代表有橫向捲軸） */
  pageOverflow: number
  /** 除對戰樹外，內容超出寬度而且可以橫向捲動的元素 */
  scrollers: string[]
}

/** 檢查目前頁面沒有橫向捲軸，也沒有對戰樹以外的橫向捲動區。 */
export async function expectNoHorizontalScroll(page: Page) {
  const report = await page.evaluate(
    ({ allowed, ignored }): LayoutReport => {
      const describe = (element: Element) => {
        const slot = element.getAttribute("data-slot")
        const classes = element.getAttribute("class")?.split(/\s+/).slice(0, 4)
        return `${element.tagName.toLowerCase()}${slot ? `[data-slot=${slot}]` : ""}${classes?.length ? `.${classes.join(".")}` : ""}`
      }
      const root = document.documentElement
      const scrollers = [...document.body.querySelectorAll("*")]
        .filter((element) => {
          const { overflowX, visibility } = getComputedStyle(element)
          return (
            (overflowX === "auto" || overflowX === "scroll") &&
            visibility !== "hidden" &&
            element.scrollWidth > element.clientWidth + 1 &&
            !element.matches(allowed) &&
            element.closest(ignored) === null
          )
        })
        .map(describe)
      return { pageOverflow: root.scrollWidth - root.clientWidth, scrollers }
    },
    { allowed: BRACKET_TREE_SELECTOR, ignored: DEVTOOLS_SELECTOR },
  )
  expect(
    report.pageOverflow,
    `${page.url()} 的頁面比視窗寬 ${report.pageOverflow} px，出現橫向捲軸`,
  ).toBeLessThanOrEqual(0)
  expect(report.scrollers, `${page.url()} 有對戰樹以外的橫向捲動區`).toEqual([])
}

/** 窄螢幕（< 640 px，Tailwind 的 sm 以下）：手機版的額外檢查用。 */
export function isNarrowViewport(page: Page): boolean {
  return (page.viewportSize()?.width ?? Number.POSITIVE_INFINITY) < 640
}
