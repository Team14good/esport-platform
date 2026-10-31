import { Card } from "@/components/ui/card"
import { cn } from "@/lib/utils"
import type { BracketSide } from "./bracket-types"
import { sideView } from "./match-status"
import type { PublicGame, PublicMatchDetail, ScoreType } from "./match-types"

function cellText(game: PublicGame, side: BracketSide, scoreType: ScoreType) {
  const score = side === "a" ? game.score_a : game.score_b
  if (scoreType === "rounds" && score !== null) return String(score)
  // win_loss（或缺回合數時）寫勝負
  return game.winner_side === side ? "勝" : "負"
}

function GameCell({
  game,
  side,
  scoreType,
}: {
  game: PublicGame
  side: BracketSide
  scoreType: ScoreType
}) {
  const won = game.winner_side === side
  return (
    <td
      data-slot="game-score"
      data-side={side}
      data-winner={won || undefined}
      className={cn(
        "border-t py-2.5 font-bold font-mono tabular-nums",
        side === "a" ? "text-right" : "text-left",
        // 該局勝方 foreground、敗方 status-eliminated（每局結果已登錄，與系列是否確認無關）
        won ? "text-foreground" : "text-status-eliminated",
      )}
    >
      {cellText(game, side, scoreType)}
    </td>
  )
}

type MatchGameListProps = {
  detail: PublicMatchDetail
  className?: string
}

const HEAD_CELL =
  "pb-2 align-bottom font-semibold text-muted-foreground text-overline"

/** 公開的各局列表：表頭「局」＋兩隊隊名，每局一列「第 N 局」。沒有已登錄的局時不顯示。 */
export function MatchGameList({ detail, className }: MatchGameListProps) {
  if (detail.games.length === 0) return null
  const { score_type: scoreType } = detail
  return (
    <Card data-slot="game-list" className={cn("gap-0 p-4", className)}>
      <table className="w-full border-collapse">
        <caption className="sr-only">各局比分</caption>
        <thead>
          <tr>
            <th scope="col" className={cn(HEAD_CELL, "w-px pr-2.5 text-left")}>
              局
            </th>
            <th
              scope="col"
              className={cn(HEAD_CELL, "w-1/2 wrap-anywhere text-right")}
            >
              {sideView(detail, "a").name}
            </th>
            <td aria-hidden="true" className="w-px px-2.5" />
            <th
              scope="col"
              className={cn(HEAD_CELL, "w-1/2 wrap-anywhere text-left")}
            >
              {sideView(detail, "b").name}
            </th>
          </tr>
        </thead>
        <tbody>
          {detail.games.map((game) => (
            <tr key={game.game_no} data-slot="game-row">
              <th
                scope="row"
                className="whitespace-nowrap border-t py-2.5 pr-2.5 text-left font-normal text-muted-foreground"
              >
                第 {game.game_no} 局
              </th>
              <GameCell game={game} side="a" scoreType={scoreType} />
              <td
                aria-hidden="true"
                className="border-t px-2.5 py-2.5 text-center font-mono text-muted-foreground"
              >
                {scoreType === "rounds" ? ":" : ""}
              </td>
              <GameCell game={game} side="b" scoreType={scoreType} />
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  )
}
