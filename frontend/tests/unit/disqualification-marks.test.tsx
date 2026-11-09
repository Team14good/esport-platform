import {
  QueryClient,
  QueryClientProvider,
  useQuery,
} from "@tanstack/react-query"
import { createMemoryHistory, createRouter } from "@tanstack/react-router"
import {
  render,
  renderHook,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import type { ReactNode } from "react"
import { beforeAll, describe, expect, it, vi } from "vitest"

import {
  CompetitionService,
  DisputesService,
  type MyTeamCard,
  type PublicBracket,
  type PublicMatchDetail,
  RegistrationService,
  type TeamDetail,
} from "@/client"
import { RouteErrorPage } from "@/components/layout/ErrorPage"
import { BracketTree } from "@/features/competition/BracketTree"
import { createBracketFixture } from "@/features/competition/bracket-fixtures"
import { publicBracketQueryKey } from "@/features/competition/bracket-queries"
import { MatchScoreDisplay } from "@/features/competition/MatchScoreDisplay"
import { matchDetailFromBracket } from "@/features/competition/match-fixtures"
import { disqualifiedLastMatches } from "@/features/competition/match-status"
import { useDisqualifiedMarks } from "@/features/competition/use-disqualified-marks"
import { routeTree } from "@/routeTree.gen"
import { renderApp, signInAs } from "./auth-fixtures"
import { httpError } from "./helpers"
import { matchDetail, TEAM_A, TEAM_B } from "./match-detail-fixture"
import { renderRouter } from "./render-router"

vi.mock("@tanstack/react-router-devtools", () => ({
  TanStackRouterDevtools: () => null,
}))
vi.mock("@tanstack/react-query-devtools", () => ({
  ReactQueryDevtools: () => null,
}))

type ReadTeamResult = Awaited<ReturnType<typeof RegistrationService.readTeam>>
type MyTeamsResult = Awaited<ReturnType<typeof RegistrationService.listMyTeams>>
type ReasonResult = Awaited<
  ReturnType<typeof DisputesService.readTeamDisqualification>
>
type AppealResultResult = Awaited<
  ReturnType<typeof DisputesService.readAppealResult>
>

const REASON = "查證屬實：隊員學生證與報名資料不符。"

/** 把對戰表裡某隊的每次出現都標為已取消資格（後端同一隊每次出現都一致）。 */
function disqualify(bracket: PublicBracket, teamId: string): PublicBracket {
  const mark = <T extends { id: string } | null>(team: T): T =>
    team !== null && team.id === teamId ? { ...team, disqualified: true } : team
  return {
    ...bracket,
    matches: bracket.matches.map((match) => ({
      ...match,
      team_a: mark(match.team_a),
      team_b: mark(match.team_b),
    })),
  }
}

/** 4 隊、全部已確認：M1、M2 準決賽，M3 決賽，最後是季軍賽 */
const FINISHED = createBracketFixture({ teamCount: 4, scenario: "finished" })
const M1 = FINISHED.matches.find((m) => m.code === "M1")!
const FINAL = FINISHED.matches.find(
  (m) => m.round_no === 2 && !m.is_third_place,
)!
const THIRD = FINISHED.matches.find((m) => m.is_third_place)!
const FINALIST = [FINAL.team_a!, FINAL.team_b!].find((team) =>
  [M1.team_a?.id, M1.team_b?.id].includes(team.id),
)!
const THIRD_PLACER = [THIRD.team_a!, THIRD.team_b!].find((team) =>
  [M1.team_a?.id, M1.team_b?.id].includes(team.id),
)!

function marksOf(card: HTMLElement, teamName: string) {
  const row = [
    ...card.querySelectorAll<HTMLElement>("[data-slot=bracket-team-row]"),
  ].find((r) => r.textContent?.includes(teamName))
  expect(row).toBeDefined()
  return [...(row?.querySelectorAll("[data-slot=bracket-mark-tag]") ?? [])].map(
    (tag) => tag.textContent,
  )
}

describe("取消資格標記：只標在最後一張場次卡", () => {
  it("依輪次找最後一場，季軍賽排在決賽之後", () => {
    const bracket = disqualify(
      disqualify(FINISHED, FINALIST.id),
      THIRD_PLACER.id,
    )
    const last = disqualifiedLastMatches(bracket.matches)
    expect(last.get(FINALIST.id)).toBe(FINAL.id)
    expect(last.get(THIRD_PLACER.id)).toBe(THIRD.id)
    expect(last.size).toBe(2)
    // 沒有取消資格的隊伍不在裡面
    expect(disqualifiedLastMatches(FINISHED.matches).size).toBe(0)
  })

  it("輪空直接進第二輪的隊伍：最後一場是它唯一的那張卡", () => {
    const six = createBracketFixture({ teamCount: 6, scenario: "scheduled" })
    const byeMatch = six.matches.find(
      (m) => (m.bye_a && m.team_a !== null) || (m.bye_b && m.team_b !== null),
    )!
    const team = (byeMatch.bye_a ? byeMatch.team_a : byeMatch.team_b)!
    const last = disqualifiedLastMatches(disqualify(six, team.id).matches)
    expect(last.get(team.id)).toBe(byeMatch.id)
    expect(last.size).toBe(1)
  })

  it("第一輪就淘汰的隊伍：最後一場是第一輪那張卡", () => {
    const eight = createBracketFixture({ teamCount: 8, scenario: "finished" })
    const first = eight.matches.find((m) => m.code === "M1")!
    const loser = [first.team_a!, first.team_b!].find(
      (team) => team.id !== first.winner_id,
    )!
    const last = disqualifiedLastMatches(disqualify(eight, loser.id).matches)
    expect(last.get(loser.id)).toBe(first.id)
  })

  it("對戰樹：決賽隊伍只在決賽卡帶標記，準決賽卡照舊", () => {
    render(<BracketTree bracket={disqualify(FINISHED, FINALIST.id)} />)

    const final = screen.getByRole("article", { name: FINAL.code })
    const semi = screen.getByRole("article", { name: "M1" })
    expect(marksOf(final, FINALIST.name)).toContain("取消資格")
    expect(marksOf(semi, FINALIST.name)).not.toContain("取消資格")
    // 標記是 destructive
    const tag = within(final)
      .getAllByText("取消資格")
      .find((el) => el.dataset.slot === "bracket-mark-tag")
    expect(tag?.dataset.tone).toBe("destructive")
  })

  it("對戰樹：季軍賽隊伍標在季軍賽卡（排在決賽之後）", () => {
    render(<BracketTree bracket={disqualify(FINISHED, THIRD_PLACER.id)} />)

    expect(
      marksOf(
        screen.getByRole("article", { name: "季軍賽" }),
        THIRD_PLACER.name,
      ),
    ).toContain("取消資格")
    expect(
      marksOf(screen.getByRole("article", { name: "M1" }), THIRD_PLACER.name),
    ).not.toContain("取消資格")
  })

  it("沒有取消資格的對戰樹不出現標記", () => {
    render(<BracketTree bracket={FINISHED} />)
    expect(screen.queryByText("取消資格")).toBeNull()
  })
})

describe("S4 Score display 的取消資格標記", () => {
  function tagsOf(side: "a" | "b") {
    const team = document.querySelector<HTMLElement>(
      `[data-slot=score-team][data-side=${side}]`,
    )!
    return [...team.querySelectorAll("[data-slot=bracket-mark-tag]")].map(
      (tag) => tag.textContent,
    )
  }

  it("傳入的隊伍加標記，另一隊不加", () => {
    const detail = matchDetail({
      status: "confirmed",
      outcome: "played",
      winner_id: TEAM_A.id,
      wins_a: 2,
      wins_b: 0,
      team_a: { ...TEAM_A, disqualified: true },
    })
    render(
      <MatchScoreDisplay
        detail={detail}
        disqualifiedTeamIds={new Set([TEAM_A.id])}
      />,
    )
    expect(tagsOf("a")).toEqual(["取消資格"])
    expect(tagsOf("b")).toEqual([])
  })

  it("以取消資格判負的那一場不重複標記", () => {
    const detail = matchDetail({
      status: "confirmed",
      outcome: "disqualified",
      winner_id: TEAM_B.id,
      team_a: { ...TEAM_A, disqualified: true },
    })
    render(
      <MatchScoreDisplay
        detail={detail}
        disqualifiedTeamIds={new Set([TEAM_A.id])}
      />,
    )
    expect(tagsOf("a")).toEqual(["取消資格"])
  })
})

describe("S4 路由的取消資格標記", () => {
  const bracket = disqualify(FINISHED, FINALIST.id)

  function mockMatchAndBracket() {
    vi.spyOn(CompetitionService, "readPublicMatch").mockImplementation((async ({
      path,
    }: {
      path: { match_id: string }
    }) => ({
      data: matchDetailFromBracket(bracket, path.match_id),
    })) as unknown as typeof CompetitionService.readPublicMatch)
    vi.spyOn(DisputesService, "readAppealResult").mockResolvedValue({
      data: { decision: null },
    } as AppealResultResult)
    return vi.spyOn(CompetitionService, "readPublicBracket").mockResolvedValue({
      data: bracket,
    } as Awaited<ReturnType<typeof CompetitionService.readPublicBracket>>)
  }

  function renderAt(matchId: string) {
    const router = createRouter({
      routeTree,
      history: createMemoryHistory({
        initialEntries: [
          `/tournaments/${bracket.tournament_id}/matches/${matchId}`,
        ],
      }),
      defaultErrorComponent: RouteErrorPage,
    })
    renderRouter(router)
  }

  function scoreTags() {
    const display = document.querySelector<HTMLElement>(
      "[data-slot=score-display]",
    )
    return [
      ...(display?.querySelectorAll("[data-slot=bracket-mark-tag]") ?? []),
    ].map((tag) => tag.textContent)
  }

  it("該隊最後一場顯示標記", async () => {
    const readBracket = mockMatchAndBracket()
    renderAt(FINAL.id)

    await waitFor(() => expect(scoreTags()).toContain("取消資格"))
    expect(readBracket).toHaveBeenCalled()
  })

  it("不是該隊最後一場時不顯示（對戰表讀完後才斷言）", async () => {
    const readBracket = mockMatchAndBracket()
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    )
    const key = publicBracketQueryKey(bracket.tournament_id)
    // 同一次 render 讀出 hook 結果與對戰表快取：快取有資料時，hook 一定已依它計算
    const probe = (matchId: string) => () => ({
      marks: useDisqualifiedMarks(
        matchDetailFromBracket(bracket, matchId) as PublicMatchDetail,
      ),
      cached: useQuery({
        queryKey: key,
        queryFn: () => Promise.resolve(bracket),
        enabled: false,
      }).data,
    })

    const semi = renderHook(probe(M1.id), { wrapper })
    await waitFor(() => expect(semi.result.current.cached).toBeDefined())
    expect([...semi.result.current.marks]).toEqual([])
    expect(readBracket).toHaveBeenCalledTimes(1)

    // 對照：同一份對戰表在決賽會標記，證明上面不是因為沒讀到資料才空
    const final = renderHook(probe(FINAL.id), { wrapper })
    await waitFor(() => expect(final.result.current.cached).toBeDefined())
    expect([...final.result.current.marks]).toEqual([FINALIST.id])
  })

  it("兩隊都沒有取消資格時不讀對戰表", async () => {
    vi.spyOn(CompetitionService, "readPublicMatch").mockResolvedValue({
      data: matchDetailFromBracket(FINISHED, M1.id) as PublicMatchDetail,
    } as Awaited<ReturnType<typeof CompetitionService.readPublicMatch>>)
    vi.spyOn(DisputesService, "readAppealResult").mockResolvedValue({
      data: { decision: null },
    } as AppealResultResult)
    const readBracket = vi.spyOn(CompetitionService, "readPublicBracket")
    renderAt(M1.id)

    await waitFor(() =>
      expect(
        document.querySelector("[data-slot=score-display]"),
      ).not.toBeNull(),
    )
    expect(readBracket).not.toHaveBeenCalled()
  })
})

// ---------------------------------------------------------------- S12、S17 的處理理由

const TEAM: TeamDetail = {
  id: "team-1",
  name: "夜貓隊",
  tournament_id: "tour-1",
  tournament_name: "政大校園盃",
  game_name: "特戰英豪",
  starters: 5,
  substitutes: 1,
  max_members: 6,
  members: [
    {
      account_id: "acc-1",
      display_name: "阿哲",
      role: "captain",
      joined_at: "2026-10-30T10:00:00Z",
      game_account_id: null,
      rank_tier: null,
      rank_score: null,
      has_rank_screenshot: false,
      rank_screenshot_name: null,
      missing_fields: [],
    },
  ],
  registration_status: "disqualified",
  invite_token: "tok-1",
  invite_status: "locked",
  my_role: "captain",
  rank_tiers: [],
  avg_rank_score: null,
  rank_filled_count: 0,
  profile_editable: false,
  submit_blockers: [],
  priority_end: "2026-10-01T00:00:00Z",
  registration_end: "2026-10-08T00:00:00Z",
  submitted_at: "2026-09-30T00:00:00Z",
  waitlist_position: null,
  waitlist_reason: null,
  representative_backfill: null,
  waitlist_phase: null,
}

const CARD: MyTeamCard = {
  team_id: "team-1",
  team_name: "夜貓隊",
  tournament_id: "tour-1",
  tournament_name: "政大校園盃",
  game_name: "特戰英豪",
  registration_status: "disqualified",
  waitlist_position: null,
  waitlist_reason: null,
  representative_backfill: null,
  waitlist_phase: null,
}

function mockReason(data: { reason: string; handled_at: string } | null) {
  return vi
    .spyOn(DisputesService, "readTeamDisqualification")
    .mockResolvedValue({ data } as ReasonResult)
}

beforeAll(async () => {
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: ["/"] }),
  })
  await Promise.all(
    (
      [
        "/teams/$teamId",
        "/me/teams",
        "/tournaments/$tournamentId/matches/$matchId",
      ] as const
    ).map((path) => router.loadRouteChunk(router.routesByPath[path])),
  )
}, 30_000)

describe("取消資格的處理理由（S17、S12）", () => {
  it("S17：取消資格徽章與主辦方的處理理由、處理時間", async () => {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }))
    signInAs()
    vi.spyOn(RegistrationService, "readTeam").mockResolvedValue({
      data: TEAM,
    } as ReadTeamResult)
    const read = mockReason({
      reason: REASON,
      handled_at: "2026-11-09T06:30:00Z",
    })
    renderApp("/teams/team-1")

    expect(await screen.findByText(REASON)).toBeInTheDocument()
    expect(read).toHaveBeenCalledWith({ path: { team_id: "team-1" } })
    const header = screen
      .getByRole("heading", { name: "夜貓隊" })
      .closest("header")!
    expect(within(header).getByText("取消資格")).toBeInTheDocument()
    expect(within(header).getByText("主辦方的處理理由")).toBeInTheDocument()
    expect(
      within(header).getByText("處理時間：2026/11/09 14:30"),
    ).toBeInTheDocument()
  })

  it("S17：沒有取消資格時不查詢也不顯示理由", async () => {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }))
    signInAs()
    vi.spyOn(RegistrationService, "readTeam").mockResolvedValue({
      data: { ...TEAM, registration_status: "drawn" },
    } as ReadTeamResult)
    const read = mockReason(null)
    renderApp("/teams/team-1")

    await screen.findByRole("heading", { name: "夜貓隊" })
    expect(read).not.toHaveBeenCalled()
    expect(screen.queryByText("主辦方的處理理由")).toBeNull()
  })

  it("S17：理由為 null 或讀取失敗時不顯示理由區塊", async () => {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }))
    signInAs()
    vi.spyOn(RegistrationService, "readTeam").mockResolvedValue({
      data: TEAM,
    } as ReadTeamResult)
    const read = vi
      .spyOn(DisputesService, "readTeamDisqualification")
      .mockRejectedValue(
        httpError(403, {
          detail: {
            code: "TEAM_MEMBER_REQUIRED",
            message: "只有隊員可以查看。",
          },
        }),
      )
    renderApp("/teams/team-1")

    await screen.findByRole("heading", { name: "夜貓隊" })
    await waitFor(() => expect(read).toHaveBeenCalledTimes(1))
    expect(screen.queryByText("主辦方的處理理由")).toBeNull()
  })

  it("S12：取消資格的隊伍在卡片下方顯示理由（不在卡片連結裡）", async () => {
    signInAs()
    vi.spyOn(RegistrationService, "listMyTeams").mockResolvedValue({
      data: [CARD],
    } as MyTeamsResult)
    mockReason({ reason: REASON, handled_at: "2026-11-09T06:30:00Z" })
    renderApp("/me/teams")

    const reason = await screen.findByText(REASON)
    const card = screen.getByRole("link", { name: /夜貓隊/ })
    expect(within(card).getByText("取消資格")).toBeInTheDocument()
    expect(card).not.toContainElement(reason)
    expect(reason.closest("li")).toBe(card.closest("li"))
  })
})
