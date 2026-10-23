import { AxiosError, AxiosHeaders } from "axios"

// 產生的 client（throwOnError）丟出的是 AxiosError；用真的 AxiosError 確認形狀相符
export function httpError(status: number, data: unknown) {
  const config = { headers: new AxiosHeaders() }
  return new AxiosError(
    `Request failed with status code ${status}`,
    "ERR_BAD_REQUEST",
    config,
    {},
    { status, statusText: "", data, headers: {}, config },
  )
}
