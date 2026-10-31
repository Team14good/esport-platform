// 端對端演練用的遊戲設定（假資料）。腳本只讀這些欄位切換遊戲，不依遊戲名稱寫分支（SM-3、NFR-9）。
// 之後與 7.1 第二階段的示範資料（兩款遊戲與段位表）對齊；欄位對應 FR-6 的遊戲設定。

export type ScoreType = "win_loss" | "rounds"

export type GameConfig = {
  /** 測試內部的識別碼（只用在標題與資料，不拿來分支） */
  key: string
  /** 遊戲名稱（介面顯示用） */
  name: string
  /** 先發人數 */
  starters: number
  /** 替補人數 */
  substitutes: number
  /** 預設 BO（只能是 1、3、5、7） */
  defaultBestOf: 1 | 3 | 5 | 7
  /** 每局預估時間（分鐘） */
  minutesPerGame: number
  /** 比分型態：只記勝負，或記回合比分 */
  scoreType: ScoreType
  /** 段位積分對照表（由低到高） */
  ranks: { name: string; points: number }[]
  /** 演練賽事的參賽隊數 */
  teamCount: number
  /** 登錄一局時使用的比分；`win_loss` 只選勝隊，沒有回合比分 */
  sampleGameScore: { winner: number; loser: number } | null
}

/** 勝局門檻：（BO＋1）÷ 2（FR-6、FR-8） */
export function winsNeeded(bestOf: GameConfig["defaultBestOf"]): number {
  return (bestOf + 1) / 2
}

/** 每隊名單上限：先發＋替補（FR-11） */
export function rosterLimit(game: GameConfig): number {
  return game.starters + game.substitutes
}

export const VALORANT: GameConfig = {
  key: "valorant",
  name: "特戰英豪",
  starters: 5,
  substitutes: 2,
  defaultBestOf: 1,
  minutesPerGame: 50,
  scoreType: "rounds",
  ranks: [
    { name: "鐵牌", points: 1 },
    { name: "銅牌", points: 2 },
    { name: "銀牌", points: 3 },
    { name: "金牌", points: 4 },
    { name: "白金", points: 5 },
    { name: "鑽石", points: 6 },
    { name: "超凡入聖", points: 7 },
    { name: "神話", points: 8 },
    { name: "輻能戰魂", points: 9 },
  ],
  teamCount: 32,
  sampleGameScore: { winner: 13, loser: 9 },
}

export const LEAGUE_OF_LEGENDS: GameConfig = {
  key: "league-of-legends",
  name: "英雄聯盟",
  starters: 5,
  substitutes: 1,
  defaultBestOf: 3,
  minutesPerGame: 40,
  scoreType: "win_loss",
  ranks: [
    { name: "鐵", points: 1 },
    { name: "銅", points: 2 },
    { name: "銀", points: 3 },
    { name: "金", points: 4 },
    { name: "白金", points: 5 },
    { name: "翡翠", points: 6 },
    { name: "鑽石", points: 7 },
    { name: "大師", points: 8 },
    { name: "宗師", points: 9 },
    { name: "菁英", points: 10 },
  ],
  teamCount: 32,
  sampleGameScore: null,
}

/** 虛構的第三款遊戲：人數、BO、比分型態都和兩款示範遊戲的組合不同，由平台管理員在後台新增（FR-6、AD-18） */
export const FICTIONAL_GAME: GameConfig = {
  key: "fictional-arena",
  name: "星砂競技場",
  starters: 3,
  substitutes: 0,
  defaultBestOf: 5,
  minutesPerGame: 15,
  scoreType: "rounds",
  ranks: [
    { name: "新星", points: 10 },
    { name: "恆星", points: 20 },
    { name: "超新星", points: 30 },
  ],
  teamCount: 8,
  sampleGameScore: { winner: 5, loser: 3 },
}

/** 跑完整賽事（報名到頒獎）的兩款示範遊戲 */
export const DEMO_GAMES: GameConfig[] = [VALORANT, LEAGUE_OF_LEGENDS]
