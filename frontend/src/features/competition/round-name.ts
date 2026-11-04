/**
 * 輪次欄的名稱：決賽、4 強、8 強、16 強…（與後端 `bracket.round_name` 同一套規則）。
 * 季軍賽與決賽同輪，但季軍賽一律顯示「季軍賽」，不可用這個函式命名。
 */
export function roundName(roundNo: number, rounds: number): string {
  const teamsLeft = 2 ** (rounds - roundNo + 1)
  return teamsLeft === 2 ? "決賽" : `${teamsLeft} 強`
}
