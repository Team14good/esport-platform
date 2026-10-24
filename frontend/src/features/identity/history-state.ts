// 註冊成功後把剛註冊的 Email 放在 history state 帶到 S7，不放進網址（避免留在瀏覽紀錄）。
declare module "@tanstack/react-router" {
  interface HistoryState {
    registeredEmail?: string
  }
}

export {}
