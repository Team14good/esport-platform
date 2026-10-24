import {
  CheckIcon,
  ChevronsUpDownIcon,
  RotateCwIcon,
  XIcon,
} from "lucide-react"
import { type ComponentProps, useState } from "react"

import type { PublicSchool } from "@/client"
import { Button } from "@/components/ui/button"
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import { cn } from "@/lib/utils"

export const SCHOOL_NOT_FOUND_TEXT = "找不到這間學校"
export const SCHOOL_LIST_ERROR_TEXT = "無法載入學校清單"

/** 不分大小寫、部分符合（cmdk 預設的模糊比對會讓不相干的校名也出現）。 */
export function matchSchool(name: string, search: string): boolean {
  const keyword = search.trim().toLowerCase()
  return keyword === "" || name.toLowerCase().includes(keyword)
}

type SchoolPickerProps = {
  schools: PublicSchool[]
  /** 選取的學校 id；null 代表不選 */
  value: string | null
  onChange: (schoolId: string | null) => void
  loading?: boolean
  /** 學校清單載入失敗：停用選單，顯示「無法載入學校清單」與「重新載入」 */
  loadError?: boolean
  onRetry?: () => void
  placeholder?: string
  onBlur?: () => void
} & Pick<
  ComponentProps<"button">,
  "id" | "aria-describedby" | "aria-invalid" | "disabled"
>

/**
 * School picker：Popover＋Command 的可搜尋下拉，只能從學校清單選擇、不能自由輸入；
 * 選了之後可以清除（S5、S10 學校為選填）。
 */
export function SchoolPicker({
  schools,
  value,
  onChange,
  loading = false,
  loadError = false,
  onRetry,
  placeholder = "選擇學校（選填）",
  onBlur,
  disabled,
  ...triggerProps
}: SchoolPickerProps) {
  const [open, setOpen] = useState(false)
  const selected = schools.find((school) => school.id === value) ?? null
  const unavailable = Boolean(disabled) || loading || loadError
  const triggerText = loadError
    ? SCHOOL_LIST_ERROR_TEXT
    : loading
      ? "載入學校清單中"
      : (selected?.name ?? placeholder)

  return (
    <div className="flex flex-col gap-2">
      <div className="relative">
        <Popover
          open={open}
          onOpenChange={(next) => {
            setOpen(next)
            if (!next) onBlur?.()
          }}
        >
          <PopoverTrigger asChild>
            <Button
              type="button"
              variant="outline"
              role="combobox"
              aria-expanded={open}
              aria-haspopup="listbox"
              disabled={unavailable}
              className={cn(
                "h-9 w-full justify-between px-3 font-normal aria-invalid:border-destructive",
                selected && "pr-16",
              )}
              {...triggerProps}
            >
              <span
                className={cn("truncate", !selected && "text-muted-foreground")}
              >
                {triggerText}
              </span>
              <ChevronsUpDownIcon aria-hidden="true" className="opacity-50" />
            </Button>
          </PopoverTrigger>
          <PopoverContent
            align="start"
            className="w-(--radix-popover-trigger-width) min-w-64 p-0"
          >
            <Command
              label="搜尋學校"
              filter={(itemValue, search) =>
                matchSchool(itemValue, search) ? 1 : 0
              }
            >
              <CommandInput placeholder="輸入校名搜尋" />
              <CommandList>
                <CommandEmpty>{SCHOOL_NOT_FOUND_TEXT}</CommandEmpty>
                <CommandGroup>
                  {schools.map((school) => (
                    <CommandItem
                      key={school.id}
                      value={school.name}
                      onSelect={() => {
                        onChange(school.id)
                        setOpen(false)
                        onBlur?.()
                      }}
                    >
                      <CheckIcon
                        aria-hidden="true"
                        className={cn(
                          school.id === value ? "opacity-100" : "opacity-0",
                        )}
                      />
                      {school.name}
                    </CommandItem>
                  ))}
                </CommandGroup>
              </CommandList>
            </Command>
          </PopoverContent>
        </Popover>
        {selected && !unavailable && (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label="清除學校"
            className="absolute top-0 right-8 size-9"
            onClick={() => {
              onChange(null)
              onBlur?.()
            }}
          >
            <XIcon aria-hidden="true" />
          </Button>
        )}
      </div>
      {loadError && onRetry && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="self-start"
          onClick={onRetry}
        >
          <RotateCwIcon aria-hidden="true" />
          重新載入
        </Button>
      )}
    </div>
  )
}
