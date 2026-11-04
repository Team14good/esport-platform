// Story 7.2 的完整賽事演練：依遊戲設定（support/games.ts）產生每一步，同一套步驟套用到每款遊戲，
// 不依遊戲名稱寫分支。上游 Story 還沒合併的步驟先以 test.fixme 列為待辦，標題註明等待的 Story；
// 該 Story 合併後把 fixme 換成 test 並補上內容（共用步驟放 support/）。
// 第二階段：每款遊戲一個真的測試，從平台管理員新增遊戲走到一隊滿編、全員填完參賽資料（2.1、2.2、2.4、3.1、3.2）。
// 期中版調整：不含通知、隊伍搜尋與晉級路徑；操作紀錄改由測試直接查 AuditLog。
import {
  logIn,
  newTestAccount,
  platformAdmin,
  registerVerifiedAccounts,
  uniqueSuffix,
} from "./support/accounts"
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
  winsNeeded,
} from "./support/games"
import { expectNoHorizontalScroll } from "./support/layout"
import { createOrganizer } from "./support/organizer"

// 這個檔案的測試依序執行（playwright.config.ts 也只開 1 個 worker）：
// 每個演練要註冊、登入多個帳號（密碼雜湊）並開多個頁面，三款遊戲同時跑會互相拖慢，
// 一般 API 超過 1 秒（NFR-2）。default 模式下某個測試失敗，後面的測試仍會執行。
test.describe.configure({ mode: "default" })

type DrillStep = {
  title: string
  /** 等待合併的 Story 編號 */
  waitingFor: string[]
  /** FR／NFR 等需求編號（不含 @） */
  requirements: string[]
}

function scoreDescription(game: GameConfig): string {
  return game.sampleGameScore
    ? `回合比分（例如 ${game.sampleGameScore.winner}:${game.sampleGameScore.loser}）`
    : "只選勝隊"
}

/** 從報名到頒獎的完整流程（UJ-1～UJ-4 的高潮步驟） */
function fullTournamentSteps(game: GameConfig): DrillStep[] {
  return [
    {
      title: "主辦方產生裁判邀請連結，裁判註冊後接受邀請",
      waitingFor: ["2.7"],
      requirements: ["FR-4"],
    },
    {
      title: `${game.teamCount} 隊的隊長送出報名（每隊 ${rosterLimit(game)} 人、全員填完參賽資料），名單鎖定`,
      waitingFor: ["3.3"],
      requirements: ["FR-13"],
    },
    {
      title: "優先期結束分配代表隊、先搶期即時分配、報名截止補位",
      waitingFor: ["3.4", "3.5", "3.6"],
      requirements: ["FR-14", "FR-15", "FR-16"],
    },
    {
      title: "觀眾未登入在賽事頁看到分配後的正取隊伍",
      waitingFor: ["3.4", "3.5", "3.6"],
      requirements: ["FR-34"],
    },
    {
      title: `主辦方提前抽籤，產生 ${game.teamCount} 隊單淘汰對戰表與季軍賽`,
      waitingFor: ["4.1"],
      requirements: ["FR-19", "FR-20"],
    },
    {
      title: "系統排定場次時間，主辦方指派裁判到場次",
      waitingFor: ["4.3", "4.4"],
      requirements: ["FR-23", "FR-4"],
    },
    {
      title: "兩隊隊長在開始前 30 分鐘內報到，裁判看到可開始",
      waitingFor: ["5.1"],
      requirements: ["FR-24"],
    },
    {
      title: `裁判逐局登錄比分（${scoreDescription(game)}），先拿 ${winsNeeded(game.defaultBestOf)} 局後送出系列結果`,
      waitingFor: ["5.3", "5.4"],
      requirements: ["FR-26", "FR-27"],
    },
    {
      title:
        "觀眾開著公開對戰樹，場次變為已確認後 10 秒內看到新結果，不需重新整理",
      waitingFor: ["4.6 第二階段", "5.5"],
      requirements: ["FR-35", "NFR-2"],
    },
    {
      title: "敗隊隊長在申訴期內提出申訴，主辦方更正結果後重新晉級",
      waitingFor: ["6.1", "6.2"],
      requirements: ["FR-30", "FR-31"],
    },
    {
      title: "隊長檢舉另一隊，主辦方取消資格，由最近一場輸給它的隊伍頂替",
      waitingFor: ["6.4", "6.5"],
      requirements: ["FR-32", "FR-33", "FR-22"],
    },
    {
      title: "申訴期滿沒有申訴的場次自動確認，勝隊晉級下一輪",
      waitingFor: ["5.5"],
      requirements: ["FR-29", "FR-21"],
    },
    {
      title:
        "季軍賽與決賽定案，賽事轉為已結束，S3 顯示冠軍、亞軍、季軍的頒獎台",
      waitingFor: ["5.6", "4.6 第二階段"],
      requirements: ["FR-21", "SM-1"],
    },
    {
      title:
        "直接查詢 AuditLog：每一次結果變更（含申訴更正與取消資格）都有操作者與變更前後的內容",
      waitingFor: ["5.3", "5.4", "6.2", "6.5"],
      requirements: ["NFR-3", "SM-4"],
    },
  ]
}

/** 虛構的第三款遊戲：平台管理員在後台新增後，跑完報名到確認結果 */
function newGameSteps(game: GameConfig): DrillStep[] {
  return [
    {
      title: `${game.teamCount} 隊以 ${rosterLimit(game)} 人名單送出報名並完成分配`,
      waitingFor: ["3.3", "3.6"],
      requirements: ["FR-13", "FR-16"],
    },
    {
      title: `抽籤後登錄一個場次（BO${game.defaultBestOf}，先拿 ${winsNeeded(game.defaultBestOf)} 局）並確認結果`,
      waitingFor: ["4.1", "5.3", "5.4", "5.5"],
      requirements: ["FR-19", "FR-26", "FR-27", "FR-29"],
    },
  ]
}

/** 已實作的前半段：新增遊戲、建立賽事、觀眾瀏覽、一隊滿編並全員填完參賽資料。 */
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

function registerSteps(
  describeTitle: string,
  game: GameConfig,
  steps: DrillStep[],
) {
  test.describe(describeTitle, () => {
    registrationDrill(game)
    for (const step of steps) {
      test.fixme(`${step.title}（等待 Story ${step.waitingFor.join("、")}）`, {
        tag: [
          ...new Set([
            "@story-7.2",
            `@game-${game.key}`,
            // 「4.6 第二階段」只取 Story 編號
            ...step.waitingFor.map((story) => `@story-${story.split(" ")[0]}`),
            ...step.requirements.map((id) => `@${id}`),
          ]),
        ],
      }, async () => {
        // 上游合併後實作；共用步驟（註冊、登錄比分等）放 support/，只讀 game 的設定
      })
    }
  })
}

for (const game of DEMO_GAMES) {
  registerSteps(
    `完整賽事演練：《${game.name}》`,
    game,
    fullTournamentSteps(game),
  )
}

registerSteps(
  `新增第三款遊戲：《${FICTIONAL_GAME.name}》`,
  FICTIONAL_GAME,
  newGameSteps(FICTIONAL_GAME),
)
