import warnings
from typing import Any

import pytest
from pydantic import ValidationError

from app.core.config import Settings

_REQUIRED: dict[str, Any] = {
    "PROJECT_NAME": "FLOW",
    "DATABASE_URL": "postgresql://postgres:secret@db:5432/app",
    "FIRST_ADMIN_EMAIL": "admin@example.com",
    "FIRST_ADMIN_PASSWORD": "secret-password",
    "SECRET_KEY": "secret-key",
}


@pytest.mark.parametrize("seconds", [14, 31])
def test_worker_poll_seconds_must_be_between_15_and_30(seconds: int) -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings(WORKER_POLL_SECONDS=seconds)  # type: ignore[call-arg]

    assert [error["loc"] for error in exc_info.value.errors()] == [
        ("WORKER_POLL_SECONDS",)
    ]


def test_worker_poll_seconds_defaults_to_20(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WORKER_POLL_SECONDS", raising=False)

    assert Settings(_env_file=None).WORKER_POLL_SECONDS == 20  # type: ignore[call-arg]


@pytest.mark.parametrize(
    ("overrides", "reported_as"),
    [
        ({"SECRET_KEY": "changethis"}, "SECRET_KEY"),
        ({"FIRST_ADMIN_PASSWORD": "changethis"}, "FIRST_ADMIN_PASSWORD"),
        (
            {"DATABASE_URL": "postgresql://postgres:changethis@db:5432/app"},
            "DATABASE_URL password",
        ),
    ],
)
def test_default_secret_is_rejected_outside_development(
    monkeypatch: pytest.MonkeyPatch, overrides: dict[str, str], reported_as: str
) -> None:
    monkeypatch.delenv("FASTAPI_ENV", raising=False)

    with pytest.raises(ValidationError, match=reported_as):
        Settings(  # type: ignore[call-arg]
            _env_file=None,
            **{**_REQUIRED, "FASTAPI_ENV": None, **overrides},
        )


def test_default_secret_only_warns_in_development() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        Settings(  # type: ignore[call-arg]
            _env_file=None,
            **{**_REQUIRED, "FASTAPI_ENV": "development", "SECRET_KEY": "changethis"},
        )

    assert any(
        issubclass(w.category, UserWarning) and "SECRET_KEY" in str(w.message)
        for w in caught
    )
