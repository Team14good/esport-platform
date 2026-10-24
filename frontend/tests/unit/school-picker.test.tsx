import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { useState } from "react"
import { describe, expect, it } from "vitest"

import type { PublicSchool } from "@/client"
import {
  matchSchool,
  SCHOOL_NOT_FOUND_TEXT,
  SchoolPicker,
} from "@/features/identity/SchoolPicker"

const SCHOOLS: PublicSchool[] = [
  { id: "1", name: "國立臺灣大學" },
  { id: "2", name: "國立臺灣師範大學" },
  { id: "3", name: "國立清華大學" },
  { id: "4", name: "FLOW Esports Academy" },
]

function Harness({ initial = null }: { initial?: string | null }) {
  const [value, setValue] = useState<string | null>(initial)
  return (
    <>
      <SchoolPicker schools={SCHOOLS} value={value} onChange={setValue} />
      <output data-testid="value">{value ?? "none"}</output>
    </>
  )
}

async function openPicker() {
  const user = userEvent.setup()
  render(<Harness />)
  await user.click(screen.getByRole("combobox"))
  const search = await screen.findByRole("combobox", { name: "搜尋學校" })
  return { user, search }
}

function optionNames() {
  return screen.queryAllByRole("option").map((option) => option.textContent)
}

describe("School picker", () => {
  it("輸入部分校名：只列出名稱包含該字串的學校", async () => {
    const { user, search } = await openPicker()
    expect(optionNames()).toHaveLength(SCHOOLS.length)

    await user.type(search, "臺灣大學")

    expect(optionNames()).toEqual(["國立臺灣大學"])
  })

  it("不分大小寫", async () => {
    const { user, search } = await openPicker()

    await user.type(search, "esPORTS")

    expect(optionNames()).toEqual(["FLOW Esports Academy"])
  })

  it("沒有符合的學校：顯示「找不到這間學校」，也無法把自由文字當成選取值", async () => {
    const { user, search } = await openPicker()

    await user.type(search, "不存在的學校")

    expect(screen.getByText(SCHOOL_NOT_FOUND_TEXT)).toBeInTheDocument()
    expect(optionNames()).toEqual([])
    await user.keyboard("{Enter}")
    expect(screen.getByTestId("value")).toHaveTextContent("none")
  })

  it("選取後顯示校名，可以清除", async () => {
    const { user, search } = await openPicker()
    await user.type(search, "清華")
    await user.click(screen.getByRole("option", { name: "國立清華大學" }))

    expect(screen.getByTestId("value")).toHaveTextContent("3")
    expect(screen.getByRole("combobox")).toHaveTextContent("國立清華大學")

    await user.click(screen.getByRole("button", { name: "清除學校" }))

    expect(screen.getByTestId("value")).toHaveTextContent("none")
    expect(screen.getByRole("combobox")).toHaveTextContent("選擇學校（選填）")
    expect(screen.queryByRole("button", { name: "清除學校" })).toBeNull()
  })

  it("已選的學校在清單中打勾", async () => {
    const user = userEvent.setup()
    render(<Harness initial="2" />)
    await user.click(screen.getByRole("combobox"))

    const option = await screen.findByRole("option", {
      name: "國立臺灣師範大學",
    })
    expect(within(option).getByText("國立臺灣師範大學")).toBeTruthy()
    expect(option.querySelector("svg.opacity-100")).not.toBeNull()
  })

  it("matchSchool：空白關鍵字全部符合、前後空白忽略", () => {
    expect(matchSchool("國立臺灣大學", "")).toBe(true)
    expect(matchSchool("國立臺灣大學", "  臺灣 ")).toBe(true)
    expect(matchSchool("國立臺灣大學", "清華")).toBe(false)
  })
})
