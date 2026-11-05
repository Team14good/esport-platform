import type { LinkOptions } from "@tanstack/react-router"
import {
  CalendarClockIcon,
  EyeIcon,
  LayoutDashboardIcon,
  TrophyIcon,
  UserCheckIcon,
} from "lucide-react"

import type { BackofficeNavItem } from "@/components/layout/BackofficeLayout"

export const ORGANIZER_BACKOFFICE_TITLE = "主辦方後台"

/** 主辦方後台（S25、S26）的側欄。 */
export const ORGANIZER_NAV: BackofficeNavItem[] = [
  { to: "/organizer", label: "我的賽事", icon: TrophyIcon },
]

/**
 * 主辦方賽事後台（S27 起）的側欄：最上方「查看賽事頁」連到 S2，下方「總覽」；
 * 之後的 Story（例如 2.7 裁判）把自己的頁面接在「總覽」後面。
 * `BackofficeNavItem` 沒有 `params`，所以 `to` 直接給代入 id 後的實際路徑。
 */
export function tournamentNav(tournamentId: string): BackofficeNavItem[] {
  const id = encodeURIComponent(tournamentId)
  return [
    {
      to: `/tournaments/${id}` as LinkOptions["to"],
      label: "查看賽事頁",
      icon: EyeIcon,
    },
    {
      to: `/organizer/tournaments/${id}` as LinkOptions["to"],
      label: "總覽",
      icon: LayoutDashboardIcon,
    },
    {
      to: `/organizer/tournaments/${id}/matches` as LinkOptions["to"],
      label: "場次管理",
      icon: CalendarClockIcon,
    },
    {
      to: `/organizer/tournaments/${id}/referees` as LinkOptions["to"],
      label: "裁判",
      icon: UserCheckIcon,
    },
  ]
}
