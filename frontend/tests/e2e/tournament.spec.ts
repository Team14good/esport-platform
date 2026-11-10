// Story 7.2 的完整賽事演練：依遊戲設定（support/games.ts）產生每一步，同一套步驟套用到每款遊戲，
// 不依遊戲名稱寫分支。
// 第二階段：每款遊戲一個測試，從平台管理員新增遊戲走到一隊滿編、全員填完參賽資料（整隊走畫面）。
// 第三階段：兩款示範遊戲各跑一場 32 隊賽事到頒獎，第三款遊戲跑 8 隊到確認一場結果。關鍵步驟走畫面，
// 大量重複的準備與場次走公開 API（support/bulk.ts），受真實時間限制的期限改資料庫（support/db.ts）。
// 期中版調整：不含通知、隊伍搜尋與晉級路徑；操作紀錄改由測試直接查 AuditLog。
import {
  logIn,
  newTestAccount,
  platformAdmin,
  registerVerifiedAccount,
  registerVerifiedAccounts,
  uniqueSuffix,
} from "./support/accounts"
import {
  apiAssignReferee,
  apiLogin,
  type BulkTeam,
  createRegisteredTeams,
  fetchAccountId,
  fetchBracket,
  fetchRegistrationStatus,
  fetchTournamentStatus,
  findTeam,
  playableMatches,
  playMatchByApi,
  playMatchesByApi,
  teamsOf,
  waitForMatchStatus,
} from "./support/bulk"
import {
  auditRows,
  endPriorityWindow,
  expireAppealWindows,
  openCheckIn,
} from "./support/db"
import {
  addGame,
  browseOpenTournament,
  createTeam,
  createTournament,
  expectedAveragePoints,
  fillPlayerProfile,
  joinTeam,
} from "./support/drill"
import { expect, test } from "./support/fixtures"
import {
  DEMO_GAMES,
  FICTIONAL_GAME,
  type GameConfig,
  rosterLimit,
} from "./support/games"
import { expectNoHorizontalScroll } from "./support/layout"
import {
  acceptRefereeInvite,
  assignRefereeOnPage,
  bracketCardsOf,
  checkInOnPage,
  correctAppealToTeamB,
  createRefereeInvite,
  disqualifyReportedTeam,
  drawBracket,
  expectPodium,
  expectRefereeSeesMatch,
  fileAppeal,
  reportTeam,
  scoreMatchOnPage,
  submitRegistration,
} from "./support/matchday"
import { createOrganizer } from "./support/organizer"

// 這個檔案的測試依序執行（playwright.config.ts 也只開 1 個 worker）：
// 每個演練要註冊、登入多個帳號（密碼雜湊）並開多個頁面，三款遊戲同時跑會互相拖慢，
// 一般 API 超過 1 秒（NFR-2）。default 模式下某個測試失敗，後面的測試仍會執行。
test.describe.configure({ mode: "default" })

/** 第二階段：新增遊戲、建立賽事、觀眾瀏覽、一隊滿編並全員填完參賽資料（整隊走畫面）。 */
function registrationDrill(game: GameConfig) {
  test(`平台管理員新增《${game.name}》、主辦方建立賽事，一隊湊滿 ${rosterLimit(game)} 人並全員填完參賽資料`, {
    tag: [
      "@story-2.1",
      "@story-2.2",
      "@story-2.4",
      "@story-3.1",
      "@story-3.2",
      "@story-7.2",
      `@game-${game.key}`,
      "@FR-6",
      "@FR-7",
      "@FR-11",
      "@FR-12",
      "@FR-34",
      "@NFR-2",
      "@NFR-7",
    ],
  }, async ({ newRoleContext }) => {
    // 主辦方與隊員的驗證信各要等 worker 輪詢（預設每 20 秒），隊員的驗證信同時等
    test.setTimeout(360_000)
    const suffix = uniqueSuffix()
    // 後端遊戲名稱不分大小寫唯一：加上本次執行的後綴，同一個資料庫可以重複執行
    const gameName = `${game.name} ${suffix}`
    const tournamentName = `E2E ${game.name}校園賽 ${suffix}`
    const teamName = `E2E 隊 ${suffix}`
    const adminPage = await (await newRoleContext("平台管理員")).newPage()
    const organizerPage = await (await newRoleContext("主辦方")).newPage()
    let tournamentId = ""

    await test.step("平台管理員在後台新增遊戲", async () => {
      await logIn(adminPage, platformAdmin())
      await addGame(adminPage, game, gameName)
    })

    await test.step("註冊主辦方並由平台管理員核准", async () => {
      await createOrganizer(organizerPage, adminPage)
    })

    await test.step("主辦方建立賽事，自動帶入遊戲預設值", async () => {
      tournamentId = await createTournament(organizerPage, game, {
        gameName,
        tournamentName,
      })
    })

    await test.step("觀眾未登入在賽事列表的「開放報名」找到賽事並進入賽事頁", async () => {
      const spectatorPage = await (await newRoleContext("觀眾")).newPage()
      await browseOpenTournament(spectatorPage, tournamentName, tournamentId)
    })

    // 隊長＋其餘隊員，人數＝先發＋替補
    const members = Array.from({ length: rosterLimit(game) }, (_, index) => ({
      account: newTestAccount(index === 0 ? "captain" : "player"),
      role: index === 0 ? "隊長" : `隊員 ${index}`,
      rank: game.ranks[index % game.ranks.length],
      gameAccountId: `E2E-${index + 1}-${suffix.slice(-6)}`,
    }))
    const pages = await Promise.all(
      members.map(async (member) =>
        (await newRoleContext(member.role)).newPage(),
      ),
    )

    await test.step(`${members.length} 位選手註冊並驗證 Email`, async () => {
      await registerVerifiedAccounts(
        pages,
        members.map((member) => member.account),
      )
    })

    let inviteUrl = ""
    await test.step("隊長在賽事頁建立隊伍", async () => {
      inviteUrl = await createTeam(pages[0], tournamentId, teamName)
    })

    await test.step("其餘隊員開邀請連結加入隊伍", async () => {
      for (const page of pages.slice(1)) {
        await joinTeam(page, inviteUrl, teamName)
      }
    })

    await test.step("每位隊員填寫遊戲 ID、段位並上傳段位截圖", async () => {
      for (const [index, member] of members.entries()) {
        const page = pages[index]
        await page.reload()
        await fillPlayerProfile(page, {
          displayName: member.account.displayName,
          gameAccountId: member.gameAccountId,
          rankName: member.rank.name,
        })
      }
    })

    await test.step("隊長看到名單滿編與平均段位積分", async () => {
      const captainPage = pages[0]
      await captainPage.reload()
      const roster = captainPage.locator('ul[aria-label="隊伍名單"] > li')
      await expect(roster).toHaveCount(members.length)
      await expect(roster.getByText("資料完成", { exact: true })).toHaveCount(
        members.length,
      )
      await expect(
        captainPage.getByText(
          `${members.length}／${members.length} 人（先發 ${game.starters}）`,
          { exact: true },
        ),
      ).toBeVisible()
      await expect(
        captainPage.getByText(
          expectedAveragePoints(members.map((member) => member.rank.points)),
          { exact: true },
        ),
      ).toBeVisible()
      await expect(
        captainPage.getByText("隊伍已滿", { exact: false }),
      ).toBeVisible()
      await expectNoHorizontalScroll(captainPage)
    })

    await test.step("名單已滿時，其他帳號開邀請連結看到連結已失效", async () => {
      // 主辦方是名單以外的另一個已登入帳號
      await organizerPage.goto(inviteUrl)
      await expect(
        organizerPage.getByRole("heading", { name: "加入隊伍", level: 1 }),
      ).toBeVisible()
      await expect(
        organizerPage.getByText("連結已失效：隊伍已滿。", { exact: true }),
      ).toBeVisible()
      await expect(
        organizerPage.getByRole("button", { name: "加入隊伍", exact: true }),
      ).toHaveCount(0)
      await expectNoHorizontalScroll(organizerPage)
    })
  })
}

type NewRoleContext = Parameters<
  Parameters<typeof test>[2]
>[0]["newRoleContext"]

/** 開一個新角色並登入。 */
async function rolePage(
  newRoleContext: NewRoleContext,
  role: string,
  account: Parameters<typeof logIn>[1],
) {
  const page = await (await newRoleContext(role)).newPage()
  await logIn(page, account)
  return page
}

/** 新增遊戲到抽籤完成；裁判已接受邀請。 */
async function setUpDrawnTournament(
  game: GameConfig,
  newRoleContext: NewRoleContext,
) {
  const suffix = uniqueSuffix()
  const gameName = `${game.name} ${suffix}`
  const tournamentName = `E2E ${game.name}完整賽 ${suffix}`
  const adminPage = await (await newRoleContext("平台管理員")).newPage()
  const organizerPage = await (await newRoleContext("主辦方")).newPage()
  const refereePage = await (await newRoleContext("裁判")).newPage()
  const referee = newTestAccount("referee")
  let tournamentId = ""
  let teams: BulkTeam[] = []

  await test.step("平台管理員新增遊戲", async () => {
    await logIn(adminPage, platformAdmin())
    await addGame(adminPage, game, gameName)
  })
  const organizer = await test.step("主辦方註冊並由平台管理員核准", () =>
    createOrganizer(organizerPage, adminPage))

  await test.step("主辦方建立賽事，裁判註冊後接受邀請", async () => {
    tournamentId = await createTournament(organizerPage, game, {
      gameName,
      tournamentName,
    })
    await registerVerifiedAccount(refereePage, referee)
    const invite = await createRefereeInvite(organizerPage, tournamentId)
    await acceptRefereeInvite(refereePage, invite, tournamentName)
  })

  await test.step(`${game.teamCount} 隊（每隊 ${rosterLimit(game)} 人）報名，第一隊由隊長在 S17 送出`, async () => {
    teams = await createRegisteredTeams(tournamentId, game, suffix)
    const captainPage = await rolePage(
      newRoleContext,
      "第一隊隊長",
      teams[0].captain.account,
    )
    await submitRegistration(captainPage, teams[0].id)
    await captainPage.close()
  })

  await test.step("優先期結束後 worker 分配，所有代表隊成為正取", async () => {
    await endPriorityWindow(tournamentId)
    await expect
      .poll(() => fetchRegistrationStatus(teams[0]), {
        timeout: 90_000,
        intervals: [2_000],
      })
      .toBe("accepted")
    const statuses = await Promise.all(teams.map(fetchRegistrationStatus))
    expect(new Set(statuses)).toEqual(new Set(["accepted"]))
  })

  await test.step("主辦方提前抽籤，觀眾在公開對戰表看到隊伍", async () => {
    await drawBracket(organizerPage, tournamentId)
    const bracket = await fetchBracket(tournamentId)
    // 正取 4 隊以上有季軍賽，場次數等於隊數（FR-20）
    expect(bracket.matches).toHaveLength(game.teamCount)
    expect(bracket.matches.some((match) => match.is_third_place)).toBe(true)
    const spectator = await (await newRoleContext("觀眾")).newPage()
    await spectator.goto(`/tournaments/${tournamentId}/bracket`)
    await expect(bracketCardsOf(spectator, teams[0].name).first()).toBeVisible()
    await expectNoHorizontalScroll(spectator)
    await spectator.close()
  })

  return {
    tournamentId,
    teams,
    organizer,
    organizerPage,
    referee,
    refereePage,
  }
}

type DrawnTournament = Awaited<ReturnType<typeof setUpDrawnTournament>>

/**
 * 第一輪第一場全部走畫面：指派裁判、兩隊長報到、裁判逐局登錄；申訴期滿由 worker 確認，
 * 觀眾開著對戰樹，確認後 10 秒內看到勝隊晉級。回傳這一場。
 */
async function playFirstMatchOnPages(
  game: GameConfig,
  drill: DrawnTournament,
  newRoleContext: NewRoleContext,
) {
  const { tournamentId, teams, organizerPage, referee, refereePage } = drill
  const bracket = await fetchBracket(tournamentId)
  const round = playableMatches(bracket, 1)
  const match = round[0]
  const { teamA, teamB } = teamsOf(match)
  await openCheckIn(round.map((candidate) => candidate.id))

  await test.step("主辦方在 S30 指派裁判，裁判在 S13 看到場次", async () => {
    await assignRefereeOnPage(
      organizerPage,
      tournamentId,
      match.code,
      referee.displayName,
    )
    await expectRefereeSeesMatch(refereePage, match.code)
  })

  await test.step("兩隊長在 S4 報到，裁判逐局登錄並送出系列結果", async () => {
    for (const [role, team] of [
      ["A 隊隊長", teamA],
      ["B 隊隊長", teamB],
    ] as const) {
      const page = await rolePage(
        newRoleContext,
        role,
        findTeam(teams, team.id).captain.account,
      )
      await checkInOnPage(page, tournamentId, match.id)
      await page.close()
    }
    await scoreMatchOnPage(
      refereePage,
      tournamentId,
      match.id,
      game,
      teamA.name,
      teamB.name,
    )
    await waitForMatchStatus(tournamentId, [match.id], "appeal_window", 15_000)
  })

  await test.step("申訴期滿自動確認，觀眾 10 秒內看到結果，不需重新整理", async () => {
    const spectator = await (await newRoleContext("觀眾")).newPage()
    await spectator.goto(`/tournaments/${tournamentId}/bracket`)
    await expect(bracketCardsOf(spectator, teamA.name)).toHaveCount(1)
    await expireAppealWindows([match.id])
    await waitForMatchStatus(tournamentId, [match.id], "confirmed")
    // 勝隊出現在下一輪：同一隊變成兩張場次卡
    await expect(bracketCardsOf(spectator, teamA.name)).toHaveCount(2, {
      timeout: 10_000,
    })
    await spectator.close()
  })

  return match
}

const FULL_DRILL_STORIES = [
  "2.7",
  "3.3",
  "3.4",
  "4.1",
  "4.3",
  "4.4",
  "4.6",
  "5.1",
  "5.3",
  "5.4",
  "5.5",
  "5.6",
  "6.1",
  "6.2",
  "6.4",
  "6.5",
  "7.2",
]

const FULL_DRILL_REQUIREMENTS = [
  "FR-4",
  "FR-13",
  "FR-14",
  "FR-19",
  "FR-20",
  "FR-21",
  "FR-22",
  "FR-24",
  "FR-26",
  "FR-27",
  "FR-29",
  "FR-30",
  "FR-31",
  "FR-32",
  "FR-33",
  "FR-35",
  "NFR-2",
  "NFR-3",
  "NFR-7",
  "SM-1",
  "SM-3",
  "SM-4",
]

/** 完整賽事：從報名到頒獎。 */
function fullTournamentDrill(game: GameConfig) {
  test(`《${game.name}》${game.teamCount} 隊完整賽事：報名、抽籤、報到、比分、申訴更正、取消資格頂替到頒獎`, {
    tag: [
      ...FULL_DRILL_STORIES.map((story) => `@story-${story}`),
      `@game-${game.key}`,
      ...FULL_DRILL_REQUIREMENTS.map((requirement) => `@${requirement}`),
    ],
  }, async ({ newRoleContext }) => {
    test.setTimeout(45 * 60_000)
    const drill = await setUpDrawnTournament(game, newRoleContext)
    const { tournamentId, teams, organizer, organizerPage, refereePage } = drill
    const organizerToken = await apiLogin(organizer)
    const refereeToken = await apiLogin(drill.referee)
    const firstMatch = await playFirstMatchOnPages(game, drill, newRoleContext)
    const firstRound = playableMatches(await fetchBracket(tournamentId), 1)

    const appealMatch = firstRound[0]
    const appealTeams = teamsOf(appealMatch)
    const otherMatches = firstRound.slice(1)

    await test.step("敗隊隊長提出申訴，主辦方更正結果後勝隊改變", async () => {
      await playMatchByApi({
        tournamentId,
        game,
        match: appealMatch,
        teams,
        scorerToken: organizerToken,
        winner: "a",
      })
      const loserPage = await rolePage(
        newRoleContext,
        "申訴隊隊長",
        findTeam(teams, appealTeams.teamB.id).captain.account,
      )
      await fileAppeal(loserPage, tournamentId, appealMatch.id)
      await loserPage.close()
      await correctAppealToTeamB(
        organizerPage,
        tournamentId,
        game,
        appealTeams.teamA.name,
        appealTeams.teamB.name,
      )
      const after = await waitForMatchStatus(
        tournamentId,
        [appealMatch.id],
        "confirmed",
        15_000,
      )
      expect(
        after.matches.find((match) => match.id === appealMatch.id)?.winner_id,
      ).toBe(appealTeams.teamB.id)
    })

    await test.step("第一輪其餘場次：申訴期滿自動確認，勝隊晉級", async () => {
      await playMatchesByApi({
        tournamentId,
        game,
        matches: otherMatches,
        teams,
        scorerToken: organizerToken,
        winner: "a",
      })
      await expireAppealWindows(otherMatches.map((match) => match.id))
      await waitForMatchStatus(
        tournamentId,
        otherMatches.map((match) => match.id),
        "confirmed",
      )
    })

    await test.step("隊長檢舉一支等待第二輪的隊伍，主辦方取消資格，由最近一場輸給它的隊伍頂替", async () => {
      const excluded = new Set([
        firstMatch.team_a?.id,
        appealTeams.teamA.id,
        appealTeams.teamB.id,
      ])
      const target = otherMatches.find(
        (match) => match.team_a && !excluded.has(match.team_a.id),
      )
      if (!target) throw new Error("找不到可取消資格的隊伍")
      const { teamA: disqualified, teamB: replacement } = teamsOf(target)
      const reporter = otherMatches.find((match) => match.id !== target.id)
      if (!reporter) throw new Error("找不到提出檢舉的隊伍")
      const reporterPage = await rolePage(
        newRoleContext,
        "檢舉隊隊長",
        findTeam(teams, teamsOf(reporter).teamA.id).captain.account,
      )
      await reportTeam(reporterPage, tournamentId, disqualified.name)
      await reporterPage.close()
      await disqualifyReportedTeam(
        organizerPage,
        tournamentId,
        disqualified.name,
      )
      const after = await fetchBracket(tournamentId)
      const seated = after.matches
        .filter((match) => match.round_no === 2)
        .flatMap((match) => [match.team_a?.id, match.team_b?.id])
      expect(seated).toContain(replacement.id)
      expect(seated).not.toContain(disqualified.id)
    })

    await test.step("其餘各輪打到決賽與季軍賽，決賽走畫面", async () => {
      const { rounds } = await fetchBracket(tournamentId)
      for (let round = 2; round <= rounds; round += 1) {
        const matches = playableMatches(await fetchBracket(tournamentId), round)
        await openCheckIn(matches.map((match) => match.id))
        const final =
          round === rounds
            ? matches.find((match) => !match.is_third_place)
            : undefined
        await playMatchesByApi({
          tournamentId,
          game,
          matches: matches.filter((match) => match.id !== final?.id),
          teams,
          scorerToken: organizerToken,
          winner: "a",
        })
        if (final) {
          const { teamA, teamB } = teamsOf(final)
          await apiAssignReferee(
            tournamentId,
            final.id,
            organizerToken,
            await fetchAccountId(refereeToken),
          )
          for (const [role, team] of [
            ["決賽 A 隊隊長", teamA],
            ["決賽 B 隊隊長", teamB],
          ] as const) {
            const page = await rolePage(
              newRoleContext,
              role,
              findTeam(teams, team.id).captain.account,
            )
            await checkInOnPage(page, tournamentId, final.id)
            await page.close()
          }
          await scoreMatchOnPage(
            refereePage,
            tournamentId,
            final.id,
            game,
            teamA.name,
            teamB.name,
          )
        }
        const ids = matches.map((match) => match.id)
        await waitForMatchStatus(tournamentId, ids, "appeal_window", 30_000)
        await expireAppealWindows(ids)
        await waitForMatchStatus(tournamentId, ids, "confirmed")
      }
    })

    await test.step("賽事轉為已結束，S3 顯示冠軍、亞軍、季軍的頒獎台", async () => {
      await expect
        .poll(() => fetchTournamentStatus(tournamentId), { timeout: 60_000 })
        .toBe("finished")
      const bracket = await fetchBracket(tournamentId)
      const final = bracket.matches.find(
        (match) => match.round_no === bracket.rounds && !match.is_third_place,
      )
      const thirdPlace = bracket.matches.find((match) => match.is_third_place)
      if (!final || !thirdPlace) throw new Error("找不到決賽或季軍賽")
      const finalists = teamsOf(final)
      expect(bracket.podium?.champion?.id).toBe(finalists.teamA.id)
      expect(bracket.podium?.runner_up?.id).toBe(finalists.teamB.id)
      expect(bracket.podium?.third_place?.id).toBe(thirdPlace.team_a?.id)
      const spectator = await (await newRoleContext("觀眾")).newPage()
      await expectPodium(spectator, tournamentId, {
        champion: finalists.teamA.name,
        runnerUp: finalists.teamB.name,
        thirdPlace: thirdPlace.team_a?.name ?? "",
      })
    })

    await test.step("直接查 AuditLog：結果變更都有操作者與變更前後的內容", async () => {
      const actions = [
        "appeal.resolved",
        "report.resolved",
        "match.teams_changed",
      ]
      const changes = await auditRows(tournamentId, actions)
      expect(new Set(changes.map((row) => row.action))).toEqual(
        new Set(actions),
      )
      for (const row of changes) {
        expect(row.actor_id, row.action).not.toBeNull()
        expect(row.before, row.action).not.toBeNull()
        expect(row.after, row.action).not.toBeNull()
      }
      const submitted = await auditRows(tournamentId, [
        "match.result_submitted",
      ])
      expect(submitted.length).toBeGreaterThanOrEqual(game.teamCount - 1)
      for (const row of submitted) {
        expect(row.actor_id).not.toBeNull()
      }
    })
  })
}

/** 第三款遊戲：平台管理員在後台新增後，跑完報名到確認一場結果，全程不改程式。 */
function newGameDrill(game: GameConfig) {
  test(`後台新增的《${game.name}》：${game.teamCount} 隊報名、抽籤，登錄一場 BO${game.defaultBestOf} 並確認結果`, {
    tag: [
      "@story-2.1",
      "@story-3.3",
      "@story-4.1",
      "@story-5.3",
      "@story-5.4",
      "@story-5.5",
      "@story-7.2",
      `@game-${game.key}`,
      "@FR-6",
      "@FR-13",
      "@FR-19",
      "@FR-26",
      "@FR-27",
      "@FR-29",
      "@NFR-2",
      "@NFR-7",
    ],
  }, async ({ newRoleContext }) => {
    test.setTimeout(20 * 60_000)
    const drill = await setUpDrawnTournament(game, newRoleContext)
    await playFirstMatchOnPages(game, drill, newRoleContext)
  })
}

for (const game of DEMO_GAMES) {
  test.describe(`完整賽事演練：《${game.name}》`, () => {
    registrationDrill(game)
    fullTournamentDrill(game)
  })
}

test.describe(`新增第三款遊戲：《${FICTIONAL_GAME.name}》`, () => {
  registrationDrill(FICTIONAL_GAME)
  newGameDrill(FICTIONAL_GAME)
})
