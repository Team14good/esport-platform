"""worker 每一輪要執行的工作清單（依序執行）。

之後的 Story 在這裡登錄工作，例如消化 outbox（Story 1.3）與各種到期規則。
每個工作接收一個 session，只呼叫各模組 service，不得 commit 或 rollback。
"""

from app.worker import Job

JOBS: list[Job] = []
