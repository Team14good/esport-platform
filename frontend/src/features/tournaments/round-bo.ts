import type { RoundBo } from "@/client"

/** 名額 N 的單淘汰總輪數＝⌈log₂N⌉（與後端 `service.total_rounds` 相同；N ≥ 2）。 */
export function totalRounds(capacity: number): number {
  let rounds = 0
  while (2 ** rounds < capacity) rounds += 1
  return rounds
}

/**
 * 距決賽 `roundsFromFinal` 輪的名稱：決賽、4 強、8 強…
 * 與後端 `competition/bracket.round_name` 一致。
 */
export function roundLabel(roundsFromFinal: number): string {
  return roundsFromFinal === 0 ? "決賽" : `${2 ** (roundsFromFinal + 1)} 強`
}

/** S27 顯示用：「決賽 BO5、4 強 BO3」，依距決賽的輪數由小到大。 */
export function formatRoundBo(roundBo: readonly RoundBo[]): string {
  return [...roundBo]
    .sort((a, b) => a.rounds_from_final - b.rounds_from_final)
    .map((item) => `${roundLabel(item.rounds_from_final)} BO${item.bo}`)
    .join("、")
}
