from dataclasses import dataclass
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


@dataclass(frozen=True)
class AccessTokenClaims:
    """解碼後的 access token：`subject` 是帳號 id，`version` 是簽發時的憑證版本。"""

    subject: str
    version: int


def create_access_token(
    subject: str | Any, expires_delta: timedelta, *, version: int
) -> str:
    """簽發 access token；`version` 寫進 `ver` claim（帳號的憑證版本）。

    `version` 必填：漏傳帳號目前的版本，簽出的 token 會在第一次重設密碼後悄悄失效。
    """
    expire = clock.now() + expires_delta
    to_encode = {"exp": expire, "sub": str(subject), "ver": version}
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> AccessTokenClaims | None:
    """驗證簽章與到期時間，回傳 `sub` 與 `ver`；簽章錯誤、格式錯誤、過期或缺欄位都回傳 None。

    到期時間以 `clock.now()` 判斷（不用 PyJWT 內建、讀真實時間的 exp 檢查），
    測試替換時鐘後才能推進到過期。沒有 `ver` 的 token（Story 1.5 以前簽發）視為 0；
    `ver` 存在但不是非負整數時視為無效。
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
    version = payload.get("ver", 0)
    # bool 是 int 的子類別，要先排除
    if isinstance(exp, bool) or not isinstance(exp, int | float):
        return None
    if not isinstance(subject, str) or not subject:
        return None
    if isinstance(version, bool) or not isinstance(version, int) or version < 0:
        return None
    try:
        expires_at = datetime.fromtimestamp(exp, UTC)
    except OverflowError, OSError, ValueError:
        return None
    if expires_at <= clock.now():
        return None
    return AccessTokenClaims(subject=subject, version=version)


def verify_password(
    plain_password: str, hashed_password: str
) -> tuple[bool, str | None]:
    return password_hash.verify_and_update(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return password_hash.hash(password)
