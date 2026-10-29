// 對戰樹的假資料產生器，給單元測試與 /dev/bracket 預覽頁共用；第二階段接上真資料後只留給測試。
// 結構照 D 的 backend/app/modules/competition/bracket.py（origin/story/4-1）：P＝不小於隊數的最小 2 的次方，
// 輪空位置以位元反轉平均分散，第一輪輪空的位置留空號，只編實際存在的場次，正取 4 隊以上才有季軍賽。

import type {
  BracketSide,
  MatchOutcome,
  MatchStatus,
  PublicBracket,
  PublicMatch,
  PublicTeamRef,
} from "./bracket-types"

export type BracketScenario =
  /** 剛抽籤：全部待開打 */
  | "scheduled"
  /** 進行中：第一輪已確認（含棄權、取消資格），第二輪各種狀態 */
  | "in_progress"
  /** 全部已確認 */
  | "finished"
  /** 一場準決賽雙方棄權：決賽輪空、季軍賽取消 */
  | "third_place_voided"

export const FIXTURE_TOURNAMENT_ID = "tournament-fixture"
/** 第一輪 2026-10-18（日）13:00（台北），之後每輪間隔 3 小時 */
const FIRST_ROUND_AT = Date.parse("2026-10-18T05:00:00Z")
const ROUND_INTERVAL_MS = 3 * 60 * 60 * 1000

const TEAM_NAMES = [
  "中興 Titan",
  "輔大 Blaze",
  "清大 Hydra",
  "交大 Nova",
  "台大 Phoenix",
  "成大 Kraken",
  "政大 Viper",
  "師大 Aurora",
  "中央 Vortex",
  "中正 Falcon",
  "中山 Tempest",
  "東華 Raven",
  "淡江 Specter",
  "逢甲 Comet",
  "元智 Onyx",
  "銘傳 Zephyr",
  "東海 Golem",
  "文化 Mirage",
  "世新 Pulse",
  "長庚 Cobra",
  "海大 Tidal",
  "北科 Forge",
  "台科 Circuit",
  "高師 Ember",
  "嘉大 Quasar",
  "暨南 Lynx",
  "宜大 Monsoon",
  "屏大 Saber",
  "彰師 Rune",
  "高大 Nimbus",
  "聯大 Halo",
  "金大 Drift",
]

type Source = { code: string; kind: "勝者" | "敗者" }

type Plan = {
  code: string
  roundNo: number
  position: number
  isThirdPlace: boolean
  next: { code: string; side: BracketSide } | null
  loserNext: { code: string; side: BracketSide } | null
  sourceA: Source | null
  sourceB: Source | null
  byeA: boolean
  byeB: boolean
}

function bitReverseOrder(count: number): number[] {
  const bits = Math.log2(count)
  const reverse = (x: number) =>
    bits === 0
      ? 0
      : Number.parseInt(
          x.toString(2).padStart(bits, "0").split("").reverse().join(""),
          2,
        )
  return [...Array(count).keys()].sort((a, b) => reverse(a) - reverse(b))
}

function byePairs(size: number, byeCount: number): Set<number> {
  if (byeCount === 0) return new Set()
  const quarter = size / 4
  const order = bitReverseOrder(quarter)
  const upper = order.slice(0, Math.min(byeCount, quarter))
  const lower = byeCount > quarter ? order.slice(0, byeCount - quarter) : []
  return new Set([...upper.map((j) => 2 * j), ...lower.map((j) => 2 * j + 1)])
}

export function roundName(roundNo: number, rounds: number): string {
  const teamsLeft = 2 ** (rounds - roundNo + 1)
  return teamsLeft === 2 ? "決賽" : `${teamsLeft} 強`
}

function planBracket(teamCount: number) {
  let size = 1
  while (size < teamCount) size *= 2
  const rounds = Math.log2(size)
  const byes = byePairs(size, size - teamCount)
  const hasThirdPlace = teamCount >= 4

  const positions = new Map<number, number[]>()
  positions.set(
    1,
    [...Array(size / 2).keys()].filter((i) => !byes.has(i)),
  )
  for (let r = 2; r <= rounds; r++)
    positions.set(r, [...Array(size / 2 ** r).keys()])

  const codes = new Map<string, string>()
  let n = 0
  for (let r = 1; r <= rounds; r++) {
    for (const pos of positions.get(r) ?? []) {
      n += 1
      codes.set(`${r}:${pos}`, `M${n}`)
    }
  }
  const thirdCode = hasThirdPlace ? `M${n + 1}` : null

  const plans: Plan[] = []
  for (let r = 1; r <= rounds; r++) {
    for (const pos of positions.get(r) ?? []) {
      let sourceA: Source | null = null
      let sourceB: Source | null = null
      let byeA = false
      let byeB = false
      if (r === 2) {
        if (byes.has(2 * pos)) byeA = true
        else sourceA = { code: codes.get(`1:${2 * pos}`)!, kind: "勝者" }
        if (byes.has(2 * pos + 1)) byeB = true
        else sourceB = { code: codes.get(`1:${2 * pos + 1}`)!, kind: "勝者" }
      } else if (r > 2) {
        sourceA = { code: codes.get(`${r - 1}:${2 * pos}`)!, kind: "勝者" }
        sourceB = { code: codes.get(`${r - 1}:${2 * pos + 1}`)!, kind: "勝者" }
      }
      const isFinal = r === rounds
      plans.push({
        code: codes.get(`${r}:${pos}`)!,
        roundNo: r,
        position: pos,
        isThirdPlace: false,
        next: isFinal
          ? null
          : {
              code: codes.get(`${r + 1}:${Math.floor(pos / 2)}`)!,
              side: pos % 2 === 0 ? "a" : "b",
            },
        loserNext:
          thirdCode !== null && r === rounds - 1
            ? { code: thirdCode, side: pos % 2 === 0 ? "a" : "b" }
            : null,
        sourceA,
        sourceB,
        byeA,
        byeB,
      })
    }
  }
  if (thirdCode !== null) {
    const semis = plans.filter((p) => p.roundNo === rounds - 1)
    plans.push({
      code: thirdCode,
      roundNo: rounds,
      position: 1,
      isThirdPlace: true,
      next: null,
      loserNext: null,
      sourceA: { code: semis[0].code, kind: "敗者" },
      sourceB: { code: semis[1].code, kind: "敗者" },
      byeA: false,
      byeB: false,
    })
  }
  return { rounds, plans }
}

type Result = {
  status: MatchStatus
  outcome?: MatchOutcome | null
  /** 勝方；雙方棄權與未確認時不必給 */
  winner?: BracketSide | null
  wins?: [number, number]
}

/** 依場次編號決定結果，讓同一個情境每次產生的資料都相同 */
function playedResult(index: number): Result {
  // 第 4、6 場分別是一方棄權、取消資格，其餘 BO3
  if (index === 3)
    return { status: "confirmed", outcome: "forfeit", winner: "b" }
  if (index === 5)
    return { status: "confirmed", outcome: "disqualified", winner: "a" }
  return {
    status: "confirmed",
    outcome: "played",
    winner: index % 3 === 1 ? "b" : "a",
    wins: index % 2 === 0 ? [2, 1] : [0, 2],
  }
}

function resultFor(
  scenario: BracketScenario,
  plan: Plan,
  index: number,
  rounds: number,
): Result | null {
  switch (scenario) {
    case "scheduled":
      return null
    case "finished":
      return playedResult(index)
    case "in_progress": {
      if (rounds === 1) return { status: "live", wins: [1, 1] }
      if (plan.roundNo === 1) return playedResult(index)
      if (plan.roundNo !== 2) return null
      // 第二輪：依位置輪流出現進行中、申訴期、申訴中、已確認
      switch (plan.position % 4) {
        case 0:
          return { status: "live", wins: [1, 1] }
        case 1:
          return {
            status: "appeal_window",
            outcome: "played",
            winner: "a",
            wins: [2, 1],
          }
        case 2:
          return {
            status: "appealed",
            outcome: "played",
            winner: "b",
            wins: [1, 2],
          }
        default:
          return playedResult(index)
      }
    }
    case "third_place_voided": {
      if (plan.isThirdPlace) return { status: "voided" }
      if (plan.roundNo === rounds)
        return { status: "confirmed", outcome: "walkover" }
      if (plan.roundNo === rounds - 1 && plan.position === 0)
        return { status: "confirmed", outcome: "double_forfeit" }
      return playedResult(index)
    }
  }
}

type BracketFixtureOptions = {
  teamCount: number
  scenario?: BracketScenario
}

/** 產生一份 PublicBracket 假資料；teamCount 2～32，同樣的參數每次產生相同的資料。 */
export function createBracketFixture({
  teamCount,
  scenario: requested = "scheduled",
}: BracketFixtureOptions): PublicBracket {
  if (teamCount < 2 || teamCount > TEAM_NAMES.length) {
    throw new Error(`teamCount 必須介於 2 與 ${TEAM_NAMES.length} 之間`)
  }
  // 少於 4 隊沒有季軍賽，「季軍賽取消」改用全部已確認
  const scenario =
    requested === "third_place_voided" && teamCount < 4 ? "finished" : requested
  const { rounds, plans } = planBracket(teamCount)
  const teams: PublicTeamRef[] = TEAM_NAMES.slice(0, teamCount).map(
    (name, i) => ({ id: `team-${i + 1}`, name }),
  )

  const matches = new Map<string, PublicMatch>()
  for (const plan of plans) {
    matches.set(plan.code, {
      id: `match-${plan.code}`,
      code: plan.code,
      round_no: plan.roundNo,
      slot_no: plan.position + 1,
      is_third_place: plan.isThirdPlace,
      team_a: null,
      team_b: null,
      source_a: plan.sourceA && `${plan.sourceA.code} ${plan.sourceA.kind}`,
      source_b: plan.sourceB && `${plan.sourceB.code} ${plan.sourceB.kind}`,
      bye_side: plan.byeA ? "a" : plan.byeB ? "b" : null,
      scheduled_at: new Date(
        FIRST_ROUND_AT + (plan.roundNo - 1) * ROUND_INTERVAL_MS,
      ).toISOString(),
      status: "scheduled",
      outcome: null,
      winner_id: null,
      wins_a: 0,
      wins_b: 0,
    })
  }

  // 抽籤：第一輪每場兩隊，再排輪空隊伍
  const pool = teams[Symbol.iterator]()
  const take = () => pool.next().value ?? null
  for (const plan of plans) {
    if (plan.roundNo !== 1) continue
    const match = matches.get(plan.code)!
    match.team_a = take()
    match.team_b = take()
  }
  for (const plan of plans) {
    const match = matches.get(plan.code)!
    if (plan.byeA) match.team_a = take()
    if (plan.byeB) match.team_b = take()
  }

  const seat = (
    target: { code: string; side: BracketSide } | null,
    team: PublicTeamRef | null,
  ) => {
    if (target === null) return
    const match = matches.get(target.code)!
    if (target.side === "a") {
      match.team_a = team
      match.source_a = null
    } else {
      match.team_b = team
      match.source_b = null
    }
  }

  // 依編號順序結算，勝隊進下一場、準決賽敗隊進季軍賽
  plans.forEach((plan, index) => {
    const result = resultFor(scenario, plan, index, rounds)
    if (result === null) return
    const match = matches.get(plan.code)!
    match.status = result.status
    match.outcome = result.outcome ?? null
    match.wins_a = result.wins?.[0] ?? 0
    match.wins_b = result.wins?.[1] ?? 0

    if (result.outcome === "walkover") {
      // 只有一方有隊伍，由它晉級
      const winner = match.team_a ?? match.team_b
      match.winner_id = winner?.id ?? null
      if (match.status === "confirmed") seat(plan.next, winner)
      return
    }
    if (result.outcome === "double_forfeit") {
      // 下一輪等它勝者的位置確定不會有隊伍：顯示「—」＋「輪空」；季軍賽的來源保留
      if (match.status === "confirmed") seat(plan.next, null)
      return
    }
    if (!result.winner) return
    const winner = result.winner === "a" ? match.team_a : match.team_b
    const loser = result.winner === "a" ? match.team_b : match.team_a
    match.winner_id = winner?.id ?? null
    if (match.status !== "confirmed") return
    seat(plan.next, winner)
    seat(plan.loserNext, loser)
  })

  return {
    tournament_id: FIXTURE_TOURNAMENT_ID,
    rounds,
    round_names: [...Array(rounds).keys()].map((i) => roundName(i + 1, rounds)),
    matches: [...matches.values()],
    updated_at: new Date(FIRST_ROUND_AT).toISOString(),
  }
}

/** 模擬一次輪詢變動：第一場進行中的比分加 1；沒有進行中的場次時，把第一場待開打的改為進行中。 */
export function simulateBracketChange(bracket: PublicBracket): PublicBracket {
  const matches = bracket.matches.map((m) => ({ ...m }))
  const live = matches.find((m) => m.status === "live")
  if (live) {
    live.wins_a += 1
  } else {
    const next = matches.find(
      (m) => m.status === "scheduled" && m.team_a !== null && m.team_b !== null,
    )
    if (next) {
      next.status = "live"
      next.wins_a = 0
      next.wins_b = 0
    }
  }
  return {
    ...bracket,
    matches,
    updated_at: new Date(Date.parse(bracket.updated_at) + 5000).toISOString(),
  }
}
