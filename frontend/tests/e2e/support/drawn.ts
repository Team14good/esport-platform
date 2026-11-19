// 已抽籤賽事的共用準備：第二階段以上的 e2e（tournament.spec.ts、spectator.spec.ts）從這裡取得
// 「報名截止、全員正取、主辦方已抽籤」的賽事，各步驟的畫面與 API 對應見 setUpDrawnTournament。
import {
  logIn,
  newTestAccount,
  platformAdmin,
  registerVerifiedAccount,
  uniqueSuffix,
} from "./accounts"
import {
  type BulkTeam,
  createRegisteredTeams,
  fetchBracket,
  fetchRegistrationStatus,
  fetchTournamentStatus,
} from "./bulk"
import { endPriorityWindow } from "./db"
import { addGame, createTournament } from "./drill"
import { expect, test } from "./fixtures"
import { type GameConfig, rosterLimit } from "./games"
import { expectNoHorizontalScroll } from "./layout"
import {
  acceptRefereeInvite,
  bracketCardsOf,
  createRefereeInvite,
  drawBracket,
  expectRegistrationAccepted,
  submitRegistration,
} from "./matchday"
import { createOrganizer } from "./organizer"

export type NewRoleContext = Parameters<
  Parameters<typeof test>[2]
>[0]["newRoleContext"]

/** 開一個新角色並登入。 */
export async function rolePage(
  newRoleContext: NewRoleContext,
  role: string,
  account: Parameters<typeof logIn>[1],
) {
  const page = await (await newRoleContext(role)).newPage()
  await logIn(page, account)
  return page
}

/** 新增遊戲到抽籤完成；裁判已接受邀請。 */
export async function setUpDrawnTournament(
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
    const captainPage = await rolePage(
      newRoleContext,
      "第一隊隊長（分配後）",
      teams[0].captain.account,
    )
    await expectRegistrationAccepted(captainPage, teams[0].id)
    await captainPage.close()
  })

  await test.step("主辦方提前抽籤，觀眾在公開對戰表看到隊伍", async () => {
    await drawBracket(organizerPage, tournamentId)
    expect(await fetchTournamentStatus(tournamentId)).toBe("published")
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
