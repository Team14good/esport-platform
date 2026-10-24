"""worker：同一份程式碼的另一個進入點，角色等同 router（AD-5、AD-7）。

每一輪依序執行工作清單。工作一次只處理一筆（一則事件、一封信），回傳是否
處理了一筆；worker 為每一筆開一個 session、一個交易，成功就 commit，再呼叫
同一個工作處理下一筆，直到工作回傳 False 或達到 `max_items`。某一筆失敗就
rollback 並記錄日誌，改執行下一個工作；不影響其他工作，也不中斷迴圈。
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

# 處理一筆；True 代表處理了一筆、可能還有下一筆
Job = Callable[[Session], bool]
SessionFactory = Callable[[], Session]

# 每個工作每一輪最多處理的筆數，避免單一工作佔住整輪
DEFAULT_MAX_ITEMS = 100


def _default_session_factory() -> Session:
    return Session(engine)


def _run_item(job: Job, name: str, session_factory: SessionFactory) -> bool:
    """以一個獨立交易處理一筆；回傳是否要繼續處理下一筆。"""
    try:
        with session_factory() as session:
            try:
                more = job(session)
                session.commit()
            except Exception:
                logger.exception("Worker job %s failed", name)
                session.rollback()
                return False
    except Exception:
        # rollback 或關閉 session 本身失敗（例如資料庫斷線）：記錄後繼續，不讓 worker 結束
        logger.exception("Worker job %s could not clean up its session", name)
        return False
    return more


def run_once(
    jobs: Sequence[Job],
    *,
    session_factory: SessionFactory = _default_session_factory,
    max_items: int = DEFAULT_MAX_ITEMS,
) -> None:
    """執行一輪：每個工作逐筆處理，每筆一個獨立交易。"""
    for job in jobs:
        name = getattr(job, "__name__", repr(job))
        for _ in range(max_items):
            if not _run_item(job, name, session_factory):
                break


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
