"""業務錯誤與其 HTTP 回應格式。

回應格式：`{"detail": {"code": "UPPER_SNAKE", "message": "繁中訊息"}}`；
欄位驗證錯誤沿用 FastAPI 預設的 422。要查資料庫才知道的欄位錯誤（例如學校
不存在）拋 `FieldError`：回應與 FastAPI 的 422 同格式，`type` 是錯誤代碼、
`loc` 指向該欄位，前端因此能把訊息顯示在欄位下方。
"""

import re
from collections.abc import Mapping

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*$")


class BusinessError(Exception):
    """service 違反業務規則時拋出；router 不必攔截，由全域 handler 轉成 4xx。"""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        if not _CODE_PATTERN.fullmatch(code):
            raise ValueError(f"BusinessError code must be UPPER_SNAKE: {code!r}")
        if not 400 <= status_code < 500:
            raise ValueError(f"BusinessError status_code must be 4xx: {status_code}")
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        # 額外的回應標頭，例如 401 的 `WWW-Authenticate: Bearer`
        self.headers = dict(headers) if headers else None


class FieldError(BusinessError):
    """某個請求欄位的值違反業務規則：回 422，`loc` 指向該欄位。"""

    def __init__(self, code: str, message: str, *, loc: tuple[str, ...]) -> None:
        super().__init__(code, message, status_code=422)
        self.loc = loc


async def business_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, BusinessError)
    if isinstance(exc, FieldError):
        detail: object = [{"type": exc.code, "loc": list(exc.loc), "msg": exc.message}]
    else:
        detail = {"code": exc.code, "message": exc.message}
    return JSONResponse(
        status_code=exc.status_code, content={"detail": detail}, headers=exc.headers
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(BusinessError, business_error_handler)
