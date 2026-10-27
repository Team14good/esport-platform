import { HrefLink } from "@/components/common/HrefLink"

// 品牌 SVG 都用同一個漸層 id，內嵌在同一頁會衝突，所以一律以 <img> 引用 public/brand/ 的檔案。
// 深淺色切換只靠 CSS（.dark），不等 React，避免閃爍。

/**
 * 頂欄左側的 L2 logo：≥ sm 顯示 lockup（高 28px），< sm 只顯示標誌本體。
 * 點擊回首頁；登入後回到目前身分的首頁（`homePath`）。
 */
export function Logo({ homePath = "/" }: { homePath?: string }) {
  return (
    <HrefLink
      href={homePath}
      aria-label="FLOW 首頁"
      className="flex shrink-0 items-center rounded-md outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
    >
      <span className="hidden sm:inline-flex">
        <img
          src="/brand/flow-logo-L2-lockup-light.svg"
          alt=""
          width={162}
          height={50}
          className="h-7 w-auto dark:hidden"
        />
        <img
          src="/brand/flow-logo-L2-lockup-dark.svg"
          alt=""
          width={162}
          height={50}
          className="hidden h-7 w-auto dark:block"
        />
      </span>
      <span className="inline-flex sm:hidden">
        <img
          src="/brand/flow-logo-L2-mark-light.svg"
          alt=""
          width={66}
          height={66}
          className="size-7 dark:hidden"
        />
        <img
          src="/brand/flow-logo-L2-mark.svg"
          alt=""
          width={66}
          height={66}
          className="hidden size-7 dark:block"
        />
      </span>
    </HrefLink>
  )
}
