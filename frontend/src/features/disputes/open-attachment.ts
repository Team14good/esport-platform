import { toast } from "sonner"

import { notifyError } from "@/lib/feedback"

export const POPUP_BLOCKED_TEXT =
  "瀏覽器擋下了新分頁，請允許這個網站開啟彈出式視窗後再查看附件。"

// 附件的物件網址在新分頁開啟後保留一段時間再釋放
const ATTACHMENT_URL_TTL_MS = 60_000

/**
 * 以登入者的權杖下載附件（S32 申訴、S33 檢舉），於新分頁開啟；失敗時關閉分頁並以錯誤
 * Toast 顯示。分頁要在點擊當下（`await` 之前）開啟，Firefox、Safari 才不會當成彈出式
 * 視窗擋下；下載完成後再把分頁導到附件。
 */
export async function openAttachment(
  download: () => Promise<{ data: unknown }>,
) {
  const tab = window.open("", "_blank")
  if (!tab) {
    toast.error(POPUP_BLOCKED_TEXT, {
      id: POPUP_BLOCKED_TEXT,
      duration: Number.POSITIVE_INFINITY,
      closeButton: true,
    })
    return
  }
  // 新分頁不能反過來操作本頁（等同 noopener）
  tab.opener = null
  try {
    const { data } = await download()
    const url = URL.createObjectURL(data as Blob)
    tab.location.href = url
    setTimeout(() => URL.revokeObjectURL(url), ATTACHMENT_URL_TTL_MS)
  } catch (error) {
    tab.close()
    notifyError(error)
  }
}
