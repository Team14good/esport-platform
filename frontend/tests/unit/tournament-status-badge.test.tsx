import { render, screen, within } from "@testing-library/react"
import { beforeAll, describe, expect, it, vi } from "vitest"

import {
  type PublicTournament,
  type TournamentStatus,
  TournamentsService,
} from "@/client"
import type { StatusTone } from "@/components/common/StatusBadge"
import { TournamentStatusBadge } from "@/features/tournaments/TournamentStatusBadge"
import { renderApp } from "./auth-fixtures"

vi.mock("@tanstack/react-router-devtools", () => ({
  TanStackRouterDevtools: () => null,
}))
vi.mock("@tanstack/react-query-devtools", () => ({
  ReactQueryDevtools: () => null,
}))

type ListResult = Awaited<
  ReturnType<typeof TournamentsService.listPublicTournaments>
>
type ReadResult = Awaited<
  ReturnType<typeof TournamentsService.readPublicTournament>
>

function tournament(
  overrides: Partial<PublicTournament> = {},
): PublicTournament {
  return {
    id: "t-1",
    name: "期中盃",
    status: "published",
    game_name: "特戰英豪",
    capacity: 16,
    registration_start: "2025-10-12T11:00:00Z",
    priority_end: "2025-10-13T11:00:00Z",
    registration_end: "2025-10-17T11:00:00Z",
    start_at: "2025-10-18T11:00:00Z",
    round_interval_minutes: 180,
    livestream_url: null,
    ...overrides,
  }
}

function badgeIn(container: HTMLElement): HTMLElement {
  const badge = container.querySelector<HTMLElement>(
    '[data-slot="status-badge"]',
  )
  if (!badge) throw new Error("找不到狀態徽章")
  return badge
}

// 路由元件是拆分後延遲載入的；先載入頁面模組，避免冷啟動轉譯超過 findBy 的 1 秒等待
beforeAll(async () => {
  await Promise.all([
    import("@/features/tournaments/TournamentList"),
    import("@/features/tournaments/TournamentPage"),
  ])
})

describe("賽事狀態徽章", () => {
  it.each<[TournamentStatus, string, StatusTone, boolean]>([
    ["upcoming", "尚未開放", "muted", false],
    ["open", "開放報名", "live", false],
    ["closed", "報名截止", "muted", false],
    ["published", "賽程已公布", "brand", false],
    ["ongoing", "進行中", "live", true],
    ["finished", "已結束", "muted", false],
    ["cancelled", "已取消", "destructive", false],
  ])("%s：「%s」，tone %s，脈動點 %s", (status, label, tone, pulse) => {
    render(<TournamentStatusBadge status={status} />)

    const badge = screen.getByText(label)
    expect(badge).toHaveAttribute("data-slot", "status-badge")
    expect(badge).toHaveAttribute("data-tone", tone)
    expect(
      badge.querySelector('[data-slot="status-badge-pulse"]') !== null,
    ).toBe(pulse)
  })

  it("S1：每張賽事卡的狀態是徽章；分組標題維持文字", async () => {
    vi.spyOn(TournamentsService, "listPublicTournaments").mockResolvedValue({
      data: [
        tournament({ id: "t-on", name: "進行盃", status: "ongoing" }),
        tournament({ id: "t-x", name: "取消盃", status: "cancelled" }),
      ],
    } as unknown as ListResult)
    renderApp("/")

    const ongoing = await screen.findByRole("link", { name: /進行盃/ })
    expect(badgeIn(ongoing)).toHaveTextContent("進行中")
    expect(badgeIn(ongoing)).toHaveAttribute("data-tone", "live")
    const cancelled = screen.getByRole("link", { name: /取消盃/ })
    expect(badgeIn(cancelled)).toHaveAttribute("data-tone", "destructive")

    const heading = screen.getByRole("heading", { name: "進行中（1 場）" })
    expect(
      heading.querySelector('[data-slot="status-badge"]'),
    ).not.toBeInTheDocument()
  })

  it("S2：標題列與總覽的「狀態」欄都是徽章", async () => {
    vi.spyOn(TournamentsService, "readPublicTournament").mockResolvedValue({
      data: tournament({ status: "published" }),
    } as unknown as ReadResult)
    renderApp("/tournaments/t-1")

    const title = await screen.findByRole("heading", {
      level: 1,
      name: "期中盃",
    })
    const header = title.closest("header")
    if (!header) throw new Error("找不到標題列")
    expect(badgeIn(header)).toHaveTextContent("賽程已公布")
    expect(badgeIn(header)).toHaveAttribute("data-tone", "brand")

    const status = within(screen.getByRole("tabpanel"))
      .getByText("狀態")
      .closest("div")
    if (!status) throw new Error("找不到狀態欄")
    expect(badgeIn(status)).toHaveTextContent("賽程已公布")
  })
})
