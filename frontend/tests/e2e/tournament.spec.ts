// Story 7.2 的完整賽事演練：依遊戲設定（support/games.ts）產生每一步，同一套步驟套用到每款遊戲，
// 不依遊戲名稱寫分支。上游 Story 還沒合併的步驟先以 test.fixme 列為待辦，標題註明等待的 Story；
// 該 Story 合併後把 fixme 換成 test 並補上內容（共用步驟放 support/）。
// 期中版調整：不含通知、隊伍搜尋與晉級路徑；操作紀錄改由測試直接查 AuditLog。
import { test } from "./support/fixtures"
import {
  DEMO_GAMES,
  FICTIONAL_GAME,
  type GameConfig,
  rosterLimit,
  winsNeeded,
} from "./support/games"

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
      title: `主辦方建立《${game.name}》${game.teamCount} 隊校園賽，帶入預設 BO${game.defaultBestOf}、每局 ${game.minutesPerGame} 分鐘`,
      waitingFor: ["2.2"],
      requirements: ["FR-7"],
    },
    {
      title: "主辦方產生裁判邀請連結，裁判註冊後接受邀請",
      waitingFor: ["2.7"],
      requirements: ["FR-4"],
    },
    {
      title: `${game.teamCount} 位隊長各自建立隊伍，以邀請連結湊滿 ${rosterLimit(game)} 人（先發 ${game.starters}＋替補 ${game.substitutes}）`,
      waitingFor: ["3.1"],
      requirements: ["FR-11"],
    },
    {
      title: `選手填寫遊戲 ID、段位（${game.ranks[0].name}～${game.ranks[game.ranks.length - 1].name}）並上傳段位截圖`,
      waitingFor: ["3.2"],
      requirements: ["FR-12"],
    },
    {
      title: "隊長送出報名，名單鎖定",
      waitingFor: ["3.3"],
      requirements: ["FR-13"],
    },
    {
      title: "優先期結束分配代表隊、先搶期即時分配、報名截止補位",
      waitingFor: ["3.4", "3.5", "3.6"],
      requirements: ["FR-14", "FR-15", "FR-16"],
    },
    {
      title: "觀眾未登入瀏覽公開賽事列表與賽事頁的正取隊伍",
      waitingFor: ["2.4"],
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
      title: `平台管理員在後台新增《${game.name}》：先發 ${game.starters}、替補 ${game.substitutes}、BO${game.defaultBestOf}、${scoreDescription(game)}`,
      waitingFor: ["2.1"],
      requirements: ["FR-6"],
    },
    {
      title: `主辦方以《${game.name}》建立 ${game.teamCount} 隊賽事，自動帶入新遊戲的預設值`,
      waitingFor: ["2.2"],
      requirements: ["FR-7", "FR-6"],
    },
    {
      title: `${game.teamCount} 隊以 ${rosterLimit(game)} 人名單完成組隊、參賽資料與報名分配`,
      waitingFor: ["3.1", "3.2", "3.3", "3.6"],
      requirements: ["FR-11", "FR-12", "FR-13", "FR-16"],
    },
    {
      title: `抽籤後登錄一個場次（BO${game.defaultBestOf}，先拿 ${winsNeeded(game.defaultBestOf)} 局）並確認結果`,
      waitingFor: ["4.1", "5.3", "5.4", "5.5"],
      requirements: ["FR-19", "FR-26", "FR-27", "FR-29"],
    },
  ]
}

function registerSteps(
  describeTitle: string,
  game: GameConfig,
  steps: DrillStep[],
) {
  test.describe(describeTitle, () => {
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
