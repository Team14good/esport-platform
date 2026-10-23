"""業務錯誤與其 HTTP 回應格式。

回應格式：`{"detail": {"code": "UPPER_SNAKE", "message": "繁中訊息"}}`；
欄位驗證錯誤沿用 FastAPI 預設的 422。
"""

import re

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*$")


class BusinessError(Exception):
    """service 違反業務規則時拋出；router 不必攔截，由全域 handler 轉成 4xx。"""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        if not _CODE_PATTERN.fullmatch(code):
            raise ValueError(f"BusinessError code must be UPPER_SNAKE: {code!r}")
        if not 400 <= status_code < 500:
            raise ValueError(f"BusinessError status_code must be 4xx: {status_code}")
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


async def business_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, BusinessError)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": {"code": exc.code, "message": exc.message}},
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(BusinessError, business_error_handler)
