import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import {
  PageBanner,
  PageBannerSlot,
  pickPageBanner,
} from "@/components/common/PageBanner"

describe("Page banner", () => {
  it("destructive：顯示訊息，沒有按鈕也不能關閉", () => {
    render(<PageBanner variant="destructive">此賽事已取消</PageBanner>)

    const banner = screen.getByRole("alert")
    expect(banner).toHaveTextContent("此賽事已取消")
    expect(banner).toHaveAttribute("data-slot", "page-banner")
    expect(screen.queryByRole("button")).toBeNull()
  })

  it("default 用 status，不打斷螢幕閱讀器", () => {
    render(<PageBanner>計時暫停</PageBanner>)

    const banner = screen.getByRole("status")
    expect(banner).toHaveTextContent("計時暫停")
    expect(banner).toHaveAttribute("data-slot", "page-banner")
    expect(screen.queryByRole("alert")).toBeNull()
  })

  it("default：可帶 outline 按鈕與關閉鈕", async () => {
    const user = userEvent.setup()
    const onClick = vi.fn()
    const onDismiss = vi.fn()
    render(
      <PageBanner
        action={{ label: "申請成為主辦方", onClick }}
        onDismiss={onDismiss}
      >
        想辦賽事？
      </PageBanner>,
    )

    await user.click(screen.getByRole("button", { name: "申請成為主辦方" }))
    expect(onClick).toHaveBeenCalledTimes(1)

    await user.click(screen.getByRole("button", { name: "關閉提示" }))
    expect(onDismiss).toHaveBeenCalledTimes(1)
  })

  it("default 沒有傳 onDismiss 時沒有關閉鈕", () => {
    render(<PageBanner>連線中斷，正在重試</PageBanner>)

    expect(screen.getByRole("status")).toHaveTextContent("連線中斷，正在重試")
    expect(screen.queryByRole("button", { name: "關閉提示" })).toBeNull()
  })

  it("同頁最多一則：destructive 優先，否則取第一則；沒有候選時不顯示", () => {
    const info = { children: "計時暫停" }
    const cancelled = { variant: "destructive" as const, children: "已取消" }

    expect(pickPageBanner([info, false, cancelled])).toBe(cancelled)
    expect(pickPageBanner([null, info, { children: "第二則" }])).toBe(info)
    expect(pickPageBanner([false, null, undefined])).toBeNull()
  })

  it("PageBannerSlot 只渲染挑中的那一則", () => {
    const { container, rerender } = render(
      <PageBannerSlot
        banners={[
          { children: "連線中斷" },
          { variant: "destructive", children: "此賽事已取消" },
        ]}
      />,
    )

    const banners = screen.getAllByRole("alert")
    expect(banners).toHaveLength(1)
    expect(banners[0]).toHaveTextContent("此賽事已取消")

    rerender(<PageBannerSlot banners={[false]} />)
    expect(container).toBeEmptyDOMElement()
  })
})
