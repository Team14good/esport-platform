"""測試報告（Story 7.3）的支援：讀分層與追溯對應檔、記錄 API 耗時與 NFR-1 併發數字。

只有設了環境變數時才寫檔（`scripts/test-all.sh` 會設），平常跑 `scripts/test.sh` 不產生任何檔案：

- `TEST_TIMINGS_FILE`：`client` fixture 每次 API 請求的耗時，一行一筆 JSON。
- `TEST_NFR1_FILE`：併發測試記下的送出數、名額、實際筆數，一行一筆 JSON。
"""

import json
import os
import re
import time
from pathlib import Path
from typing import Any

import httpx
import yaml

TESTS_DIR = Path(__file__).resolve().parent
TRACEABILITY_FILE = TESTS_DIR / "traceability.yaml"

LAYERS = ("unit", "integration")
STORY_PATTERN = re.compile(r"^\d+\.\d+$")
REQUIREMENT_PATTERN = re.compile(r"^N?FR-\d+$")


def load_traceability() -> dict[str, dict[str, Any]]:
    """回傳 {相對於 tests/ 的路徑: {layer, stories, frs}}。"""
    data = yaml.safe_load(TRACEABILITY_FILE.read_text(encoding="utf-8"))
    return dict(data or {})


def _append_jsonl(env_name: str, rows: list[dict[str, Any]]) -> None:
    target = os.environ.get(env_name)
    if not target or not rows:
        return
    path = Path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def record_nfr1(scenario: str, **numbers: Any) -> None:
    """記下一個併發情境的數字（給測試報告的 NFR-1 區塊）；沒設 `TEST_NFR1_FILE` 時不做事。"""
    _append_jsonl("TEST_NFR1_FILE", [{"scenario": scenario, **numbers}])


class ApiTimingRecorder:
    """掛在 TestClient 的 httpx event hook 上，記錄每個請求從送出到收到回應的毫秒數。"""

    def __init__(self) -> None:
        self.enabled = bool(os.environ.get("TEST_TIMINGS_FILE"))
        self.rows: list[dict[str, Any]] = []
        self.current_test = ""

    def attach(self, client: httpx.Client, test_id: str) -> None:
        if not self.enabled:
            return
        self.current_test = test_id
        client.event_hooks["request"].append(self._on_request)
        client.event_hooks["response"].append(self._on_response)

    def _on_request(self, request: httpx.Request) -> None:
        request.extensions["flow_started"] = time.perf_counter()

    def _on_response(self, response: httpx.Response) -> None:
        started = response.request.extensions.get("flow_started")
        if started is None:
            return
        self.rows.append(
            {
                "test": self.current_test,
                "method": response.request.method,
                "path": response.request.url.path,
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            }
        )

    def flush(self) -> None:
        _append_jsonl("TEST_TIMINGS_FILE", self.rows)
        self.rows = []


api_timings = ApiTimingRecorder()
