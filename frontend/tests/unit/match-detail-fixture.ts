import type { PublicMatch } from "@/features/competition/bracket-types"
import type { PublicMatchDetail } from "@/features/competition/match-types"

export const TEAM_A = { id: "team-a", name: "成大 Kraken" }
export const TEAM_B = { id: "team-b", name: "北科 Ember" }

/** 單元測試用的一場比賽：預設是 32 強 M3、隊伍已定、待開打、沒有局 */
export function publicMatch(overrides: Partial<PublicMatch> = {}): PublicMatch {
  return {
    id: "match-M3",
    code: "M3",
    round_no: 1,
    slot_no: 3,
    is_third_place: false,
    team_a: TEAM_A,
    team_b: TEAM_B,
    source_a: null,
    source_b: null,
    bye_side: null,
    // 台北時間 2026/10/18（日）13:00
    scheduled_at: "2026-10-18T05:00:00Z",
    status: "scheduled",
    outcome: null,
    winner_id: null,
    wins_a: 0,
    wins_b: 0,
    ...overrides,
  }
}

export function matchDetail(
  overrides: Partial<PublicMatchDetail> = {},
): PublicMatchDetail {
  return {
    ...publicMatch(),
    tournament: { id: "t1", name: "2026 秋季校際盃" },
    game_name: "特戰英豪",
    best_of: 3,
    score_type: "rounds",
    round_name: "32 強",
    games: [],
    same_round: [],
    appeal_deadline: null,
    updated_at: "2026-10-18T05:00:00Z",
    ...overrides,
  }
}
