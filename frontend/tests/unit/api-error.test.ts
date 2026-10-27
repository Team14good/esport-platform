import { AxiosError } from "axios"
import { describe, expect, it } from "vitest"

import {
  applyFieldErrors,
  FORBIDDEN_FALLBACK_MESSAGE,
  getErrorMessage,
  NETWORK_ERROR_MESSAGE,
  parseApiError,
  UNAUTHORIZED_FALLBACK_MESSAGE,
  UNEXPECTED_ERROR_MESSAGE,
} from "@/lib/api-error"
import { httpError } from "./helpers"

describe("parseApiError", () => {
  it("422：detail[] 依 loc 的最後一段對應欄位", () => {
    const error = httpError(422, {
      detail: [
        { loc: ["body", "email"], msg: "請輸入有效的 Email", type: "x" },
        { loc: ["body", "email"], msg: "第二個錯誤不顯示", type: "x" },
        { loc: ["body", "password"], msg: "密碼至少 8 個字元", type: "x" },
      ],
    })

    expect(parseApiError(error)).toEqual({
      kind: "validation",
      fields: { email: "請輸入有效的 Email", password: "密碼至少 8 個字元" },
    })
  })

  it("4xx 業務錯誤：照實帶出 code 與 message", () => {
    const error = httpError(409, {
      detail: {
        code: "EMAIL_ALREADY_REGISTERED",
        message: "這個 Email 已經註冊過。",
      },
    })

    expect(parseApiError(error)).toEqual({
      kind: "business",
      code: "EMAIL_ALREADY_REGISTERED",
      message: "這個 Email 已經註冊過。",
    })
  })

  it("403：歸為 forbidden，有業務訊息時照實保留", () => {
    expect(
      parseApiError(
        httpError(403, {
          detail: {
            code: "EMAIL_NOT_VERIFIED",
            message: "請先完成 Email 驗證。",
          },
        }),
      ),
    ).toEqual({
      kind: "forbidden",
      code: "EMAIL_NOT_VERIFIED",
      message: "請先完成 Email 驗證。",
    })
    expect(parseApiError(httpError(403, {}))).toEqual({
      kind: "forbidden",
      message: FORBIDDEN_FALLBACK_MESSAGE,
    })
    // FastAPI 預設的 403 detail 是字串：照實保留，不換成泛用文字
    expect(
      parseApiError(httpError(403, { detail: "Not enough privileges" })),
    ).toEqual({ kind: "forbidden", message: "Not enough privileges" })
  })

  it("401：歸為 unauthorized，保留業務代碼以分辨未登入與帳密錯誤", () => {
    expect(
      parseApiError(
        httpError(401, {
          detail: { code: "AUTHENTICATION_REQUIRED", message: "請先登入。" },
        }),
      ),
    ).toEqual({
      kind: "unauthorized",
      code: "AUTHENTICATION_REQUIRED",
      message: "請先登入。",
    })
    expect(
      parseApiError(
        httpError(401, {
          detail: {
            code: "INVALID_CREDENTIALS",
            message: "Email 或密碼錯誤。",
          },
        }),
      ),
    ).toEqual({
      kind: "unauthorized",
      code: "INVALID_CREDENTIALS",
      message: "Email 或密碼錯誤。",
    })
    expect(
      parseApiError(httpError(401, { detail: "Not authenticated" })),
    ).toEqual({ kind: "unauthorized", message: "Not authenticated" })
    expect(parseApiError(httpError(401, {}))).toEqual({
      kind: "unauthorized",
      message: UNAUTHORIZED_FALLBACK_MESSAGE,
    })
  })

  it("連不到伺服器：沒有回應時顯示「無法連線到伺服器」", () => {
    const error = new AxiosError("Network Error", "ERR_NETWORK")

    expect(parseApiError(error)).toEqual({
      kind: "network",
      message: NETWORK_ERROR_MESSAGE,
    })
    expect(NETWORK_ERROR_MESSAGE).toBe("無法連線到伺服器")
  })

  it("其他錯誤：detail 是字串時照實顯示，否則顯示狀態碼", () => {
    expect(parseApiError(httpError(400, { detail: "Bad request" }))).toEqual({
      kind: "unknown",
      message: "Bad request",
    })
    expect(parseApiError(httpError(500, "Internal Server Error"))).toEqual({
      kind: "unknown",
      message: "伺服器發生錯誤（500）",
    })
    expect(parseApiError(new Error("boom")).kind).toBe("unknown")
    expect(parseApiError(undefined).kind).toBe("unknown")
  })

  it("getErrorMessage 把欄位錯誤合併成一行", () => {
    expect(
      getErrorMessage({ kind: "validation", fields: { a: "甲", b: "乙" } }),
    ).toBe("甲；乙")
    expect(
      getErrorMessage({ kind: "business", code: "X", message: "訊息" }),
    ).toBe("訊息")
  })

  it("422 欄位名是 Object.prototype 上的名稱（constructor）時也照常收集", () => {
    const error = httpError(422, {
      detail: [
        { loc: ["body", "constructor"], msg: "建構子欄位錯誤", type: "x" },
        { loc: ["body", "toString"], msg: "字串欄位錯誤", type: "x" },
      ],
    })

    expect(parseApiError(error)).toEqual({
      kind: "validation",
      fields: { constructor: "建構子欄位錯誤", toString: "字串欄位錯誤" },
    })
  })

  it("422 沒有任何可用的欄位錯誤時，改用依狀態碼的訊息，不會是空白", () => {
    const empty = httpError(422, { detail: [] })
    const noMsg = httpError(422, { detail: [{ loc: ["body", "email"] }] })

    for (const error of [empty, noMsg]) {
      const apiError = parseApiError(error)
      expect(apiError).toEqual({
        kind: "unknown",
        message: "伺服器發生錯誤（422）",
      })
      expect(getErrorMessage(apiError)).not.toBe("")
    }
    // 表單也不會什麼都不顯示
    const form = {
      setError: () => {},
      getValues: () => ({ email: "" }),
    } as never
    expect(applyFieldErrors(form, empty)).toEqual({
      kind: "unknown",
      message: "伺服器發生錯誤（422）",
    })
  })

  it("getErrorMessage 在文字為空時改用「發生未預期的錯誤」", () => {
    expect(getErrorMessage({ kind: "validation", fields: {} })).toBe(
      UNEXPECTED_ERROR_MESSAGE,
    )
    expect(getErrorMessage({ kind: "unknown", message: "" })).toBe(
      UNEXPECTED_ERROR_MESSAGE,
    )
  })
})
