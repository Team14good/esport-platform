import re
import typing
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field
from pydantic.functional_validators import AfterValidator
from pydantic_core import PydanticCustomError
from pydantic_core.core_schema import ErrorType

from app.core.errors import (
    BusinessError,
    FieldError,
    _translate_validation_error,
    register_error_handlers,
)


def _client_raising(error: BusinessError) -> TestClient:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/boom")
    def boom() -> None:
        raise error

    return TestClient(app)


def test_business_error_uses_given_status_and_detail_format() -> None:
    client = _client_raising(BusinessError("SAMPLE_CODE", "繁中訊息", status_code=409))

    response = client.get("/boom")

    assert response.status_code == 409
    assert response.json() == {"detail": {"code": "SAMPLE_CODE", "message": "繁中訊息"}}


def test_business_error_defaults_to_400() -> None:
    client = _client_raising(BusinessError("SAMPLE_CODE", "繁中訊息"))

    response = client.get("/boom")

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "SAMPLE_CODE"


@pytest.mark.parametrize(
    "code", ["sample_code", "Sample", "SAMPLE-CODE", "_SAMPLE", ""]
)
def test_business_error_code_must_be_upper_snake(code: str) -> None:
    with pytest.raises(ValueError):
        BusinessError(code, "繁中訊息")


@pytest.mark.parametrize("status_code", [200, 302, 500])
def test_business_error_status_must_be_4xx(status_code: int) -> None:
    with pytest.raises(ValueError):
        BusinessError("SAMPLE_CODE", "繁中訊息", status_code=status_code)


def test_field_error_uses_fastapi_validation_format() -> None:
    client = _client_raising(
        FieldError("SCHOOL_NOT_FOUND", "找不到這間學校", loc=("body", "school_id"))
    )

    response = client.get("/boom")

    assert response.status_code == 422
    assert response.json() == {
        "detail": [
            {
                "type": "SCHOOL_NOT_FOUND",
                "loc": ["body", "school_id"],
                "msg": "找不到這間學校",
            }
        ]
    }


# ---------------------------------------------------------------- 422 繁中訊息


class _Color(StrEnum):
    RED = "red"
    BLUE = "blue"


def _validate_even(value: int) -> int:
    if value % 2:
        raise PydanticCustomError("not_even", "請輸入偶數")
    return value


class _Payload(BaseModel):
    name: str
    color: _Color
    tags: list[str] = []
    options: dict[str, int] = {}
    count: int = 0
    code: str = Field(default="ab", min_length=2, max_length=3)
    even: Annotated[int, AfterValidator(_validate_even)] = 0


def _validation_client() -> TestClient:
    app = FastAPI()
    register_error_handlers(app)

    @app.post("/payload")
    def payload(body: _Payload) -> None:  # noqa: ARG001
        return None

    return TestClient(app)


_HAS_CJK = re.compile(r"[一-鿿]")


def _post(body: object) -> list[dict[str, object]]:
    response = _validation_client().post("/payload", json=body)

    assert response.status_code == 422
    detail: list[dict[str, object]] = response.json()["detail"]
    assert detail
    for error in detail:
        assert {"type", "loc", "msg"} <= set(error)
        assert _HAS_CJK.search(str(error["msg"])), error
    return detail


def test_validation_missing_field_is_translated_and_keeps_type_and_loc() -> None:
    detail = _post({"color": "red"})

    assert [(e["type"], e["loc"]) for e in detail] == [("missing", ["body", "name"])]
    assert detail[0]["msg"] == "此欄位必填"


def test_validation_unknown_enum_value_is_translated() -> None:
    detail = _post({"name": "a", "color": "green"})

    assert [(e["type"], e["loc"]) for e in detail] == [("enum", ["body", "color"])]
    assert detail[0]["msg"] == "選項不合法"


@pytest.mark.parametrize(
    ("field", "value", "error_type"),
    [
        ("tags", "x", "list_type"),
        ("options", [], "dict_type"),
        ("count", "abc", "int_parsing"),
        ("name", 5, "string_type"),
        ("code", "a", "string_too_short"),
        ("code", "abcd", "string_too_long"),
    ],
)
def test_validation_type_errors_are_translated(
    field: str, value: object, error_type: str
) -> None:
    body: dict[str, object] = {"name": "a", "color": "red", field: value}

    detail = _post(body)

    assert [e["type"] for e in detail] == [error_type]
    assert detail[0]["loc"] == ["body", field]


def test_validation_body_not_an_object_is_translated() -> None:
    detail = _post([1, 2])

    assert detail[0]["loc"] == ["body"]


def test_validation_custom_error_message_is_kept() -> None:
    detail = _post({"name": "a", "color": "red", "even": 3})

    assert [(e["type"], e["loc"], e["msg"]) for e in detail] == [
        ("not_even", ["body", "even"], "請輸入偶數")
    ]


def test_validation_unmapped_builtin_type_uses_generic_message() -> None:
    translated = _translate_validation_error(
        {"type": "bytes_type", "loc": ["body", "x"], "msg": "Input should be bytes"}
    )

    assert translated["msg"] == "欄位內容不正確"
    assert translated["type"] == "bytes_type"


def test_custom_error_types_do_not_collide_with_pydantic_builtin_types() -> None:
    """自訂的 `PydanticCustomError` type 不能和 Pydantic 內建代碼同名，
    否則 handler 會把它的繁中訊息換成通用訊息（例如曾有的 `url_too_long`）。"""
    app_root = Path(__file__).resolve().parents[2] / "app"
    pattern = re.compile(r'PydanticCustomError\(\s*"([a-z0-9_]+)"')
    builtin = set(typing.get_args(ErrorType))

    used = {
        match.group(1)
        for path in app_root.rglob("*.py")
        for match in pattern.finditer(path.read_text(encoding="utf-8"))
    }

    assert used, "找不到任何自訂 type，檢查的正規表示式可能壞了"
    assert used & builtin == set()
