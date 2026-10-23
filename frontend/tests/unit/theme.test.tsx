import { readFileSync } from "node:fs"
import path from "node:path"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ThemeToggle } from "@/components/layout/ThemeToggle"
import { THEME_STORAGE_KEY, ThemeProvider } from "@/components/theme-provider"

function renderToggle() {
  return render(
    <ThemeProvider>
      <ThemeToggle />
    </ThemeProvider>,
  )
}

const html = document.documentElement

beforeEach(() => {
  html.className = "dark"
})

describe("主題切換", () => {
  it("首次造訪：沒有已存主題時為深色，顯示太陽圖示", () => {
    const { container } = renderToggle()

    expect(html).toHaveClass("dark")
    expect(html).not.toHaveClass("light")
    expect(
      screen.getByRole("button", { name: "切換為淺色模式" }),
    ).toBeInTheDocument()
    expect(container.querySelector("svg.lucide-sun")).not.toBeNull()
  })

  it("點主題切換：立即換成淺色並寫入 localStorage，重新整理後仍是淺色、顯示月亮", async () => {
    const user = userEvent.setup()
    const first = renderToggle()

    await user.click(screen.getByRole("button", { name: "切換為淺色模式" }))

    expect(html).toHaveClass("light")
    expect(html).not.toHaveClass("dark")
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("light")

    // 模擬重新整理：重新掛載
    first.unmount()
    html.className = "dark"
    const { container } = renderToggle()

    expect(html).toHaveClass("light")
    expect(
      screen.getByRole("button", { name: "切換為深色模式" }),
    ).toBeInTheDocument()
    expect(container.querySelector("svg.lucide-moon")).not.toBeNull()
  })

  it("存取 localStorage 失敗時仍可切換，只是不保存", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked")
    })
    const setItem = vi
      .spyOn(Storage.prototype, "setItem")
      .mockImplementation(() => {
        throw new Error("blocked")
      })
    const user = userEvent.setup()
    renderToggle()

    expect(html).toHaveClass("dark")
    await user.click(screen.getByRole("button", { name: "切換為淺色模式" }))

    expect(setItem).toHaveBeenCalled()
    expect(html).toHaveClass("light")
    expect(
      screen.getByRole("button", { name: "切換為深色模式" }),
    ).toBeInTheDocument()
  })

  it("無效的已存主題視為深色", () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, "purple")
    renderToggle()

    expect(html).toHaveClass("dark")
    expect(
      screen.getByRole("button", { name: "切換為淺色模式" }),
    ).toBeInTheDocument()
  })
})

describe("index.html 繪製前套用主題", () => {
  const indexHtml = readFileSync(
    path.resolve(import.meta.dirname, "../../index.html"),
    "utf-8",
  )
  const inlineScript = indexHtml.match(/<script>([\s\S]*?)<\/script>/)?.[1]

  function runInlineScript() {
    expect(inlineScript).toBeDefined()
    new Function(inlineScript as string)()
  }

  it("<html> 預設帶 dark、語言為 zh-Hant", () => {
    expect(indexHtml).toMatch(/<html lang="zh-Hant" class="dark">/)
  })

  it("已存 light 時在繪製前換成淺色", () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, "light")
    runInlineScript()
    expect(html).toHaveClass("light")
    expect(html).not.toHaveClass("dark")
  })

  it("沒有已存主題或值無效時維持深色", () => {
    runInlineScript()
    expect(html).toHaveClass("dark")

    window.localStorage.setItem(THEME_STORAGE_KEY, "purple")
    runInlineScript()
    expect(html).toHaveClass("dark")
  })

  it("讀取 localStorage 失敗時維持深色", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked")
    })
    runInlineScript()
    expect(html).toHaveClass("dark")
  })

  it("有 16px 單色與 32px 漸層 favicon，且沒有載入 webfont", () => {
    expect(indexHtml).toMatch(
      /<link rel="icon" type="image\/png" sizes="16x16" href="\/favicon-16.png" \/>/,
    )
    expect(indexHtml).toMatch(
      /<link rel="icon" type="image\/png" sizes="32x32" href="\/favicon-32.png" \/>/,
    )
    expect(indexHtml).toMatch(/rel="apple-touch-icon" sizes="180x180"/)
    expect(indexHtml).not.toMatch(/fonts\.googleapis|@font-face|\.woff2?/)
  })
})
