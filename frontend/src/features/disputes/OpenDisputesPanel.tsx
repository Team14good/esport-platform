import { useQuery } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import type { ReactNode } from "react"

import { formatMatchDateTime } from "@/features/competition/match-time"
import { getErrorMessage, parseApiError } from "@/lib/api-error"
import { openDisputesQueryOptions, sortOpenItems } from "./organizer-queries"

export const OPEN_DISPUTES_TITLE = "待處理"
export const NO_OPEN_DISPUTES_TEXT = "目前沒有待處理的申訴或檢舉。"
const KIND_LABEL = { appeal: "申訴", report: "檢舉" } as const
// 申訴進 S32、檢舉進 S33
const KIND_ROUTE = {
  appeal: "/organizer/tournaments/$tournamentId/appeals",
  report: "/organizer/tournaments/$tournamentId/reports",
} as const

/**
 * S27 待處理清單：待處理申訴數、檢舉數與每一筆（類型、場次或被檢舉隊名、提出時間、
 * 處理期限），依處理期限由近到遠，沒有期限的檢舉排最後；申訴點選進 S32、檢舉進 S33。
 * 期中不做逾期變色（6.3）。
 */
export function OpenDisputesPanel({ tournamentId }: { tournamentId: string }) {
  const disputes = useQuery(openDisputesQueryOptions(tournamentId))

  let content: ReactNode
  if (disputes.data) {
    const items = sortOpenItems(disputes.data.items)
    content = (
      <>
        <div className="flex flex-wrap gap-x-4 gap-y-1">
          <p className="text-body">
            待處理申訴{" "}
            <span className="font-medium">{disputes.data.appeals}</span> 件
          </p>
          <p className="text-body">
            待處理檢舉{" "}
            <span className="font-medium">{disputes.data.reports}</span> 件
          </p>
        </div>
        {items.length === 0 ? (
          <p className="text-body text-muted-foreground">
            {NO_OPEN_DISPUTES_TEXT}
          </p>
        ) : (
          <ul className="flex flex-col gap-2">
            {items.map((item) => {
              const subject =
                item.kind === "report" ? item.team_name : item.match_code
              return (
                <li key={`${item.kind}-${item.id}`}>
                  <Link
                    to={KIND_ROUTE[item.kind]}
                    params={{ tournamentId }}
                    data-slot="open-dispute"
                    className="flex flex-col gap-1 rounded-md border p-3 text-body hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring sm:flex-row sm:flex-wrap sm:items-center sm:gap-x-4"
                  >
                    <span className="font-medium">
                      {KIND_LABEL[item.kind]}
                      {subject ? ` · ${subject}` : ""}
                    </span>
                    <span className="text-caption text-muted-foreground">
                      提出 {formatMatchDateTime(item.filed_at)}
                    </span>
                    {item.deadline ? (
                      <span className="text-caption">
                        處理期限 {formatMatchDateTime(item.deadline)}
                      </span>
                    ) : null}
                  </Link>
                </li>
              )
            })}
          </ul>
        )}
      </>
    )
  } else if (disputes.isError) {
    content = (
      <p className="text-body text-destructive">
        {getErrorMessage(parseApiError(disputes.error))}
      </p>
    )
  } else {
    content = (
      <p role="status" className="text-body text-muted-foreground">
        載入中
      </p>
    )
  }

  return (
    <section
      aria-labelledby={`open-disputes-${tournamentId}`}
      className="flex flex-col gap-3 rounded-lg border bg-card p-4"
    >
      <h2 id={`open-disputes-${tournamentId}`} className="text-heading-md">
        {OPEN_DISPUTES_TITLE}
      </h2>
      {content}
    </section>
  )
}
