"""未登入呼叫任何寫入 API 一律回 401（AD-10）；只有公開清單上的端點例外。

逐一列舉 app 的所有寫入路由（取自 OpenAPI 規格：FastAPI 0.141 起 include 的 router
不再展開到 `app.routes`），之後新增的路由也會自動被檢查：沒有套用
`CurrentAccount`（或更嚴格的依賴）的寫入端點，必須明確加進公開清單。
"""

import re
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.modules.identity.router import PUBLIC_WRITE_ROUTES

APP_DIR = Path(__file__).resolve().parents[1] / "app"
API = settings.API_V1_STR
WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
PUBLIC = {(method, f"{API}{path}") for method, path in PUBLIC_WRITE_ROUTES}


def _write_routes() -> list[tuple[str, str]]:
    return sorted(
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        for method in operations
        if method.upper() in WRITE_METHODS
    )


def test_no_route_is_hidden_from_the_openapi_schema() -> None:
    # 列舉靠 OpenAPI；include_in_schema=False 的路由會被漏掉，所以不允許使用
    for path in APP_DIR.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "include_in_schema" not in source, path.relative_to(APP_DIR)


PROTECTED = [route for route in _write_routes() if route not in PUBLIC]


def test_public_list_matches_existing_routes() -> None:
    # 公開清單的每一項都要真的存在，避免清單過期而掩蓋問題
    assert PUBLIC <= set(_write_routes())


def test_protected_write_routes_are_enumerated() -> None:
    assert ("PATCH", f"{API}/accounts/me") in PROTECTED


@pytest.mark.parametrize(("method", "path"), PROTECTED)
def test_write_route_without_token_is_401(
    client: TestClient, method: str, path: str
) -> None:
    url = re.sub(r"\{[^}]+\}", str(uuid.uuid4()), path)

    response = client.request(method, url, json={})

    assert response.status_code == 401, f"{method} {path}"
    assert response.json()["detail"]["code"] == "AUTHENTICATION_REQUIRED"
