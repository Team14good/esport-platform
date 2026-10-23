import { TopBar } from "./TopBar"

/** 共用外框：頂欄＋內容區。 */
export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-svh flex-col">
      <TopBar />
      <main className="mx-auto flex w-full max-w-content-max flex-1 flex-col px-gutter-mobile py-6 sm:px-gutter-desktop">
        {children}
      </main>
    </div>
  )
}
