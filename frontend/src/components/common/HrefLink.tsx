import { useRouter } from "@tanstack/react-router"
import type { ComponentProps } from "react"

type HrefLinkProps = ComponentProps<"a"> & { href: string }

/**
 * 站內連結，目的地是執行期才知道的完整路徑（例如後端給的身分首頁，或帶 ?query 的
 * redirect）：交給 router 的 history 導覽、不整頁重新載入。Link 的 to 只接受已登錄的
 * 路由，查詢參數也會被當成路徑的一部分，所以這類連結不用 Link。
 */
export function HrefLink({ href, onClick, ...props }: HrefLinkProps) {
  const router = useRouter()
  return (
    <a
      href={href}
      {...props}
      onClick={(event) => {
        onClick?.(event)
        // 新分頁開啟等修飾鍵點擊交給瀏覽器
        if (
          event.defaultPrevented ||
          event.button !== 0 ||
          event.metaKey ||
          event.ctrlKey ||
          event.shiftKey ||
          event.altKey
        ) {
          return
        }
        event.preventDefault()
        router.history.push(href)
      }}
    />
  )
}
