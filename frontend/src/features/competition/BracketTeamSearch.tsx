import { ChevronDown, ChevronUp, Search, X } from "lucide-react"
import { useMemo, useRef, useState } from "react"

import type { PublicBracket } from "@/client"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"
import { BracketTree } from "./BracketTree"
import { normalizeTeamQuery, searchBracketTeams } from "./bracket-search"

export const TEAM_SEARCH_PLACEHOLDER = "搜尋隊名"
export const TEAM_SEARCH_NOT_FOUND_TEXT =
  "對戰表上沒有符合的隊伍。候補、已撤回或被退回的隊伍不會出現在對戰表上。"

/** 命中數文字（含「找到 0 隊」） */
export function teamSearchCountText(count: number): string {
  return `找到 ${count} 隊`
}

type BracketTeamSearchProps = {
  query: string
  onQueryChange: (query: string) => void
  /** 有搜尋時的命中隊數；沒有搜尋時為 null（不顯示命中數） */
  hitCount: number | null
  onPrevious: () => void
  onNext: () => void
}

/** Team search（DESIGN.md）：放大鏡＋輸入框＋清除鈕、命中數、多隊時的上一隊／下一隊。 */
export function BracketTeamSearch({
  query,
  onQueryChange,
  hitCount,
  onPrevious,
  onNext,
}: BracketTeamSearchProps) {
  const inputRef = useRef<HTMLInputElement>(null)

  return (
    <div
      data-slot="bracket-team-search"
      className="flex w-full min-w-0 items-center gap-2 sm:max-w-sm"
    >
      <div className="relative min-w-0 flex-1">
        <Search
          aria-hidden="true"
          className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground"
        />
        <Input
          ref={inputRef}
          type="search"
          aria-label={TEAM_SEARCH_PLACEHOLDER}
          placeholder={TEAM_SEARCH_PLACEHOLDER}
          autoComplete="off"
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          className="bg-background pr-9 pl-8 caret-primary dark:bg-background [&::-webkit-search-cancel-button]:appearance-none"
        />
        {query !== "" && (
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label="清除搜尋"
            title="清除搜尋"
            className="absolute top-1/2 right-0.5 -translate-y-1/2 text-muted-foreground"
            onClick={() => {
              onQueryChange("")
              inputRef.current?.focus()
            }}
          >
            <X aria-hidden="true" />
          </Button>
        )}
      </div>
      <span
        role="status"
        data-slot="bracket-team-search-count"
        className={cn(
          "whitespace-nowrap font-semibold text-xs",
          hitCount === 0 ? "text-muted-foreground" : "text-search-highlight",
        )}
      >
        {hitCount === null ? null : teamSearchCountText(hitCount)}
      </span>
      {hitCount !== null && hitCount > 1 && (
        <div className="flex shrink-0 items-center">
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label="上一隊"
            title="上一隊"
            onClick={onPrevious}
          >
            <ChevronUp aria-hidden="true" />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label="下一隊"
            title="下一隊"
            onClick={onNext}
          >
            <ChevronDown aria-hidden="true" />
          </Button>
        </div>
      )}
    </div>
  )
}

type BracketExplorerProps = {
  bracket: PublicBracket
  changedMatchIds?: ReadonlySet<string>
  matchHref?: (matchId: string) => string
}

/**
 * S3 的對戰樹＋隊伍搜尋（4.7）。搜尋內容只存在元件 state、不寫入網址；
 * 輪詢換成新資料時保留輸入與目前高亮的隊伍（依隊伍 id），那隊不再命中時改高亮第一隊。
 */
export function BracketExplorer({
  bracket,
  changedMatchIds,
  matchHref,
}: BracketExplorerProps) {
  const [query, setQuery] = useState("")
  const [selectedTeamId, setSelectedTeamId] = useState<string | null>(null)
  const searching = normalizeTeamQuery(query) !== ""
  const hits = useMemo(
    () => searchBracketTeams(bracket, query),
    [bracket, query],
  )

  const selectedIndex = hits.findIndex((team) => team.id === selectedTeamId)
  const currentIndex = selectedIndex >= 0 ? selectedIndex : 0
  const current = hits[currentIndex] ?? null
  // 原本選的隊伍不再命中：改回第一隊（避免它之後又命中時跳回去）
  if (selectedTeamId !== null && selectedIndex < 0) setSelectedTeamId(null)

  const step = (delta: number) => {
    if (hits.length === 0) return
    const next = (currentIndex + delta + hits.length) % hits.length
    setSelectedTeamId(hits[next].id)
  }

  return (
    <BracketTree
      bracket={bracket}
      changedMatchIds={changedMatchIds}
      matchHref={matchHref}
      highlightTeamId={current?.id ?? null}
      toolbar={
        <BracketTeamSearch
          query={query}
          onQueryChange={(value) => {
            setQuery(value)
            // 換搜尋字時預設高亮第一隊
            setSelectedTeamId(null)
          }}
          hitCount={searching ? hits.length : null}
          onPrevious={() => step(-1)}
          onNext={() => step(1)}
        />
      }
      toolbarNote={
        searching && hits.length === 0 ? (
          <p
            data-slot="bracket-team-search-empty"
            className="mb-2 text-body text-muted-foreground"
          >
            {TEAM_SEARCH_NOT_FOUND_TEXT}
          </p>
        ) : null
      }
    />
  )
}
