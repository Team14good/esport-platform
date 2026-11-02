import { Link } from "@tanstack/react-router"
import type { ReactNode } from "react"

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import type { FileRouteTypes } from "@/routeTree.gen"

// S2 的分頁列。每個分頁是一個路由（S3 對戰表是 `/tournaments/$tournamentId/bracket`），
// 分頁按鈕是連結；之後的 Story（4.6 對戰表、3.9 正取隊伍）在 TOURNAMENT_TABS 加上自己的分頁。

/** 分頁可以連到的路由：賽事頁底下、但不是 S4 場次頁（`matches/`，不在分頁列） */
type TournamentTabPath = Exclude<
  Extract<FileRouteTypes["to"], `/tournaments/$tournamentId${string}`>,
  `${string}/matches/${string}`
>

// 分頁的白名單：新增分頁只要在這裡加一項，`TournamentTab` 跟著推導
const TOURNAMENT_TABS = [
  { value: "overview", label: "總覽", to: "/tournaments/$tournamentId" },
] as const satisfies ReadonlyArray<{
  value: string
  label: string
  to: TournamentTabPath
}>

export type TournamentTab = (typeof TOURNAMENT_TABS)[number]["value"]

type TournamentTabsProps = {
  tournamentId: string
  /** 目前所在的分頁 */
  current: TournamentTab
  /** 目前分頁的內容 */
  children: ReactNode
}

/** S2 的分頁列＋目前分頁的內容。 */
export function TournamentTabs({
  tournamentId,
  current,
  children,
}: TournamentTabsProps) {
  return (
    <Tabs value={current} className="gap-4">
      <TabsList className="max-w-full overflow-x-auto">
        {TOURNAMENT_TABS.map((tab) => (
          <TabsTrigger key={tab.value} value={tab.value} asChild>
            <Link to={tab.to} params={{ tournamentId }}>
              {tab.label}
            </Link>
          </TabsTrigger>
        ))}
      </TabsList>
      <TabsContent value={current}>{children}</TabsContent>
    </Tabs>
  )
}
