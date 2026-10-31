// 開發模式的場次頁預覽：只在 import.meta.env.DEV 時顯示，正式 build 顯示 404。
// 以假資料驅動 useMatchPolling，可模擬比分變動與斷線；第二階段接上真資料後刪除這個檔案。
import { useQueryClient } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { useRef, useState } from "react"

import { NotFoundPage } from "@/components/layout/ErrorPage"
import { Button } from "@/components/ui/button"
import { createBracketFixture } from "@/features/competition/bracket-fixtures"
import { ConnectionLostBanner } from "@/features/competition/ConnectionLostBanner"
import { MatchSpectatorView } from "@/features/competition/MatchSpectatorView"
import {
  matchDetailFromBracket,
  simulateMatchChange,
} from "@/features/competition/match-fixtures"
import { MatchNotFoundError } from "@/features/competition/match-source"
import type { PublicMatchDetail } from "@/features/competition/match-types"
import { useMatchPolling } from "@/features/competition/use-match-polling"

export const Route = createFileRoute("/dev/match")({
  head: () => ({ meta: [{ title: "場次頁預覽 · FLOW" }] }),
  component: DevMatchRoute,
})

function DevMatchRoute() {
  // 正式 build 時 DEV 為常數 false，預覽頁與假資料都會被移除
  if (!import.meta.env.DEV) return <NotFoundPage />
  return <MatchPreview />
}

/** 32 隊「進行中」假對戰樹裡各種狀態的代表場次 */
const PRESETS: { matchId: string; label: string }[] = [
  { matchId: "match-M1", label: "已確認（2 : 1）" },
  { matchId: "match-M2", label: "已確認（win_loss）" },
  { matchId: "match-M4", label: "一方棄權" },
  { matchId: "match-M6", label: "取消資格" },
  { matchId: "match-M17", label: "進行中" },
  { matchId: "match-M18", label: "申訴期" },
  { matchId: "match-M19", label: "申訴中" },
  { matchId: "match-M25", label: "待開打、隊伍未定" },
  { matchId: "match-M31", label: "決賽" },
  { matchId: "match-M32", label: "季軍賽" },
  { matchId: "missing", label: "找不到場次" },
]

function MatchPreview() {
  const queryClient = useQueryClient()
  const [bracket] = useState(() =>
    createBracketFixture({ teamCount: 32, scenario: "in_progress" }),
  )
  const [matchId, setMatchId] = useState(PRESETS[4].matchId)
  const [offline, setOffline] = useState(false)
  const queryKey = ["dev-match", matchId]
  // 每場各自一份假資料；「模擬變動」改的是目前這一份，下一次輪詢就會拿到
  const store = useRef(new Map<string, PublicMatchDetail>())
  const offlineRef = useRef(offline)
  offlineRef.current = offline

  const current = (): PublicMatchDetail => {
    let data = store.current.get(matchId)
    if (data === undefined) {
      data = matchDetailFromBracket(bracket, matchId)
      if (data === undefined) throw new MatchNotFoundError()
      store.current.set(matchId, data)
    }
    return data
  }

  const { detail, changed, connectionLost, lastUpdatedAt, notFound } =
    useMatchPolling({
      queryKey,
      queryFn: async () => {
        if (offlineRef.current) throw new Error("模擬斷線")
        return current()
      },
    })

  const simulateChange = () => {
    store.current.set(matchId, simulateMatchChange(current()))
    void queryClient.refetchQueries({ queryKey })
  }

  return (
    <div className="flex min-w-0 flex-col gap-6">
      {connectionLost && <ConnectionLostBanner lastUpdatedAt={lastUpdatedAt} />}
      <header className="flex flex-col gap-1">
        <h1 className="text-heading-lg">場次頁預覽</h1>
        <p className="text-muted-foreground">
          開發模式專用，以假資料每 5
          秒輪詢。「模擬變動」在進行中的場次多登錄一局、待開打的場次改為進行中。
        </p>
      </header>
      <fieldset className="flex flex-wrap items-center gap-2">
        <legend className="mb-2 text-muted-foreground text-overline">
          場次
        </legend>
        {PRESETS.map((preset) => (
          <Button
            key={preset.matchId}
            type="button"
            size="sm"
            variant={preset.matchId === matchId ? "default" : "outline"}
            aria-pressed={preset.matchId === matchId}
            onClick={() => setMatchId(preset.matchId)}
          >
            {preset.label}
          </Button>
        ))}
      </fieldset>
      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          variant="outline"
          onClick={simulateChange}
          disabled={notFound || offline}
        >
          模擬變動
        </Button>
        <Button
          type="button"
          variant="outline"
          onClick={() => setOffline((v) => !v)}
        >
          {offline ? "恢復連線" : "模擬斷線"}
        </Button>
      </div>
      {notFound ? (
        <NotFoundPage />
      ) : (
        detail && <MatchSpectatorView detail={detail} changed={changed} />
      )}
    </div>
  )
}
