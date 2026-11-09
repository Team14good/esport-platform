import type { AppealDecision } from "@/client"

/** 申訴處理決定的顯示文字（S32 列表與操作、S4 處理結果共用）。 */
export const DECISION_LABEL: Record<AppealDecision, string> = {
  upheld: "維持原結果",
  corrected: "更正結果",
  rematch: "重新比賽",
}
