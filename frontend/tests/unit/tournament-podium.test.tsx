import { screen, waitFor, within } from "@testing-library/react"
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest"
import {
  CompetitionService,
  type PublicBracket,
  type PublicMatch,
  type PublicPodium,
  type PublicTournament,
  TournamentsService,
} from "@/client"
import { BracketTree } from "@/features/competition/BracketTree"
import { createBracketFixture } from "@/features/competition/bracket-fixtures"
import { matchPath } from "@/features/competition/match-source"
import {
  TournamentPodium,
  teamLastMatchId,
} from "@/features/competition/TournamentPodium"
import { renderApp } from "./auth-fixtures"
import { renderInRouter } from "./render-router"

type ReadTournamentResult = Awaited<
  ReturnType<typeof TournamentsService.readPublicTournament>
>
type ReadBracketResult = Awaited<
  ReturnType<typeof CompetitionService.readPublicBracket>
>

const TOURNAMENT_ID = "t-1"

function teamsOf(match: PublicMatch) {
  const [winner, loser] =
    match.winner_id === match.team_a?.id
      ? [match.team_a, match.team_b]
      : [match.team_b, match.team_a]
  return { winner, loser }
}

function finalOf(bracket: PublicBracket): PublicMatch {
  const final = bracket.matches.find(
    (match) => match.round_no === bracket.rounds && !match.is_third_place,
  )
  if (!final) throw new Error("fixture 沒有決賽")
  return final
}

function thirdPlaceOf(bracket: PublicBracket): PublicMatch | undefined {
  return bracket.matches.find((match) => match.is_third_place)
}

/** 依 fixture 的結果組出已結束賽事的對戰表；teamCount < 4 時沒有季軍賽 */
function finished(teamCount = 8): PublicBracket {
  const fixture = {
    ...createBracketFixture({ teamCount, scenario: "finished" }),
    tournament_id: TOURNAMENT_ID,
  }
  const final = teamsOf(finalOf(fixture))
  const thirdPlace = thirdPlaceOf(fixture)
  const podium: PublicPodium = {
    champion: final.winner,
    runner_up: final.loser,
    third_place: thirdPlace ? teamsOf(thirdPlace).winner : null,
  }
  return { ...fixture, podium }
}

function tournament(status: PublicTournament["status"]): PublicTournament {
  return {
    id: TOURNAMENT_ID,
    name: "期中盃",
    status,
    game_name: "特戰英豪",
    capacity: 16,
    registration_start: "2025-10-12T11:00:00Z",
    priority_end: "2025-10-13T11:00:00Z",
    registration_end: "2025-10-17T11:00:00Z",
    start_at: "2025-10-18T11:00:00Z",
    round_interval_minutes: 180,
    livestream_url: null,
  }
}

function mockApi(status: PublicTournament["status"], bracket: PublicBracket) {
  vi.spyOn(TournamentsService, "readPublicTournament").mockResolvedValue({
    data: tournament(status),
  } as unknown as ReadTournamentResult)
  return vi
    .spyOn(CompetitionService, "readPublicBracket")
    .mockResolvedValue({ data: bracket } as unknown as ReadBracketResult)
}

function cardOf(container: HTMLElement, matchId: string) {
  const card = container.querySelector<HTMLElement>(
    `[data-match-id="${matchId}"]`,
  )
  if (!card) throw new Error(`找不到場次卡 ${matchId}`)
  return card
}

function marksOf(card: HTMLElement) {
  return Array.from(
    card.querySelectorAll<HTMLElement>('[data-slot="bracket-mark-tag"]'),
  ).map((tag) => [tag.textContent, tag.dataset.tone])
}

beforeAll(async () => {
  await Promise.all([
    import("@/features/tournaments/TournamentPage"),
    import("@/features/competition/TournamentBracketPage"),
  ])
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe("teamLastMatchId", () => {
  it("取輪次最大的一場，不算已取消的場次", () => {
    const bracket = finished()
    const final = finalOf(bracket)
    const champion = teamsOf(final).winner?.id ?? ""
    expect(teamLastMatchId(bracket.matches, champion)).toBe(final.id)

    const voidedFinal = bracket.matches.map((match) =>
      match.id === final.id ? { ...match, status: "voided" as const } : match,
    )
    const last = teamLastMatchId(voidedFinal, champion)
    expect(last).not.toBeNull()
    expect(last).not.toBe(final.id)
  })

  it("找不到隊伍時回傳 null", () => {
    expect(teamLastMatchId(finished().matches, "nobody")).toBeNull()
  })
})

describe("Podium", () => {
  it("依序列出冠軍、亞軍、季軍，隊名連到該隊最後一場的 S4", async () => {
    const bracket = finished()
    await renderInRouter(<TournamentPodium bracket={bracket} />)

    const region = await screen.findByRole("region", { name: "賽事名次" })
    const rows = Array.from(
      region.querySelectorAll<HTMLElement>('[data-slot="podium-row"]'),
    )
    expect(rows.map((row) => marksOf(row))).toEqual([
      [["冠軍", "brand"]],
      [["亞軍", "default"]],
      [["季軍", "default"]],
    ])

    const final = finalOf(bracket)
    const thirdPlace = thirdPlaceOf(bracket) as PublicMatch
    const championName = bracket.podium?.champion?.name ?? ""
    const champion = within(rows[0]).getByRole("link", { name: championName })
    expect(champion).toHaveClass("text-heading-md")
    expect(champion).toHaveAttribute("href", matchPath(TOURNAMENT_ID, final.id))
    expect(
      within(rows[1]).getByRole("link", {
        name: bracket.podium?.runner_up?.name,
      }),
    ).toHaveAttribute("href", matchPath(TOURNAMENT_ID, final.id))
    const third = within(rows[2]).getByRole("link", {
      name: bracket.podium?.third_place?.name,
    })
    expect(third).toHaveClass("text-body")
    expect(third).toHaveAttribute(
      "href",
      matchPath(TOURNAMENT_ID, thirdPlace.id),
    )
  })

  it("手機直排、桌機三欄", async () => {
    await renderInRouter(<TournamentPodium bracket={finished()} />)
    const region = await screen.findByRole("region", { name: "賽事名次" })
    expect(region.querySelector('[data-slot="podium"]')).toHaveClass(
      "grid-cols-1",
      "md:grid-cols-3",
    )
  })

  it("沒有季軍賽時只列冠軍、亞軍", async () => {
    await renderInRouter(<TournamentPodium bracket={finished(3)} />)
    const region = await screen.findByRole("region", { name: "賽事名次" })
    expect(region.querySelectorAll('[data-slot="podium-row"]')).toHaveLength(2)
    expect(within(region).queryByText("季軍")).not.toBeInTheDocument()
  })

  it("找不到場次的隊伍只顯示隊名，不是連結", async () => {
    const bracket = finished()
    const ghost = { id: "ghost", name: "幽靈隊" }
    await renderInRouter(
      <TournamentPodium
        bracket={{
          ...bracket,
          podium: { champion: ghost, runner_up: null, third_place: null },
        }}
      />,
    )
    expect(await screen.findByText("幽靈隊")).toBeInTheDocument()
    expect(
      screen.queryByRole("link", { name: "幽靈隊" }),
    ).not.toBeInTheDocument()
  })

  it.each([
    ["賽事未結束", null],
    ["名次全部從缺", { champion: null, runner_up: null, third_place: null }],
  ])("%s時不顯示", async (_name, podium) => {
    await renderInRouter(
      <>
        <span>已渲染</span>
        <TournamentPodium bracket={{ ...finished(), podium }} />
      </>,
    )
    await screen.findByText("已渲染")
    expect(
      screen.queryByRole("region", { name: "賽事名次" }),
    ).not.toBeInTheDocument()
  })
})

describe("決賽與季軍賽卡的名次標記", () => {
  it("決賽標冠軍（brand）、亞軍，季軍賽只標季軍，其他場次不標", async () => {
    const bracket = finished()
    const { container } = await renderInRouter(
      <BracketTree bracket={bracket} />,
    )
    await screen.findAllByRole("article")

    const final = finalOf(bracket)
    const finalCard = cardOf(container, final.id)
    const finalMarks = marksOf(finalCard)
    expect(finalMarks).toContainEqual(["冠軍", "brand"])
    expect(finalMarks).toContainEqual(["亞軍", "default"])

    const thirdPlace = thirdPlaceOf(bracket) as PublicMatch
    expect(marksOf(cardOf(container, thirdPlace.id))).toEqual([
      ["季軍", "default"],
    ])

    const earlier = bracket.matches.find(
      (match) => match.round_no === 1 && !match.is_third_place,
    ) as PublicMatch
    expect(marksOf(cardOf(container, earlier.id))).toEqual([])
  })

  it("賽事未結束時不標名次", async () => {
    const bracket = { ...finished(), podium: null }
    const { container } = await renderInRouter(
      <BracketTree bracket={bracket} />,
    )
    await screen.findAllByRole("article")
    const marks = marksOf(cardOf(container, finalOf(bracket).id))
    expect(marks.map(([label]) => label)).not.toContain("冠軍")
  })

  it("季軍賽已取消：卡片保留「已取消」，不標季軍，也不算該隊最後一場", async () => {
    const fixture = {
      ...createBracketFixture({
        teamCount: 8,
        scenario: "third_place_voided",
      }),
      tournament_id: TOURNAMENT_ID,
    }
    const final = teamsOf(finalOf(fixture))
    const bracket: PublicBracket = {
      ...fixture,
      podium: {
        champion: final.winner,
        runner_up: final.loser,
        third_place: null,
      },
    }
    const { container } = await renderInRouter(
      <BracketTree bracket={bracket} />,
    )
    await screen.findAllByRole("article")
    const thirdPlace = thirdPlaceOf(bracket) as PublicMatch
    const card = cardOf(container, thirdPlace.id)
    expect(card).toHaveAttribute("data-status", "voided")
    expect(within(card).getByText("已取消")).toBeInTheDocument()
    expect(marksOf(card).map(([label]) => label)).not.toContain("季軍")
  })

  it("整張卡連結的可及名稱也帶名次", async () => {
    const bracket = finished()
    await renderInRouter(
      <BracketTree
        bracket={bracket}
        matchHref={(id) => matchPath(TOURNAMENT_ID, id)}
      />,
    )
    const link = await screen.findByRole("link", { name: /（冠軍）/ })
    expect(link).toHaveAttribute(
      "href",
      matchPath(TOURNAMENT_ID, finalOf(bracket).id),
    )
  })
})

describe("S2、S3 頁面", () => {
  it("S3：賽事結束時 Podium 在對戰樹上方", async () => {
    mockApi("finished", finished())
    renderApp(`/tournaments/${TOURNAMENT_ID}/bracket`)

    const region = await screen.findByRole("region", { name: "賽事名次" })
    const tree = document.querySelector('[data-slot="bracket-tree"]')
    expect(tree).not.toBeNull()
    expect(
      region.compareDocumentPosition(tree as Node) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy()
  })

  it("S2：賽事結束時最上方顯示 Podium", async () => {
    const read = mockApi("finished", finished())
    renderApp(`/tournaments/${TOURNAMENT_ID}`)

    const region = await screen.findByRole("region", { name: "賽事名次" })
    expect(read).toHaveBeenCalledWith({
      path: { tournament_id: TOURNAMENT_ID },
    })
    const heading = await screen.findByRole("heading", { name: "期中盃" })
    expect(
      region.compareDocumentPosition(heading) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy()
  })

  it("S2：賽事未結束時不抓對戰表、不顯示 Podium", async () => {
    const read = mockApi("ongoing", {
      ...finished(),
      podium: null,
    })
    renderApp(`/tournaments/${TOURNAMENT_ID}`)

    await screen.findByRole("heading", { name: "期中盃" })
    await waitFor(() =>
      expect(TournamentsService.readPublicTournament).toHaveBeenCalled(),
    )
    expect(read).not.toHaveBeenCalled()
    expect(
      screen.queryByRole("region", { name: "賽事名次" }),
    ).not.toBeInTheDocument()
  })
})
