import { MoonIcon, SunIcon } from "lucide-react"

import { useTheme } from "@/components/theme-provider"
import { Button } from "@/components/ui/button"

/** 主題切換：深色時顯示太陽（點了切到淺色），淺色時顯示月亮。 */
export function ThemeToggle({ showLabel = false }: { showLabel?: boolean }) {
  const { theme, toggleTheme } = useTheme()
  const label = theme === "dark" ? "切換為淺色模式" : "切換為深色模式"
  const Icon = theme === "dark" ? SunIcon : MoonIcon

  if (showLabel) {
    return (
      <Button
        variant="ghost"
        className="w-full justify-start"
        onClick={toggleTheme}
      >
        <Icon aria-hidden="true" />
        {label}
      </Button>
    )
  }

  return (
    <Button
      variant="ghost"
      size="icon"
      className="size-touch-target"
      aria-label={label}
      title={label}
      onClick={toggleTheme}
    >
      <Icon aria-hidden="true" />
    </Button>
  )
}
