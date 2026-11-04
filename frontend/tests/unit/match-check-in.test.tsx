import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { useState } from "react"
import { describe, expect, it, vi } from "vitest"

import {
  type CheckInStatus,
  CompetitionService,
  type PublicMatchDetail,
} from "@/client"
import {
  CHECK_IN_LEAD_MS,
  checkInCountdownPhase,
  MatchCheckIn,
  showsCheckIn,
  TOO_EARLY_RETRY_MS,
  tooEarlyRetryInterval,
} from "@/features/competition/MatchCheckIn"
import { formatMatchDateTime } from "@/features/competition/match-time"
import { ACCESS_TOKEN_STORAGE_KEY } from "@/features/identity/auth"
import { httpError } from "./helpers"
import { matchDetail, TEAM_A, TEAM_B } from "./match-detail-fixture"

type ReadStatusResult = Awaited<
  ReturnType<typeof CompetitionService.readCheckInStatus>
>
type CheckInResult = Awaited<ReturnType<typeof CompetitionService.checkIn>>

const MINUTE = 60 * 1000

function iso(ms: number) {
  return new Date(ms).toISOString()
}

/** 預定開始在現在之後 offset 毫秒的待開打場次 */
function scheduledIn(
  offset: number,
  overrides: Partial<PublicMatchDetail> = {},
) {
  return matchDetail({ scheduled_at: iso(Date.now() + offset), ...overrides })
}

function mockStatus(status: Partial<CheckInStatus> & { opens_at: string }) {
  return vi.spyOn(CompetitionService, "readCheckInStatus").mockResolvedValue({
    data: { side: null, reason: null, ...status },
  } as unknown as ReadStatusResult)
}

function signIn() {
  window.localStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, "token-1")
}

/** 持有場次資料的外框：refresh 把資料換成 next（模擬重抓後伺服器回傳的新狀態） */
function renderCheckIn(
  initial: PublicMatchDetail,
  next?: () => PublicMatchDetail,
) {
  const refresh = vi.fn()
  function Harness() {
    const [detail, setDetail] = useState(initial)
    refresh.mockImplementation(async () => {
      if (next) setDetail(next())
    })
    return <MatchCheckIn detail={detail} refresh={refresh} />
  }
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  render(
    <QueryClientProvider client={queryClient}>
      <Harness />
    </QueryClientProvider>,
  )
  return { refresh }
}

function teamColumn(name: string) {
  const column = screen
    .getAllByRole("listitem")
    .find((item) => within(item).queryByText(name))
  if (!column) throw new Error(`找不到 ${name} 那一欄`)
  return column
}

describe("報到倒數的階段", () => {
  const opensAt = "2026-10-18T04:30:00Z"
  const scheduledAt = "2026-10-18T05:00:00Z"
  const forfeitDeadline = "2026-10-18T05:15:00Z"
  const at = (time: string) => Date.parse(time)

  it("開放前：「報到開放」→ 開放時間（muted）", () => {
    expect(
      checkInCountdownPhase({
        opensAt,
        scheduledAt,
        forfeitDeadline,
        now: at("2026-10-18T04:00:00Z"),
      }),
    ).toEqual({
      label: "報到開放",
      deadline: opensAt,
      variant: "muted",
      suffix: "起可報到",
    })
  })

  it("開放後：「距預定開始」→ 預定時間（live）", () => {
    expect(
      checkInCountdownPhase({
        opensAt,
        scheduledAt,
        forfeitDeadline,
        now: at(opensAt),
      }),
    ).toMatchObject({
      label: "距預定開始",
      deadline: scheduledAt,
      variant: "live",
    })
  })

  it("過預定時間：「棄權期限」→ 棄權期限（appeal）", () => {
    expect(
      checkInCountdownPhase({
        opensAt,
        scheduledAt,
        forfeitDeadline,
        now: at(scheduledAt),
      }),
    ).toMatchObject({
      label: "棄權期限",
      deadline: forfeitDeadline,
      variant: "appeal",
    })
  })

  it("沒有棄權期限、或已過棄權期限：不顯示倒數", () => {
    const now = at("2026-10-18T05:20:00Z")
    expect(
      checkInCountdownPhase({ opensAt, scheduledAt, forfeitDeadline, now }),
    ).toBeNull()
    expect(
      checkInCountdownPhase({
        opensAt,
        scheduledAt,
        forfeitDeadline: null,
        now: at(scheduledAt),
      }),
    ).toBeNull()
  })
})

describe("伺服器仍回 too_early 時的重抓", () => {
  const opensAt = "2026-11-04T10:00:00.000Z"
  const opens = Date.parse(opensAt)

  it("本機已過開放時間、伺服器仍回 too_early：每 5 秒重抓", () => {
    expect(
      tooEarlyRetryInterval({ reason: "too_early", opens_at: opensAt }, opens),
    ).toBe(TOO_EARLY_RETRY_MS)
  })

  it("還沒到開放時間、或伺服器已放行：不定時重抓", () => {
    expect(
      tooEarlyRetryInterval(
        { reason: "too_early", opens_at: opensAt },
        opens - 1,
      ),
    ).toBe(false)
    expect(
      tooEarlyRetryInterval({ reason: null, opens_at: opensAt }, opens + 1),
    ).toBe(false)
    expect(tooEarlyRetryInterval(undefined, opens + 1)).toBe(false)
  })
})

describe("報到面板的去留", () => {
  it("待開打一律顯示，隊伍未定也顯示（面板自己停用）", () => {
    expect(showsCheckIn(matchDetail({ status: "scheduled" }))).toBe(true)
    expect(
      showsCheckIn(matchDetail({ status: "scheduled", team_b: null })),
    ).toBe(true)
  })

  it("離開待開打：兩隊都有隊伍才留下報到時間", () => {
    expect(showsCheckIn(matchDetail({ status: "confirmed" }))).toBe(true)
  })

  it("已取消的季軍賽、輪空直接確認的場次：不顯示", () => {
    expect(
      showsCheckIn(
        matchDetail({ status: "voided", team_a: null, team_b: null }),
      ),
    ).toBe(false)
    expect(
      showsCheckIn(
        matchDetail({ status: "confirmed", outcome: "walkover", team_b: null }),
      ),
    ).toBe(false)
  })
})

describe("S4 報到面板的資料轉接", () => {
  it("未登入觀眾：顯示兩隊報到狀態與倒數，沒有按鈕，不呼叫需登入的 API", async () => {
    const readStatus = vi.spyOn(CompetitionService, "readCheckInStatus")
    const detail = scheduledIn(2 * 60 * MINUTE, {
      check_in_a_at: "2026-10-18T04:45:00Z",
    })
    renderCheckIn(detail)

    expect(within(teamColumn(TEAM_A.name)).getByText("已報到 12:45"))
    expect(within(teamColumn(TEAM_B.name)).getByText("未報到"))
    expect(screen.queryByRole("button", { name: "報到" })).toBeNull()
    // 開放時間由預定時間推算（前 30 分鐘）
    expect(screen.getByText("報到開放")).toBeInTheDocument()
    const opensAt = iso(Date.parse(detail.scheduled_at) - CHECK_IN_LEAD_MS)
    expect(
      screen.getByText(`${formatMatchDateTime(opensAt)} 起可報到`),
    ).toBeInTheDocument()
    expect(readStatus).not.toHaveBeenCalled()
  })

  it("隊長可報到：按「報到」後重抓，顯示「已報到 HH:mm」", async () => {
    signIn()
    const detail = scheduledIn(10 * MINUTE)
    const status = mockStatus({
      side: "a",
      reason: null,
      opens_at: iso(Date.parse(detail.scheduled_at) - CHECK_IN_LEAD_MS),
    })
    const checkIn = vi
      .spyOn(CompetitionService, "checkIn")
      .mockResolvedValue({ data: {} } as unknown as CheckInResult)
    const { refresh } = renderCheckIn(detail, () => ({
      ...detail,
      check_in_a_at: "2026-10-18T04:52:00Z",
      updated_at: "2026-10-18T04:52:00Z",
    }))

    const button = await screen.findByRole("button", { name: "報到" })
    expect(button).toBeEnabled()
    // 開放後倒數距預定開始
    expect(screen.getByText("距預定開始")).toBeInTheDocument()
    status.mockResolvedValue({
      data: {
        side: "a",
        reason: "already_checked_in",
        opens_at: detail.scheduled_at,
      },
    } as unknown as ReadStatusResult)
    await userEvent.click(button)

    expect(checkIn).toHaveBeenCalledWith({
      path: { tournament_id: "t1", match_id: "match-M3" },
    })
    expect(refresh).toHaveBeenCalled()
    expect(
      await within(teamColumn(TEAM_A.name)).findByText("已報到 12:52"),
    ).toBeInTheDocument()
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "報到" })).toBeNull(),
    )
  })

  it("報到被拒（409）：面板顯示伺服器訊息，不重抓", async () => {
    signIn()
    const detail = scheduledIn(10 * MINUTE)
    mockStatus({ side: "b", reason: null, opens_at: detail.scheduled_at })
    vi.spyOn(CompetitionService, "checkIn").mockRejectedValue(
      httpError(409, {
        detail: { code: "CHECK_IN_CLOSED", message: "報到已截止。" },
      }),
    )
    const { refresh } = renderCheckIn(detail)

    await userEvent.click(await screen.findByRole("button", { name: "報到" }))

    expect(await screen.findByText("報到已截止。")).toBeInTheDocument()
    expect(refresh).not.toHaveBeenCalled()
  })

  it("隊長太早：按鈕停用，寫「{時間} 起可報到」", async () => {
    signIn()
    const detail = scheduledIn(2 * 60 * MINUTE)
    const opensAt = iso(Date.parse(detail.scheduled_at) - CHECK_IN_LEAD_MS)
    mockStatus({ side: "a", reason: "too_early", opens_at: opensAt })
    renderCheckIn(detail)

    expect(await screen.findByRole("button", { name: "報到" })).toBeDisabled()
    // 按鈕下方的說明與倒數下方的絕對時間各一次
    expect(
      screen.getAllByText(`${formatMatchDateTime(opensAt)} 起可報到`).length,
    ).toBeGreaterThanOrEqual(1)
  })

  it("過了預定時間：倒數改為公開單場的棄權期限；沒有棄權期限就不顯示倒數", async () => {
    const forfeitDeadline = iso(Date.now() + 10 * MINUTE)
    renderCheckIn(
      scheduledIn(-5 * MINUTE, { forfeit_deadline: forfeitDeadline }),
    )
    expect(screen.getByText("棄權期限")).toBeInTheDocument()
    expect(
      screen.getByText(`${formatMatchDateTime(forfeitDeadline)} 截止`),
    ).toBeInTheDocument()
    cleanup()

    renderCheckIn(scheduledIn(-5 * MINUTE, { forfeit_deadline: null }))
    expect(screen.queryByText("棄權期限")).toBeNull()
    expect(screen.queryByText("距預定開始")).toBeNull()
  })

  it("兩隊未確定：面板停用、說明「對手確定後才能報到」，不顯示倒數", async () => {
    signIn()
    const detail = scheduledIn(10 * MINUTE, {
      team_b: null,
      source_b: "M4 勝者",
    })
    mockStatus({
      side: null,
      reason: "teams_pending",
      opens_at: detail.scheduled_at,
    })
    renderCheckIn(detail)

    expect(await screen.findByText("對手確定後才能報到")).toBeInTheDocument()
    expect(screen.getByText("待定")).toBeInTheDocument()
    expect(document.querySelector("[data-slot=countdown]")).toBeNull()
  })

  it("離開待開打：只留報到時間，不顯示倒數與按鈕", async () => {
    signIn()
    const detail = scheduledIn(-10 * MINUTE, {
      status: "live",
      check_in_a_at: "2026-10-18T04:40:00Z",
      check_in_b_at: "2026-10-18T04:41:00Z",
    })
    mockStatus({
      side: "a",
      reason: "not_checkable",
      opens_at: detail.scheduled_at,
    })
    renderCheckIn(detail)

    expect(
      await within(teamColumn(TEAM_B.name)).findByText("已報到 12:41"),
    ).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "報到" })).toBeNull()
    expect(document.querySelector("[data-slot=countdown]")).toBeNull()
  })
})
