"""worker 逐筆處理（AD-5）：每筆一個交易；某筆失敗只回滾那一筆。"""

import uuid
from collections.abc import Callable

from sqlmodel import Session, select

from app.modules.identity.models import Account
from app.worker import run_once


def _emails(session: Session, prefix: str) -> list[str]:
    return sorted(
        a.email for a in session.exec(select(Account)) if a.email.startswith(prefix)
    )


def test_each_item_commits_in_its_own_transaction(
    session_factory: Callable[[], Session], session: Session
) -> None:
    prefix = uuid.uuid4().hex
    queue = ["a", "b", "boom", "c"]
    sessions: list[Session] = []

    def one_at_a_time(job_session: Session) -> bool:
        sessions.append(job_session)
        item = queue.pop(0)
        job_session.add(
            Account(
                email=f"{prefix}-{item}@example.com",
                hashed_password="x",
                display_name="逐筆",
            )
        )
        job_session.flush()
        if item == "boom":
            raise RuntimeError("item fails")
        return bool(queue)

    run_once([one_at_a_time], session_factory=session_factory)

    # a、b 已 commit；boom 那筆回滾，並停止這個工作本輪的處理
    assert _emails(session, prefix) == [
        f"{prefix}-a@example.com",
        f"{prefix}-b@example.com",
    ]
    assert queue == ["c"]
    assert len({id(s) for s in sessions}) == 3

    run_once([one_at_a_time], session_factory=session_factory)
    assert f"{prefix}-c@example.com" in _emails(session, prefix)


def test_max_items_caps_one_job_per_round(
    session_factory: Callable[[], Session],
) -> None:
    calls: list[str] = []

    def endless(_session: Session) -> bool:
        calls.append("endless")
        return True

    def after(_session: Session) -> bool:
        calls.append("after")
        return False

    run_once([endless, after], session_factory=session_factory, max_items=3)

    assert calls == ["endless", "endless", "endless", "after"]


def test_session_cleanup_failure_does_not_stop_the_round() -> None:
    calls: list[str] = []

    class BrokenSession:
        def __enter__(self) -> BrokenSession:
            return self

        def __exit__(self, *_args: object) -> None:
            raise ConnectionError("database went away")

        def commit(self) -> None:
            pass

    def broken_factory() -> Session:
        return BrokenSession()  # type: ignore[return-value]

    def job(_session: Session) -> bool:
        calls.append("job")
        return False

    run_once([job, job], session_factory=broken_factory)

    assert calls == ["job", "job"]
