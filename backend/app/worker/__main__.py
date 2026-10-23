"""worker 進入點：`python -m app.worker`。"""

import logging

import app.modules  # noqa: F401  載入所有模組的資料表
from app.core.config import settings
from app.worker import Worker
from app.worker.jobs import JOBS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app.worker")


def main() -> None:
    worker = Worker(JOBS, poll_seconds=settings.WORKER_POLL_SECONDS)
    worker.install_signal_handlers()
    logger.info(
        "Worker started: %d job(s), polling every %s seconds",
        len(JOBS),
        settings.WORKER_POLL_SECONDS,
    )
    worker.run_forever()
    logger.info("Worker stopped")


if __name__ == "__main__":
    main()
