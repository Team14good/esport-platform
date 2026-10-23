import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react"

// 主題只有深色與淺色；深色為預設，不跟隨作業系統。
// index.html 有一段內聯 script 用同一個 key 在繪製前套用主題，兩邊要一起改。
export type Theme = "dark" | "light"

export const THEME_STORAGE_KEY = "flow-theme"
export const DEFAULT_THEME: Theme = "dark"

export function readStoredTheme(): Theme {
  try {
    return window.localStorage.getItem(THEME_STORAGE_KEY) === "light"
      ? "light"
      : "dark"
  } catch {
    return DEFAULT_THEME
  }
}

function writeStoredTheme(theme: Theme) {
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme)
  } catch {
    // 無法存取 localStorage 時仍可切換，只是不保存
  }
}

function applyTheme(theme: Theme) {
  const root = window.document.documentElement
  root.classList.remove("light", "dark")
  root.classList.add(theme)
}

type ThemeProviderProps = {
  children: React.ReactNode
}

type ThemeProviderState = {
  theme: Theme
  setTheme: (theme: Theme) => void
  toggleTheme: () => void
}

const ThemeProviderContext = createContext<ThemeProviderState | undefined>(
  undefined,
)

export function ThemeProvider({ children }: ThemeProviderProps) {
  const [theme, setThemeState] = useState<Theme>(readStoredTheme)

  useEffect(() => {
    applyTheme(theme)
  }, [theme])

  const setTheme = useCallback((next: Theme) => {
    writeStoredTheme(next)
    setThemeState(next)
  }, [])

  const toggleTheme = useCallback(() => {
    setTheme(theme === "dark" ? "light" : "dark")
  }, [theme, setTheme])

  return (
    <ThemeProviderContext.Provider value={{ theme, setTheme, toggleTheme }}>
      {children}
    </ThemeProviderContext.Provider>
  )
}

export const useTheme = () => {
  const context = useContext(ThemeProviderContext)

  if (context === undefined)
    throw new Error("useTheme must be used within a ThemeProvider")

  return context
}
