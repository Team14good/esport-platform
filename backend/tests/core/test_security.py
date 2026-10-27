"""core.security：access token 的簽發與解碼、密碼雜湊。"""

import uuid
from datetime import timedelta

import jwt
import pytest

from app.core.config import settings
from app.core.security import (
    ALGORITHM,
    create_access_token,
    decode_access_token,
    get_password_hash,
    verify_password,
)
from tests.conftest import FrozenClock


def _encode(payload: dict[str, object], key: str = settings.SECRET_KEY) -> str:
    return jwt.encode(payload, key, algorithm=ALGORITHM)


@pytest.mark.usefixtures("frozen_clock")
def test_created_token_decodes_to_its_subject() -> None:
    subject = uuid.uuid4()

    token = create_access_token(subject, timedelta(minutes=5))

    assert decode_access_token(token) == str(subject)


def test_exp_is_computed_from_core_clock(frozen_clock: FrozenClock) -> None:
    token = create_access_token("abc", timedelta(days=7))

    payload = jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[ALGORITHM],
        options={"verify_exp": False},
    )
    assert payload["exp"] == int((frozen_clock.now() + timedelta(days=7)).timestamp())
    assert payload["sub"] == "abc"


def test_token_expires_by_core_clock(frozen_clock: FrozenClock) -> None:
    token = create_access_token("abc", timedelta(minutes=10))

    frozen_clock.advance(timedelta(minutes=9, seconds=59))
    assert decode_access_token(token) == "abc"

    frozen_clock.advance(timedelta(seconds=1))
    assert decode_access_token(token) is None


def test_token_signed_with_another_key_is_rejected(frozen_clock: FrozenClock) -> None:
    exp = frozen_clock.now() + timedelta(minutes=5)
    token = _encode({"sub": "abc", "exp": exp}, key="another-secret-key-0123456789")

    assert decode_access_token(token) is None


def test_unsigned_token_is_rejected(frozen_clock: FrozenClock) -> None:
    exp = int((frozen_clock.now() + timedelta(minutes=5)).timestamp())
    token = jwt.encode({"sub": "abc", "exp": exp}, key=None, algorithm="none")

    assert decode_access_token(token) is None


@pytest.mark.parametrize("token", ["", "abc", "a.b.c", "Bearer x.y.z"])
def test_malformed_token_is_rejected(token: str) -> None:
    assert decode_access_token(token) is None


@pytest.mark.parametrize(
    "payload",
    [
        {"exp": 4102444800},  # 沒有 sub
        {"sub": "abc"},  # 沒有 exp
        {"sub": "", "exp": 4102444800},
        {"sub": 123, "exp": 4102444800},
        {"sub": "abc", "exp": "soon"},
        {"sub": "abc", "exp": True},
        {"sub": "abc", "exp": 10**20},
    ],
)
def test_token_with_missing_or_invalid_claims_is_rejected(
    payload: dict[str, object],
) -> None:
    assert decode_access_token(_encode(payload)) is None


def test_password_hash_verifies_only_the_original_password() -> None:
    hashed = get_password_hash("correct horse")

    assert hashed != "correct horse"
    assert verify_password("correct horse", hashed) == (True, None)
    assert verify_password("wrong horse", hashed)[0] is False
