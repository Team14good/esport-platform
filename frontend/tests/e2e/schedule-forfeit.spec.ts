// FR-23（抽籤後自動排程、順延提示、主辦方改時間並通知）與 FR-25（過期未報到判棄權、進入申訴期）的端對端演練。
// 4 隊小賽事：預設 BO1、第 1 輪（4 強）另設 BO3，第 1 輪的最小間隔比每輪間隔長，所以第 2 輪會被順延。
// 關鍵步驟走畫面；組隊走公開 API（support/bulk.ts）；棄權期限等不了真實時間，改資料庫（support/db.ts）後
// 由真的 worker 判定。
import { logIn, platformAdmin, uniqueSuffix } from "./support/accounts"
import {
  apiCheckIn,
  type BulkTeam,
  createRegisteredTeams,
  fetchBracket,
  fetchRegistrationStatus,
  findTeam,
  playableMatches,
  teamsOf,
  waitForMatchStatus,
} from "./support/bulk"
import {
  endPriorityWindow,
  expireAppealWindows,
  expireForfeitDeadlines,
  openCheckIn,
} from "./support/db"
import { type NewRoleContext, rolePage } from "./support/drawn"
import {
  addGame,
  createTournament,
  minRoundIntervalMinutes,
} from "./support/drill"
import { API_URL } from "./support/env"
import { expect, test } from "./support/fixtures"
import type { GameConfig } from "./support/games"
import { expectNoHorizontalScroll } from "./support/layout"
import {
  bracketCardsOf,
  drawBracket,
  expectRegistrationAccepted,
  submitRegistration,
} from "./support/matchday"
import { createOrganizer } from "./support/organizer"

/** 預設 BO1；第 1 輪另設 BO3（見 setUpRegisteredTournament），4 隊、每隊 2 人。 */
const SMALL_GAME: GameConfig = {
  key: "schedule-forfeit",
  name: "排程競技場",
  starters: 2,
  substitutes: 0,
  defaultBestOf: 1,
  minutesPerGame: 20,
  scoreType: "win_loss",
  ranks: [
    { name: "新手", points: 1 },
    { name: "老手", points: 2 },
    { name: "高手", points: 3 },
  ],
  teamCount: 4,
  sampleGameScore: null,
}

/** 第 1 輪（4 強）改成 BO3 後的最小間隔（分鐘）：與 S26 的提示用同一個公式，BO 換成 3 */
const ROUND_ONE_BEST_OF = 3
const ROUND_ONE_MIN_GAP_MINUTES = minRoundIntervalMinutes({
  ...SMALL_GAME,
  defaultBestOf: ROUND_ONE_BEST_OF,
})

const MINUTE_MS = 60_000
const HOUR_MS = 60 * MINUTE_MS
const TAIPEI_OFFSET_MS = 8 * HOUR_MS
const WEEKDAYS = ["日", "一", "二", "三", "四", "五", "六"]

/** `datetime-local` 的值（台北時間，`YYYY-MM-DDTHH:mm`）。 */
function toTaipeiLocal(ms: number): string {
  return new Date(ms + TAIPEI_OFFSET_MS).toISOString().slice(0, 16)
}

/** 與畫面相同的場次時間格式（features/competition/match-time.ts）：「10/17（六）11:52」，跨年加年份。 */
function matchTimeText(iso: string): string {
  const shifted = (ms: number) => new Date(ms + TAIPEI_OFFSET_MS)
  const t = shifted(Date.parse(iso))
  const pad = (n: number) => String(n).padStart(2, "0")
  const date = `${t.getUTCMonth() + 1}/${t.getUTCDate()}（${WEEKDAYS[t.getUTCDay()]}）${pad(t.getUTCHours())}:${pad(t.getUTCMinutes())}`
  return t.getUTCFullYear() === shifted(Date.now()).getUTCFullYear()
    ? date
    : `${t.getUTCFullYear()}/${date}`
}

/** 通知內文的時間格式（backend/app/modules/notifications/rules.py 的 `_format_time`）：「10/18（六）19:00」，月日補零、不含年。 */
function notificationTimeText(ms: number): string {
  const t = new Date(ms + TAIPEI_OFFSET_MS)
  const pad = (n: number) => String(n).padStart(2, "0")
  return `${pad(t.getUTCMonth() + 1)}/${pad(t.getUTCDate())}（${WEEKDAYS[t.getUTCDay()]}）${pad(t.getUTCHours())}:${pad(t.getUTCMinutes())}`
}

/** 這個帳號的通知（API，內文不會顯示在通知列表上）。 */
async function fetchNotifications(token: string) {
  const response = await fetch(`${API_URL}/api/v1/notifications`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok) throw new Error(`GET /notifications → ${response.status}`)
  const page = (await response.json()) as {
    items: { title: string; body: string }[]
  }
  return page.items
}

/** 等 worker 把場次處理成 `status`；逾時時說明場次卡在哪個狀態。 */
async function waitForStatusOrExplain(
  tournamentId: string,
  match: { id: string; code: string },
  status: Parameters<typeof waitForMatchStatus>[2],
  timeoutMs: number,
) {
  try {
    await waitForMatchStatus(tournamentId, [match.id], status, timeoutMs)
  } catch (error) {
    const current = (await fetchBracket(tournamentId)).matches.find(
      (candidate) => candidate.id === match.id,
    )?.status
    throw Object.assign(
      new Error(
        `等了 ${timeoutMs / 1000} 秒，場次 ${match.code} 仍是「${current}」，沒有變成「${status}」`,
      ),
      { cause: error },
    )
  }
}

/**
 * 平台管理員新增遊戲、主辦方建立賽事並把 4 強設成 BO3（S28）、4 隊報名且全員正取。
 * 還沒抽籤：抽籤是各測試要走畫面的步驟。
 */
async function setUpRegisteredTournament(newRoleContext: NewRoleContext) {
  const suffix = uniqueSuffix()
  const gameName = `${SMALL_GAME.name} ${suffix}`
  const tournamentName = `E2E 排程棄權賽 ${suffix}`
  const adminPage = await (await newRoleContext("平台管理員")).newPage()
  const organizerPage = await (await newRoleContext("主辦方")).newPage()
  let tournamentId = ""
  let teams: BulkTeam[] = []

  await test.step("平台管理員新增遊戲，主辦方建立賽事", async () => {
    await logIn(adminPage, platformAdmin())
    await addGame(adminPage, SMALL_GAME, gameName)
    await createOrganizer(organizerPage, adminPage)
    tournamentId = await createTournament(organizerPage, SMALL_GAME, {
      gameName,
      tournamentName,
    })
  })

  await test.step("主辦方在 S28 把 4 強改成 BO3，每輪間隔仍是 BO1 的最小間隔", async () => {
    await organizerPage.goto(`/organizer/tournaments/${tournamentId}/settings`)
    await organizerPage.getByRole("button", { name: "分輪 BO" }).click()
    const roundOne = organizerPage.getByRole("combobox", {
      name: "4 強",
      exact: true,
    })
    await roundOne.click()
    await organizerPage
      .getByRole("option", { name: `BO${ROUND_ONE_BEST_OF}`, exact: true })
      .click()
    await expect(roundOne).toHaveText(`BO${ROUND_ONE_BEST_OF}`)
    await organizerPage
      .getByRole("button", { name: "儲存設定", exact: true })
      .click()
    await expect(organizerPage.getByText("已儲存設定。")).toBeVisible()
    await expectNoHorizontalScroll(organizerPage)
  })

  await test.step("4 隊報名，優先期結束後 worker 分配，全員正取", async () => {
    teams = await createRegisteredTeams(tournamentId, SMALL_GAME, suffix)
    const captainPage = await rolePage(
      newRoleContext,
      "第一隊隊長",
      teams[0].captain.account,
    )
    await submitRegistration(captainPage, teams[0].id)
    await endPriorityWindow(tournamentId)
    await expect
      .poll(() => fetchRegistrationStatus(teams[0]), {
        timeout: 90_000,
        intervals: [2_000],
      })
      .toBe("accepted")
    const statuses = await Promise.all(teams.map(fetchRegistrationStatus))
    expect(new Set(statuses)).toEqual(new Set(["accepted"]))
    await expectRegistrationAccepted(captainPage, teams[0].id)
    await captainPage.close()
  })

  return { tournamentId, tournamentName, teams, organizerPage }
}

test("抽籤後 S27 提示順延的輪次，S30 排出各場時間，主辦方改時間後隊長收到通知", {
  tag: ["@story-4.1", "@story-4.3", "@FR-19", "@FR-23", "@NFR-7"],
}, async ({ newRoleContext }) => {
  test.setTimeout(10 * 60_000)
  const { tournamentId, tournamentName, teams, organizerPage } =
    await setUpRegisteredTournament(newRoleContext)

  await test.step("主辦方在 S27 抽籤，看到第 2 輪被順延的提示", async () => {
    await drawBracket(organizerPage, tournamentId)
    await expect(
      organizerPage.getByText(
        "第 2 輪（決賽）因前一輪 BO 數較多已順延開始時間，請到場次管理確認。",
        { exact: true },
      ),
    ).toBeVisible({ timeout: 15_000 })
    await expectNoHorizontalScroll(organizerPage)
  })

  const bracket = await fetchBracket(tournamentId)
  const roundOne = bracket.matches.filter((match) => match.round_no === 1)
  const roundTwo = bracket.matches.filter((match) => match.round_no === 2)
  expect(roundOne.length).toBeGreaterThan(0)
  expect(roundTwo.length).toBeGreaterThan(0)
  const target = roundOne[0]
  const { teamA, teamB } = teamsOf(target)
  const originalAt = Date.parse(target.scheduled_at)
  // 第 2 輪的預期時間：第 1 輪最晚的開始時間＋第 1 輪（BO3）的最小間隔（比每輪間隔長，所以被順延）
  const roundOneLatestAt = Math.max(
    ...roundOne.map((match) => Date.parse(match.scheduled_at)),
  )
  const roundTwoExpectedText = matchTimeText(
    new Date(
      roundOneLatestAt + ROUND_ONE_MIN_GAP_MINUTES * MINUTE_MS,
    ).toISOString(),
  )

  await test.step("S30 列出每場的時間，第 2 輪是第 1 輪最晚開始時間加 BO3 的最小間隔", async () => {
    await organizerPage.goto(`/organizer/tournaments/${tournamentId}/matches`)
    await expect(
      organizerPage.getByRole("heading", { name: "場次管理", level: 1 }),
    ).toBeVisible()
    const rows = organizerPage
      .locator(
        "[data-slot=data-table] tbody tr, [data-slot=data-table-cards] > li",
      )
      .filter({ visible: true })
    await expect(rows).toHaveCount(bracket.matches.length)
    // 第 1 輪每一場顯示自己的時間
    for (const match of roundOne) {
      await expect(
        rows
          .filter({ hasText: match.code })
          .filter({ hasText: matchTimeText(match.scheduled_at) }),
      ).not.toHaveCount(0)
    }
    // 第 2 輪的決賽與季軍賽都顯示預期時間
    for (const label of ["決賽", "季軍賽"]) {
      await expect(rows.filter({ hasText: label })).toContainText(
        roundTwoExpectedText,
      )
    }
    await expectNoHorizontalScroll(organizerPage)
  })

  const newAt = originalAt - 2 * HOUR_MS
  await test.step("主辦方在 S30 把第 1 輪一場提前 2 小時，列表顯示新時間", async () => {
    const row = organizerPage
      .locator(
        "[data-slot=data-table] tbody tr, [data-slot=data-table-cards] > li",
      )
      .filter({ visible: true })
      .filter({ hasText: teamA.name })
    await expect(row).toContainText(matchTimeText(target.scheduled_at))
    await row.getByRole("button", { name: "修改時間", exact: true }).click()
    const dialog = organizerPage.getByRole("dialog", { name: "修改場次時間" })
    await expect(dialog).toBeVisible()
    await dialog
      .getByLabel("新的開打時間（台北時間）", { exact: true })
      .fill(toTaipeiLocal(newAt))
    await dialog.getByRole("button", { name: "儲存時間", exact: true }).click()
    await expect(dialog).toBeHidden()
    await expect(row).toContainText(
      matchTimeText(new Date(newAt).toISOString()),
    )
    await expect(row).not.toContainText(matchTimeText(target.scheduled_at))
    await expectNoHorizontalScroll(organizerPage)
  })

  await test.step("兩隊隊長都在通知中心看到「場次時間已變更」，內文有場次與新時間", async () => {
    for (const [role, team] of [
      ["A 隊隊長", teamA],
      ["B 隊隊長", teamB],
    ] as const) {
      const captain = findTeam(teams, team.id).captain
      const captainPage = await rolePage(newRoleContext, role, captain.account)
      await captainPage.goto("/notifications")
      await expect(
        captainPage.getByRole("heading", { name: "通知", level: 1 }),
      ).toBeVisible()
      // 事件由 worker 輪詢分派（預設每 20 秒）；重新整理直到通知出現
      const notice = captainPage.getByRole("button", { name: /場次時間已變更/ })
      await expect(async () => {
        await captainPage.reload()
        await expect(notice.first()).toBeVisible({ timeout: 5_000 })
      }).toPass({ timeout: 90_000, intervals: [5_000] })
      await expectNoHorizontalScroll(captainPage)
      // 列表只顯示標題；內文（場次與新時間）從 API 讀
      const bodies = (await fetchNotifications(captain.token))
        .filter((item) => item.title === "場次時間已變更")
        .map((item) => item.body)
      expect(bodies).toContain(
        `「${tournamentName}」場次 ${target.code}的時間改為 ${notificationTimeText(newAt)}。`,
      )
      await captainPage.close()
    }
  })
})

test("一隊報到、另一隊逾期未報到，worker 判棄權，單場頁與對戰表顯示結果並進入申訴期", {
  tag: ["@story-5.2", "@story-5.8", "@FR-25", "@NFR-7"],
}, async ({ newRoleContext }) => {
  test.setTimeout(10 * 60_000)
  const { tournamentId, teams, organizerPage } =
    await setUpRegisteredTournament(newRoleContext)
  await drawBracket(organizerPage, tournamentId)

  const bracket = await fetchBracket(tournamentId)
  const round = playableMatches(bracket, 1)
  expect(round.length).toBeGreaterThan(0)
  const match = round[0]
  const { teamA, teamB } = teamsOf(match)

  await test.step("只有 A 隊隊長報到，棄權期限改成已過", async () => {
    await openCheckIn([match.id])
    await apiCheckIn(tournamentId, match.id, findTeam(teams, teamA.id).captain)
    await expireForfeitDeadlines([match.id])
  })

  await test.step("worker 判棄權，場次進入申訴期", async () => {
    await waitForStatusOrExplain(tournamentId, match, "appeal_window", 90_000)
    const judged = (await fetchBracket(tournamentId)).matches.find(
      (candidate) => candidate.id === match.id,
    )
    expect(judged?.outcome).toBe("forfeit")
    expect(judged?.winner_id).toBe(teamA.id)
  })

  await test.step("單場頁：B 隊標示棄權、場次進入申訴期", async () => {
    const spectator = await (await newRoleContext("觀眾")).newPage()
    await spectator.goto(`/tournaments/${tournamentId}/matches/${match.id}`)
    const header = spectator
      .locator("header")
      .filter({ has: spectator.getByRole("heading", { level: 1 }) })
    await expect(header.getByText("申訴期", { exact: true })).toBeVisible()
    await expect(
      spectator.getByRole("region", { name: "申訴期" }),
    ).toBeVisible()
    // 棄權標記只出現一次，掛在未報到的 B 隊旁邊，勝方 A 隊沒有
    await expect(spectator.getByText("棄權", { exact: true })).toHaveCount(1)
    const sideOf = (name: string) =>
      spectator
        .locator("[data-slot=score-team]")
        .filter({ has: spectator.getByText(name, { exact: true }) })
    await expect(sideOf(teamB.name)).toContainText("棄權")
    await expect(sideOf(teamA.name)).not.toContainText("棄權")
    await expectNoHorizontalScroll(spectator)

    await spectator.goto(`/tournaments/${tournamentId}/bracket`)
    const card = bracketCardsOf(spectator, teamA.name).first()
    await expect(card).toContainText("申訴期")
    await expect(card).toContainText("棄權")
    await expectNoHorizontalScroll(spectator)

    // 申訴期滿由 worker 確認後，勝隊 A 晉級決賽（不是季軍賽），敗隊 B 進季軍賽
    await expireAppealWindows([match.id])
    await waitForStatusOrExplain(tournamentId, match, "confirmed", 90_000)
    const confirmed = await fetchBracket(tournamentId)
    const final = confirmed.matches.find(
      (candidate) =>
        candidate.round_no === confirmed.rounds && !candidate.is_third_place,
    )
    const thirdPlace = confirmed.matches.find(
      (candidate) => candidate.is_third_place,
    )
    if (!final || !thirdPlace) throw new Error("找不到決賽或季軍賽")
    const cardOf = (id: string) =>
      spectator.locator(
        `article[data-slot=bracket-match-card][data-match-id="${id}"]`,
      )
    await expect(cardOf(final.id)).toContainText(teamA.name, {
      timeout: 15_000,
    })
    await expect(cardOf(thirdPlace.id)).toContainText(teamB.name)
    await expect(cardOf(thirdPlace.id)).not.toContainText(teamA.name)
    await spectator.close()
  })
})
