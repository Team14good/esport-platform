"""一次性連結的並行保護：同一個重設或驗證連結同時送出，恰好一個成功。

`reset_password` 先鎖帳號、再鎖 token 並重查；`verify_email` 對 token 加鎖後重查。
拿掉任一道鎖或重查，兩個請求都會成功（`credentials_version` 加 2、驗證紀錄兩筆）。

測試用的 `client`、`session` 共用同一條連線與外層交易，兩個交易不可能互搶鎖，所以這裡
自行建立並提交資料，兩個執行緒各用一條連線，以 barrier 同時送出。被只增不改的操作紀錄
參照的帳號刪不掉，留在測試資料庫（每次執行都會重建，比照 test_first_come_concurrency.py）；
token 在結束時刪除。
"""

import secrets
import threading
import uuid
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import delete
from sqlmodel import Session, col, func, select

from app.core import clock
from app.core.audit import AuditLog
from app.core.db import engine
from app.core.errors import BusinessError
from app.modules.identity import service
from app.modules.identity.models import Account, AccountToken, TokenPurpose
from tests.helpers import make_account

ROUNDS = 5
CONNECTIONS = 2


def _issue_token(account_id: uuid.UUID, purpose: TokenPurpose) -> str:
    token = secrets.token_urlsafe(32)
    now = clock.now()
    with Session(engine) as session:
        session.add(
            AccountToken(
                account_id=account_id,
                purpose=purpose,
                token_hash=service.hash_token(token),
                expires_at=now + service.RESET_PASSWORD_TOKEN_TTL,
                created_at=now,
            )
        )
        session.commit()
    return token


def _make_committed_account(*, verified: bool) -> uuid.UUID:
    with Session(engine) as session:
        # 不雜湊密碼，與先搶期併發測試相同
        account = make_account(session, verified=verified, hashed_password="x")
        session.commit()
        return account.id


def _race(action: Callable[[Session], None]) -> list[str]:
    """兩條連線同時執行 `action` 並提交；回傳每個請求的結果（`ok` 或錯誤代碼）。"""
    start = threading.Barrier(CONNECTIONS)

    def _run() -> str:
        with Session(engine) as session:
            try:
                start.wait(timeout=10)
                action(session)
                session.commit()
                return "ok"
            except BusinessError as exc:
                session.rollback()
                return exc.code
            except Exception as exc:  # 讓非預期錯誤出現在斷言訊息裡
                session.rollback()
                return repr(exc)

    with ThreadPoolExecutor(max_workers=CONNECTIONS) as executor:
        futures = [executor.submit(_run) for _ in range(CONNECTIONS)]
        return [f.result(timeout=60) for f in futures]


def _audit_count(account_id: uuid.UUID, action: str) -> int:
    with Session(engine) as session:
        return session.exec(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.entity_id == account_id)
            .where(AuditLog.action == action)
        ).one()


def _delete_tokens(account_id: uuid.UUID) -> None:
    with Session(engine) as session:
        session.execute(
            delete(AccountToken).where(col(AccountToken.account_id) == account_id)
        )
        session.commit()


def test_same_reset_link_submitted_twice_succeeds_exactly_once() -> None:
    for _ in range(ROUNDS):
        account_id = _make_committed_account(verified=True)
        token = _issue_token(account_id, TokenPurpose.RESET_PASSWORD)
        try:
            outcomes = _race(
                lambda session, token=token: service.reset_password(
                    session, token=token, new_password="new-password"
                )
            )

            assert Counter(outcomes) == {"ok": 1, "RESET_LINK_INVALID": 1}, outcomes
            with Session(engine) as session:
                account = session.get(Account, account_id)
                assert account is not None
                assert account.credentials_version == 1
            assert _audit_count(account_id, "account.password_reset") == 1
        finally:
            _delete_tokens(account_id)


def test_same_verification_link_submitted_twice_succeeds_exactly_once() -> None:
    for _ in range(ROUNDS):
        account_id = _make_committed_account(verified=False)
        token = _issue_token(account_id, TokenPurpose.VERIFY_EMAIL)
        try:
            outcomes = _race(
                lambda session, token=token: service.verify_email(session, token=token)
            )

            assert Counter(outcomes) == {"ok": 1, "VERIFICATION_LINK_INVALID": 1}, (
                outcomes
            )
            with Session(engine) as session:
                account = session.get(Account, account_id)
                assert account is not None
                assert account.email_verified is True
            assert _audit_count(account_id, "account.email_verified") == 1
        finally:
            _delete_tokens(account_id)
