import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.errors import BusinessError, register_error_handlers


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
