from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from pwdlib.hashers.bcrypt import BcryptHasher

from app.core import clock
from app.core.config import settings

password_hash = PasswordHash(
    (
        Argon2Hasher(),
        BcryptHasher(),
    )
)


ALGORITHM = "HS256"


def create_access_token(subject: str | Any, expires_delta: timedelta) -> str:
    expire = clock.now() + expires_delta
    to_encode = {"exp": expire, "sub": str(subject)}
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> str | None:
    """驗證簽章與到期時間，回傳 `sub`；簽章錯誤、格式錯誤、過期或缺欄位都回傳 None。

    到期時間以 `clock.now()` 判斷（不用 PyJWT 內建、讀真實時間的 exp 檢查），
    測試替換時鐘後才能推進到過期。
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[ALGORITHM],
            options={"verify_exp": False, "require": ["exp", "sub"]},
        )
    except jwt.InvalidTokenError:
        return None
    exp = payload.get("exp")
    subject = payload.get("sub")
    # bool 是 int 的子類別，要先排除
    if isinstance(exp, bool) or not isinstance(exp, int | float):
        return None
    if not isinstance(subject, str) or not subject:
        return None
    try:
        expires_at = datetime.fromtimestamp(exp, UTC)
    except OverflowError, OSError, ValueError:
        return None
    if expires_at <= clock.now():
        return None
    return subject


def verify_password(
    plain_password: str, hashed_password: str
) -> tuple[bool, str | None]:
    return password_hash.verify_and_update(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return password_hash.hash(password)
