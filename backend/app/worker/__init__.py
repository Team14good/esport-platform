"""worker：同一份程式碼的另一個進入點，角色等同 router（AD-5、AD-7）。

每一輪依序執行工作清單；每個工作各用一個 session、一個交易，成功就 commit，
失敗就 rollback 並記錄日誌，不影響同一輪的其他工作，也不中斷迴圈。
收到 SIGTERM／SIGINT 後會跑完目前這一輪再結束。
"""

import logging
import signal
import time
from collections.abc import Callable, Sequence
from types import FrameType

from sqlmodel import Session

from app.core.db import engine

logger = logging.getLogger(__name__)

Job = Callable[[Session], None]
SessionFactory = Callable[[], Session]


def _default_session_factory() -> Session:
    return Session(engine)


def run_once(
    jobs: Sequence[Job], *, session_factory: SessionFactory = _default_session_factory
) -> None:
    """執行一輪：每個工作一個獨立交易。"""
    for job in jobs:
        name = getattr(job, "__name__", repr(job))
        with session_factory() as session:
            try:
                job(session)
                session.commit()
            except Exception:
                session.rollback()
                logger.exception("Worker job %s failed", name)


class Worker:
    def __init__(
        self,
        jobs: Sequence[Job],
        *,
        poll_seconds: float,
        session_factory: SessionFactory = _default_session_factory,
    ) -> None:
        self.jobs = jobs
        self.poll_seconds = poll_seconds
        self.session_factory = session_factory
        self.stopping = False

    def request_stop(self) -> None:
        """要求在目前這一輪結束後停止。"""
        self.stopping = True

    def install_signal_handlers(self) -> None:
        def _handle(signum: int, _frame: FrameType | None) -> None:
            logger.info("Received signal %s, stopping after current round", signum)
            self.request_stop()

        signal.signal(signal.SIGTERM, _handle)
        signal.signal(signal.SIGINT, _handle)

    def run_forever(self) -> None:
        while not self.stopping:
            run_once(self.jobs, session_factory=self.session_factory)
            self._sleep()

    def _sleep(self) -> None:
        # 分段睡眠，收到停止訊號後最多一秒內結束
        deadline = time.monotonic() + self.poll_seconds
        while not self.stopping:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(1.0, remaining))
