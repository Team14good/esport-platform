"""業務錯誤與其 HTTP 回應格式。

回應格式：`{"detail": {"code": "UPPER_SNAKE", "message": "繁中訊息"}}`；
欄位驗證錯誤沿用 FastAPI 預設的 422，只把 Pydantic 內建的英文 `msg` 換成繁中。要查資料庫才知道的欄位錯誤（例如學校
不存在）拋 `FieldError`：回應與 FastAPI 的 422 同格式，`type` 是錯誤代碼、
`loc` 指向該欄位，前端因此能把訊息顯示在欄位下方。
"""

import re
import typing
from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic_core.core_schema import ErrorType

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


# Pydantic 內建錯誤代碼 -> 繁中訊息。`{name}` 取自錯誤的 `ctx`。
_VALIDATION_MESSAGES: dict[str, str] = {
    "missing": "此欄位必填",
    "json_invalid": "請求內容不是有效的 JSON",
    "model_attributes_type": "格式不正確",
    "dict_type": "格式不正確，需為物件",
    "list_type": "格式不正確，需為清單",
    "tuple_type": "格式不正確，需為清單",
    "set_type": "格式不正確，需為清單",
    "string_type": "請輸入文字",
    "int_type": "請輸入整數",
    "int_parsing": "請輸入整數",
    "int_from_float": "請輸入整數",
    "float_type": "請輸入數字",
    "float_parsing": "請輸入數字",
    "decimal_type": "請輸入數字",
    "decimal_parsing": "請輸入數字",
    "bool_type": "請選擇是或否",
    "bool_parsing": "請選擇是或否",
    "enum": "選項不合法",
    "literal_error": "選項不合法",
    "uuid_type": "格式不正確",
    "uuid_parsing": "格式不正確",
    "datetime_type": "請輸入有效的日期與時間",
    "datetime_parsing": "請輸入有效的日期與時間",
    "datetime_from_date_parsing": "請輸入有效的日期與時間",
    "date_type": "請輸入有效的日期",
    "date_parsing": "請輸入有效的日期",
    "time_type": "請輸入有效的時間",
    "time_parsing": "請輸入有效的時間",
    "url_type": "請輸入有效的網址",
    "url_parsing": "請輸入有效的網址",
    "none_required": "此欄位不接受內容",
    "extra_forbidden": "不接受這個欄位",
    "string_too_short": "至少需要 {min_length} 個字元",
    "string_too_long": "最多 {max_length} 個字元",
    "string_pattern_mismatch": "格式不正確",
    "too_short": "至少需要 {min_length} 筆",
    "too_long": "最多 {max_length} 筆",
    "greater_than": "需大於 {gt}",
    "greater_than_equal": "需大於或等於 {ge}",
    "less_than": "需小於 {lt}",
    "less_than_equal": "需小於或等於 {le}",
    "multiple_of": "需為 {multiple_of} 的倍數",
    "value_error": "值不合法",
    "assertion_error": "值不合法",
}
_GENERIC_VALIDATION_MESSAGE = "欄位內容不正確"
# 自訂錯誤（`PydanticCustomError`、`FieldError`）的 type 不在這份清單內，
# msg 已是繁中，原樣保留。
_BUILTIN_ERROR_TYPES = frozenset(typing.get_args(ErrorType))


def _translate_validation_error(error: dict[str, Any]) -> dict[str, Any]:
    error_type = error.get("type")
    if error_type not in _BUILTIN_ERROR_TYPES:
        return error
    template = _VALIDATION_MESSAGES.get(str(error_type), _GENERIC_VALIDATION_MESSAGE)
    ctx = error.get("ctx") or {}
    try:
        message = template.format(**ctx)
    except KeyError, IndexError:
        message = _GENERIC_VALIDATION_MESSAGE
    return {**error, "msg": message}


async def request_validation_error_handler(
    _request: Request, exc: Exception
) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    errors = [_translate_validation_error(dict(e)) for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(errors)})


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(BusinessError, business_error_handler)
    app.add_exception_handler(RequestValidationError, request_validation_error_handler)
