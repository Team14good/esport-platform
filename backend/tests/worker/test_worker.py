import logging
import os
import queue
import signal
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Callable

import pytest
from sqlmodel import Session, select

from app.core.config import settings
from app.modules.identity.models import Account
from app.worker import Worker, run_once


def _add_account(session: Session, email: str) -> None:
    session.add(Account(email=email, hashed_password="x", display_name="worker 測試"))
    session.flush()


def _exists(session: Session, email: str) -> bool:
    return (
        session.exec(select(Account).where(Account.email == email)).first() is not None
    )


def test_failed_job_rolls_back_and_next_job_still_commits(
    session_factory: Callable[[], Session],
    session: Session,
    caplog: pytest.LogCaptureFixture,
) -> None:
    failed_email = f"{uuid.uuid4().hex}@example.com"
    ok_email = f"{uuid.uuid4().hex}@example.com"

    def failing_job(job_session: Session) -> None:
        _add_account(job_session, failed_email)
        raise RuntimeError("boom")

    def ok_job(job_session: Session) -> None:
        _add_account(job_session, ok_email)

    with caplog.at_level(logging.ERROR, logger="app.worker"):
        run_once([failing_job, ok_job], session_factory=session_factory)

    assert not _exists(session, failed_email)
    assert _exists(session, ok_email)
    assert any(
        record.levelno == logging.ERROR and "failing_job" in record.getMessage()
        for record in caplog.records
    )


def test_sigterm_finishes_current_round_then_stops(
    session_factory: Callable[[], Session],
) -> None:
    executed: list[str] = []

    def receives_sigterm(_session: Session) -> None:
        executed.append("first")
        signal.raise_signal(signal.SIGTERM)

    def runs_after_signal(_session: Session) -> None:
        executed.append("second")

    worker = Worker(
        [receives_sigterm, runs_after_signal],
        poll_seconds=30,
        session_factory=session_factory,
    )
    previous_term = signal.getsignal(signal.SIGTERM)
    previous_int = signal.getsignal(signal.SIGINT)
    try:
        worker.install_signal_handlers()
        worker.run_forever()
    finally:
        signal.signal(signal.SIGTERM, previous_term)
        signal.signal(signal.SIGINT, previous_int)

    assert executed == ["first", "second"]


def test_loop_keeps_running_after_a_failed_round(
    session_factory: Callable[[], Session],
) -> None:
    rounds: list[int] = []
    worker: Worker

    def flaky_job(_session: Session) -> None:
        rounds.append(len(rounds) + 1)
        if len(rounds) == 1:
            raise RuntimeError("first round fails")
        worker.request_stop()

    worker = Worker([flaky_job], poll_seconds=0, session_factory=session_factory)
    worker.run_forever()

    assert rounds == [1, 2]


def test_stop_request_during_sleep_returns_promptly(
    session_factory: Callable[[], Session],
) -> None:
    worker = Worker([], poll_seconds=30, session_factory=session_factory)
    timer = threading.Timer(0.5, worker.request_stop)

    started = time.monotonic()
    timer.start()
    try:
        worker.run_forever()
    finally:
        timer.cancel()

    assert time.monotonic() - started < 2


def test_entry_point_stops_cleanly_on_sigterm() -> None:
    # 真正的進入點：python -m app.worker；連線指向測試資料庫以免碰到開發資料庫
    env = {**os.environ, "DATABASE_URL": str(settings.DATABASE_URL)}
    process = subprocess.Popen(
        [sys.executable, "-m", "app.worker"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )
    lines: queue.Queue[str] = queue.Queue()
    output: list[str] = []

    def _read() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            lines.put(line)

    threading.Thread(target=_read, daemon=True).start()

    def _wait_for(text: str, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while (remaining := deadline - time.monotonic()) > 0:
            try:
                line = lines.get(timeout=remaining)
            except queue.Empty:
                return False
            output.append(line)
            if text in line:
                return True
        return False

    try:
        assert _wait_for("Worker started", timeout=15), "".join(output)
        process.send_signal(signal.SIGTERM)
        assert process.wait(timeout=5) == 0
        assert _wait_for("Worker stopped", timeout=2), "".join(output)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
