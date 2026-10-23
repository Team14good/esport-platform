from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.errors import BusinessError
from app.main import app


def test_health_check_without_trailing_slash_returns_true(client: TestClient) -> None:
    response = client.get(f"{settings.API_V1_STR}/utils/health-check")

    assert response.status_code == 200
    assert response.json() is True


def test_business_error_handler_is_registered() -> None:
    assert BusinessError in app.exception_handlers


def test_cors_allows_only_frontend_host(client: TestClient) -> None:
    url = f"{settings.API_V1_STR}/utils/health-check"

    allowed = client.get(url, headers={"Origin": settings.FRONTEND_HOST})
    other = client.get(url, headers={"Origin": "http://evil.example.com"})

    assert allowed.headers["access-control-allow-origin"] == settings.FRONTEND_HOST
    assert "access-control-allow-origin" not in other.headers


def test_template_features_are_removed(client: TestClient) -> None:
    paths = set(client.get(f"{settings.API_V1_STR}/openapi.json").json()["paths"])
    removed = ("/login", "/users", "/items", "/private")

    assert f"{settings.API_V1_STR}/utils/health-check" in paths
    assert not [
        path
        for path in paths
        if path.startswith(tuple(f"{settings.API_V1_STR}{p}" for p in removed))
    ]
