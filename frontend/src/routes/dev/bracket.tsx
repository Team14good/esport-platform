// 開發模式的對戰樹預覽頁：只在 import.meta.env.DEV 時顯示，正式 build 顯示 404。
// 第一階段用假資料驅動 useBracketPolling；第二階段接上 S3 後刪除這個檔案。
import { useQueryClient } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { useRef, useState } from "react"

import { NotFoundPage } from "@/components/layout/ErrorPage"
import { Button } from "@/components/ui/button"
import { BracketPending } from "@/features/competition/BracketPending"
import { BracketTree } from "@/features/competition/BracketTree"
import {
  type BracketScenario,
  createBracketFixture,
  simulateBracketChange,
} from "@/features/competition/bracket-fixtures"
import type { PublicBracket } from "@/features/competition/bracket-types"
import { ConnectionLostBanner } from "@/features/competition/ConnectionLostBanner"
import { useBracketPolling } from "@/features/competition/use-bracket-polling"

export const Route = createFileRoute("/dev/bracket")({
  head: () => ({ meta: [{ title: "對戰樹預覽 · FLOW" }] }),
  component: DevBracketRoute,
})

function DevBracketRoute() {
  // 正式 build 時 DEV 為常數 false，預覽頁與假資料都會被移除
  if (!import.meta.env.DEV) return <NotFoundPage />
  return <BracketPreview />
}

const TEAM_COUNTS = [2, 3, 4, 13, 16, 32] as const
type TeamCountOption = (typeof TEAM_COUNTS)[number] | "pending"

const SCENARIOS: { value: BracketScenario; label: string }[] = [
  { value: "scheduled", label: "全部待開打" },
  { value: "in_progress", label: "進行中" },
  { value: "finished", label: "全部已確認" },
  { value: "third_place_voided", label: "季軍賽取消" },
]

function OptionGroup<T extends string | number>({
  label,
  options,
  value,
  onChange,
}: {
  label: string
  options: { value: T; label: string }[]
  value: T
  onChange: (value: T) => void
}) {
  return (
    <fieldset className="flex flex-wrap items-center gap-2">
      <legend className="mb-2 text-muted-foreground text-overline">
        {label}
      </legend>
      {options.map((option) => (
        <Button
          key={option.value}
          type="button"
          size="sm"
          variant={option.value === value ? "default" : "outline"}
          aria-pressed={option.value === value}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </Button>
      ))}
    </fieldset>
  )
}

function BracketPreview() {
  const queryClient = useQueryClient()
  const [teamCount, setTeamCount] = useState<TeamCountOption>(32)
  const [scenario, setScenario] = useState<BracketScenario>("in_progress")
  const [offline, setOffline] = useState(false)

  const config = `${teamCount}:${scenario}`
  const queryKey = ["dev-bracket", config]
  // 每種設定各自一份假資料；「模擬變動」改的是目前這一份，下一次輪詢就會拿到
  const store = useRef(new Map<string, PublicBracket>())
  const offlineRef = useRef(offline)
  offlineRef.current = offline

  const current = (): PublicBracket => {
    let data = store.current.get(config)
    if (data === undefined) {
      data = {
        ...createBracketFixture({ teamCount: Number(teamCount), scenario }),
        // 換設定時當作另一個賽事，不 flash
        tournament_id: `dev-${config}`,
      }
      store.current.set(config, data)
    }
    return data
  }

  const { bracket, changedMatchIds, connectionLost, lastUpdatedAt } =
    useBracketPolling({
      queryKey,
      queryFn: async () => {
        if (offlineRef.current) throw new Error("模擬斷線")
        return current()
      },
      enabled: teamCount !== "pending",
    })

  const simulateChange = () => {
    store.current.set(config, simulateBracketChange(current()))
    void queryClient.refetchQueries({ queryKey })
  }

  return (
    <div className="flex min-w-0 flex-col gap-6">
      {connectionLost && <ConnectionLostBanner lastUpdatedAt={lastUpdatedAt} />}
      <header className="flex flex-col gap-1">
        <h1 className="text-heading-lg">對戰樹預覽</h1>
        <p className="text-muted-foreground">
          開發模式專用，以假資料每 5 秒輪詢。「模擬斷線」後連續失敗 3 次（約 15
          秒）會出現連線中斷橫幅。
        </p>
      </header>
      <div className="flex flex-col gap-4">
        <OptionGroup<TeamCountOption>
          label="隊數"
          value={teamCount}
          onChange={setTeamCount}
          options={[
            ...TEAM_COUNTS.map((n) => ({ value: n, label: `${n} 隊` })),
            { value: "pending" as const, label: "尚未抽籤" },
          ]}
        />
        <OptionGroup<BracketScenario>
          label="場次狀態"
          value={scenario}
          onChange={setScenario}
          options={SCENARIOS}
        />
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="outline"
            onClick={simulateChange}
            disabled={teamCount === "pending" || offline}
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
      </div>
      <section className="min-w-0 rounded-lg border bg-card p-4">
        {teamCount === "pending" || bracket === undefined ? (
          <BracketPending />
        ) : (
          <BracketTree bracket={bracket} changedMatchIds={changedMatchIds} />
        )}
      </section>
    </div>
  )
}
