import { useNavigate } from "@tanstack/react-router"
import { useState } from "react"

import type { PageBannerProps } from "@/components/common/PageBanner"
import { useCurrentAccount, useIsSignedIn } from "@/features/identity/auth"
import { useMyOrganizerApplication } from "@/features/identity/organizer-application"

export const ORGANIZER_APPLY_BANNER_TEXT = "想辦賽事？"
export const ORGANIZER_APPLY_BUTTON_TEXT = "申請成為主辦方"

/** 關閉狀態依帳號 id 分開記錄：同一台電腦換帳號登入時各自顯示。 */
export function organizerBannerDismissedKey(accountId: string): string {
  return `flow-organizer-apply-banner-dismissed:${accountId}`
}

// localStorage 可能被停用或丟例外（隱私模式、儲存空間已滿）：讀不到視為沒關閉
function readDismissed(accountId: string): boolean {
  try {
    return (
      window.localStorage.getItem(organizerBannerDismissedKey(accountId)) ===
      "1"
    )
  } catch {
    return false
  }
}

// 寫不進去時只在本次畫面隱藏（呼叫端另以 state 記錄）
function writeDismissed(accountId: string): void {
  try {
    window.localStorage.setItem(organizerBannerDismissedKey(accountId), "1")
  } catch {
    // 不報錯
  }
}

/**
 * S1 頂部「想辦賽事？」Page banner（UX-DR13）：只給已登入、非主辦方、
 * 最新申請不是待審核的帳號；帳號或申請資料載入中或失敗時不顯示（回傳 null）。
 * 由 S1 放進自己的 `PageBannerSlot`，與其他候選一起決定顯示哪一則。
 */
export function useOrganizerApplyBanner(): PageBannerProps | null {
  const navigate = useNavigate()
  const signedIn = useIsSignedIn()
  const account = useCurrentAccount()
  const application = useMyOrganizerApplication()
  // 本次畫面已關閉的帳號 id（localStorage 寫不進去時也能立即隱藏）
  const [dismissedFor, setDismissedFor] = useState<string | null>(null)

  if (
    !signedIn ||
    account.status !== "success" ||
    application.status !== "success" ||
    account.data.is_organizer ||
    application.data?.status === "pending"
  ) {
    return null
  }
  const accountId = account.data.id
  if (dismissedFor === accountId || readDismissed(accountId)) return null

  return {
    children: ORGANIZER_APPLY_BANNER_TEXT,
    action: {
      label: ORGANIZER_APPLY_BUTTON_TEXT,
      onClick: () => void navigate({ to: "/organizer/apply" }),
    },
    onDismiss: () => {
      writeDismissed(accountId)
      setDismissedFor(accountId)
    },
  }
}
