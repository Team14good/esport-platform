"""產生繁中測試報告（Story 7.3）：由 scripts/test-all.sh 在 backend 容器裡呼叫。

用法：python scripts/build_test_report.py <原始輸出資料夾> <報告路徑>

報告裡的數字只取自原始輸出資料夾裡當次執行的檔案，缺檔的區塊註明「沒有資料」：

- layers.json：各層的結束碼、是否略過、耗時（test-all.sh 寫入）
- vitest-junit.xml、backend-unit.xml、backend-integration.xml：JUnit 結果
- coverage.json：後端覆蓋率（`coverage json`）
- api-timings-integration.jsonl：整合測試每次 API 的耗時（tests/report_support.py）
- nfr1.jsonl：併發測試記下的數字（tests/report_support.py）
- playwright.json：Playwright json reporter 的輸出（含 api-timings.json 附件）
"""

import base64
import json
import math
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

BACKEND_DIR = Path(__file__).resolve().parents[1]
TRACEABILITY_FILE = BACKEND_DIR / "tests" / "traceability.yaml"
TEST_SH = BACKEND_DIR / "scripts" / "test.sh"

SLOW_MS = 1000.0
# 只記錄、不判定 1 秒限制的 API（與 frontend/tests/e2e/support/fixtures.ts 一致）
EXEMPT_ROUTES = {("POST", "/api/v1/access-tokens"): "登入（密碼雜湊）"}
UUID_PATTERN = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE
)
STATUS_LABEL = {"passed": "通過", "failed": "失敗", "skipped": "略過"}


@dataclass
class Case:
    layer: str
    file: str
    name: str
    status: str  # passed／failed／skipped
    seconds: float
    message: str = ""
    stories: list[str] = field(default_factory=list)
    frs: list[str] = field(default_factory=list)


@dataclass
class Layer:
    key: str
    title: str
    tool: str
    cases: list[Case]
    exit_code: int | None
    skipped: bool
    seconds: float | None
    has_data: bool


# ---------------------------------------------------------------- 讀檔


def _read_json(path: Path) -> Any:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def pure_functions() -> list[str]:
    """scripts/test.sh 的 PURE_FUNCTIONS 清單（單一來源）。"""
    text = TEST_SH.read_text(encoding="utf-8")
    block = re.search(r"PURE_FUNCTIONS=\((.*?)\)", text, re.DOTALL)
    return block.group(1).split() if block else []


def load_traceability() -> dict[str, dict[str, Any]]:
    return dict(yaml.safe_load(TRACEABILITY_FILE.read_text(encoding="utf-8")) or {})


def _junit_cases(path: Path, layer: str) -> list[Case] | None:
    if not path.is_file():
        return None
    root = ET.parse(path).getroot()
    cases: list[Case] = []
    for testcase in root.iter("testcase"):
        status, message = "passed", ""
        for child in testcase:
            if child.tag in ("failure", "error"):
                status = "failed"
                message = (child.get("message") or child.text or "").strip()
            elif child.tag == "skipped" and status != "failed":
                status = "skipped"
                message = (child.get("message") or "").strip()
        cases.append(
            Case(
                layer=layer,
                file=testcase.get("classname") or testcase.get("file") or "",
                name=testcase.get("name") or "",
                status=status,
                seconds=float(testcase.get("time") or 0),
                message=message.splitlines()[0][:200] if message else "",
            )
        )
    return cases


def _backend_file(classname: str, known: set[str]) -> str:
    """pytest 的 classname（tests.registration.test_x[.TestY]）轉成對應檔的路徑。"""
    parts = classname.split(".")
    if parts and parts[0] == "tests":
        parts = parts[1:]
    for end in range(len(parts), 0, -1):
        candidate = "/".join(parts[:end]) + ".py"
        if candidate in known:
            return candidate
    return "/".join(parts) + ".py"


def backend_cases(
    path: Path, layer: str, traceability: dict[str, dict[str, Any]]
) -> list[Case] | None:
    cases = _junit_cases(path, layer)
    if cases is None:
        return None
    known = set(traceability)
    for case in cases:
        case.file = _backend_file(case.file, known)
        entry = traceability.get(case.file, {})
        case.stories = list(entry.get("stories", []))
        case.frs = list(entry.get("frs", []))
    return cases


def _playwright_suites(suite: dict[str, Any], titles: list[str]) -> list[Any]:
    """攤平 Playwright json 的巢狀 suites，回傳 (標題路徑, spec)。"""
    found: list[Any] = []
    for spec in suite.get("specs", []):
        found.append((titles, spec))
    for child in suite.get("suites", []):
        found += _playwright_suites(child, [*titles, child.get("title", "")])
    return found


def e2e_cases(report: Any) -> tuple[list[Case], list[dict[str, Any]]]:
    """回傳 (案例, API 耗時)；案例以「檔案 › 標題 [專案]」為一筆。"""
    cases: list[Case] = []
    timings: list[dict[str, Any]] = []
    for suite in report.get("suites", []):
        file = suite.get("file") or suite.get("title", "")
        for titles, spec in _playwright_suites(suite, []):
            tags = [
                tag if tag.startswith("@") else f"@{tag}"
                for tag in spec.get("tags", [])
            ]
            stories = sorted(
                {t.removeprefix("@story-") for t in tags if t.startswith("@story-")},
                key=_story_key,
            )
            frs = sorted(
                {t[1:] for t in tags if re.match(r"^@N?FR-\d+$", t)}, key=_fr_key
            )
            for test in spec.get("tests", []):
                results = test.get("results", [])
                outcome = test.get("status")
                status = {
                    "expected": "passed",
                    "flaky": "passed",
                    "skipped": "skipped",
                }.get(outcome or "", "failed")
                message = ""
                for result in results:
                    error = result.get("error") or {}
                    if error.get("message"):
                        message = _strip_ansi(error["message"]).splitlines()[0][:200]
                    for attachment in result.get("attachments", []):
                        if attachment.get(
                            "name"
                        ) == "api-timings.json" and attachment.get("body"):
                            timings += json.loads(base64.b64decode(attachment["body"]))
                name = " › ".join([*[t for t in titles if t], spec.get("title", "")])
                cases.append(
                    Case(
                        layer="e2e",
                        file=file,
                        name=f"{name} [{test.get('projectName', '')}]",
                        status=status,
                        seconds=sum(r.get("duration", 0) for r in results) / 1000,
                        message=message,
                        stories=stories,
                        frs=frs,
                    )
                )
    return cases, timings


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def _story_key(story: str) -> tuple[int, ...]:
    return tuple(int(part) for part in story.split(".") if part.isdigit())


def _fr_key(fr: str) -> tuple[int, int]:
    return (1 if fr.startswith("NFR") else 0, int(fr.rsplit("-", 1)[1]))


# ---------------------------------------------------------------- 計算


def _percentile(values: list[float], pct: float) -> float:
    """最近排名法（nearest-rank）。"""
    ordered = sorted(values)
    rank = max(1, math.ceil(pct / 100 * len(ordered)))
    return ordered[rank - 1]


def _endpoint(method: str, url: str) -> str:
    path = re.sub(r"^https?://[^/]+", "", url).split("?")[0]
    path = UUID_PATTERN.sub("{id}", path)
    path = re.sub(r"/\d+(?=/|$)", "/{n}", path)
    return f"{method} {path}"


def timing_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """rows：{method, path 或 url, duration_ms 或 durationMs, status}。"""
    measured: list[tuple[str, float, str | None]] = []
    for row in rows:
        duration = row.get("duration_ms", row.get("durationMs"))
        if duration is None:
            continue
        method = str(row.get("method", ""))
        raw_path = str(row.get("path") or row.get("url") or "")
        endpoint = _endpoint(method, raw_path)
        bare = endpoint.split(" ", 1)[1]
        exempt = row.get("exempt") or EXEMPT_ROUTES.get((method, bare))
        measured.append((endpoint, float(duration), exempt))
    judged = [d for _, d, exempt in measured if not exempt]
    slow: dict[str, list[float]] = defaultdict(list)
    for endpoint, duration, exempt in measured:
        if not exempt and duration > SLOW_MS:
            slow[endpoint].append(duration)
    exempt_rows: dict[str, list[float]] = defaultdict(list)
    for endpoint, duration, exempt in measured:
        if exempt:
            exempt_rows[f"{endpoint}（{exempt}）"].append(duration)
    return {
        "count": len(measured),
        "judged": len(judged),
        "p50": _percentile(judged, 50) if judged else None,
        "p95": _percentile(judged, 95) if judged else None,
        "max": max(judged) if judged else None,
        "slow": dict(slow),
        "exempt": dict(exempt_rows),
    }


# ---------------------------------------------------------------- 輸出


def _ms(value: float | None) -> str:
    return "—" if value is None else f"{value:,.0f} ms"


def _pct(covered: int, total: int) -> str:
    return "—" if total == 0 else f"{covered / total * 100:.1f}%"


def _escape(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _counts(cases: list[Case]) -> Counter[str]:
    return Counter(case.status for case in cases)


def section_overview(layers: list[Layer]) -> list[str]:
    lines = [
        "## 1. 各層結果",
        "",
        "依執行順序：單元 → 整合 → 端對端。",
        "",
        "| 層級 | 工具 | 案例數 | 通過 | 失敗 | 略過 | 耗時 | 結果 |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for layer in layers:
        if layer.skipped:
            lines.append(
                f"| {layer.title} | {layer.tool} | — | — | — | — | — | 本次略過 |"
            )
            continue
        if not layer.has_data:
            lines.append(
                f"| {layer.title} | {layer.tool} | — | — | — | — | — | "
                f"沒有產生結果檔（結束碼 {layer.exit_code}） |"
            )
            continue
        counts = _counts(layer.cases)
        ok = layer.exit_code == 0 and counts["failed"] == 0
        verdict = "通過" if ok else f"失敗（結束碼 {layer.exit_code}）"
        seconds = "—" if layer.seconds is None else f"{layer.seconds:.0f} 秒"
        lines.append(
            f"| {layer.title} | {layer.tool} | {len(layer.cases)} | {counts['passed']} | "
            f"{counts['failed']} | {counts['skipped']} | {seconds} | {verdict} |"
        )
    failed = [c for layer in layers for c in layer.cases if c.status == "failed"]
    lines += ["", "### 失敗的案例", ""]
    if not failed:
        lines.append("沒有失敗的案例。")
    else:
        lines += ["| 層級 | 檔案 | 案例 | 訊息 |", "|---|---|---|---|"]
        lines += [
            f"| {c.layer} | `{c.file}` | {_escape(c.name)} | {_escape(c.message)} |"
            for c in failed
        ]
    return lines


def _module_of(path: str) -> str:
    parts = path.split("/")
    if len(parts) >= 3 and parts[1] == "modules":
        return f"modules/{parts[2]}"
    return parts[1] if len(parts) >= 2 else path


def section_coverage(coverage: Any, gate: dict[str, Any] | None) -> list[str]:
    lines = ["## 2. 後端覆蓋率", ""]
    if gate is not None:
        verdict = (
            "通過" if gate.get("exit") == 0 else f"未通過（結束碼 {gate.get('exit')}）"
        )
        lines += [f"門檻檢查（整體 85%、四個純函式逐檔 90%）：{verdict}", ""]
    if coverage is None:
        return [*lines, "沒有資料（後端測試沒有產生 coverage.json）。"]
    totals = coverage["totals"]
    lines += [
        "單元與整合兩次執行合併計算（`coverage run --append`），開啟分支量測。"
        "完整的逐行報告見 `reports/coverage/index.html`。",
        "",
        "| 項目 | 已涵蓋 | 總數 | 覆蓋率 |",
        "|---|---:|---:|---:|",
        f"| 敘述（statements） | {totals['covered_lines']} | {totals['num_statements']} | "
        f"{_pct(totals['covered_lines'], totals['num_statements'])} |",
        f"| 分支（branches） | {totals['covered_branches']} | {totals['num_branches']} | "
        f"{_pct(totals['covered_branches'], totals['num_branches'])} |",
        f"| 合計（coverage 的總覆蓋率，門檻 85%） | — | — | "
        f"{totals['percent_covered']:.1f}% |",
        "",
        "### 依模組",
        "",
        "| 模組 | 敘述 | 分支 | 合計 |",
        "|---|---:|---:|---:|",
    ]
    modules: dict[str, Counter[str]] = defaultdict(Counter)
    for path, data in coverage["files"].items():
        summary = data["summary"]
        bucket = modules[_module_of(path)]
        for key in (
            "covered_lines",
            "num_statements",
            "covered_branches",
            "num_branches",
        ):
            bucket[key] += summary[key]
    for name, c in sorted(modules.items()):
        if c["num_statements"] == 0:
            continue
        combined_total = c["num_statements"] + c["num_branches"]
        combined = c["covered_lines"] + c["covered_branches"]
        lines.append(
            f"| `{name}` | {_pct(c['covered_lines'], c['num_statements'])} | "
            f"{_pct(c['covered_branches'], c['num_branches'])} | "
            f"{_pct(combined, combined_total)} |"
        )
    return lines


def section_pure_functions(coverage: Any) -> list[str]:
    lines = [
        "## 3. 純函式的分支覆蓋率",
        "",
        "門檻 90%，由 `backend/scripts/test.sh` 逐檔強制（CI 也會檢查）。"
        "門檻判斷只看「分支」欄；「合計」是 coverage 以敘述加分支計算的覆蓋率，僅供參考。",
        "",
    ]
    if coverage is None:
        return [*lines, "沒有資料。"]
    lines += [
        "| 檔案 | 敘述 | 分支 | 合計 | 達 90% |",
        "|---|---:|---:|---:|---|",
    ]
    for path in pure_functions():
        data = coverage["files"].get(path)
        if data is None:
            lines.append(f"| `{path}` | — | — | — | 沒有資料 |")
            continue
        s = data["summary"]
        ok = s["num_branches"] == 0 or s["covered_branches"] / s["num_branches"] >= 0.9
        lines.append(
            f"| `{path}` | {_pct(s['covered_lines'], s['num_statements'])} | "
            f"{_pct(s['covered_branches'], s['num_branches'])}"
            f"（{s['covered_branches']}/{s['num_branches']}） | "
            f"{s['percent_covered']:.1f}% | {'是' if ok else '否'} |"
        )
    return lines


def section_nfr1(records: list[dict[str, Any]], cases: list[Case]) -> list[str]:
    lines = [
        "## 4. NFR-1 併發一致性",
        "",
        "整合測試以多條連線、多個執行緒同時操作真實的 PostgreSQL 18。",
        "",
    ]
    if not records:
        lines.append("沒有資料（併發測試沒有執行或沒有記錄）。")
    else:
        lines += [
            "| 情境 | 送出數 | 成功 | 業務錯誤 | 非預期錯誤 | 實際筆數 | 名額／預期 | 正取 | 候補 | 學校數 |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for r in records:
            rows = r.get("registrations", r.get("rows", "—"))
            expected = r.get("capacity", r.get("expected_rows", "—"))
            lines.append(
                f"| {r['scenario']} | {r.get('submitted', '—')} | {r.get('succeeded', '—')} | "
                f"{r.get('business_errors', '—')} | {r.get('unexpected_errors', '—')} | "
                f"{rows} | {expected} | {r.get('accepted', '—')} | "
                f"{r.get('waitlisted', '—')} | {r.get('schools', '—')} |"
            )
        for r in records:
            if "capacity" in r and "accepted" in r:
                verdict = "沒有超收" if r["accepted"] <= r["capacity"] else "超收"
                lines.append("")
                lines.append(
                    f"- {r['scenario']}：正取 {r['accepted']} 隊，名額 {r['capacity']} 隊，"
                    f"{verdict}；送出 {r['submitted']} 筆、資料庫 {r['registrations']} 筆報名。"
                )
    nfr1_cases = [c for c in cases if "NFR-1" in c.frs]
    lines += [
        "",
        "### 標註 NFR-1 的測試檔",
        "",
        "對應檔以測試檔為單位標註，所以檔內每個案例都算進來。",
        "",
    ]
    if not nfr1_cases:
        lines.append("沒有資料。")
    else:
        by_file: dict[str, Counter[str]] = defaultdict(Counter)
        for case in nfr1_cases:
            by_file[case.file][case.status] += 1
        lines += ["| 檔案 | 案例數 | 通過 | 失敗 | 略過 |", "|---|---:|---:|---:|---:|"]
        for path, counts in sorted(by_file.items()):
            lines.append(
                f"| `{path}` | {sum(counts.values())} | {counts['passed']} | "
                f"{counts['failed']} | {counts['skipped']} |"
            )
    return lines


def _timing_block(title: str, summary: dict[str, Any] | None, note: str) -> list[str]:
    lines = [f"### {title}", ""]
    if summary is None:
        return [*lines, note]
    if summary["count"] == 0:
        return [*lines, "沒有記錄到 API 請求。"]
    lines += [
        "| 筆數（判定／全部） | P50 | P95 | 最大值 |",
        "|---:|---:|---:|---:|",
        f"| {summary['judged']}／{summary['count']} | {_ms(summary['p50'])} | "
        f"{_ms(summary['p95'])} | {_ms(summary['max'])} |",
        "",
    ]
    if summary["slow"]:
        lines += [
            "超過 1 秒的端點：",
            "",
            "| 端點 | 次數 | 最大值 |",
            "|---|---:|---:|",
        ]
        for endpoint, values in sorted(
            summary["slow"].items(), key=lambda x: -max(x[1])
        ):
            lines.append(f"| `{endpoint}` | {len(values)} | {_ms(max(values))} |")
    else:
        lines.append("沒有超過 1 秒的端點。")
    if summary["exempt"]:
        lines += ["", "不判定 1 秒限制（只記錄）：", ""]
        for endpoint, values in sorted(summary["exempt"].items()):
            lines.append(
                f"- `{endpoint}`：{len(values)} 筆，P50 {_ms(_percentile(values, 50))}，"
                f"最大值 {_ms(max(values))}"
            )
    return lines


def section_nfr2(
    integration: dict[str, Any] | None, e2e: dict[str, Any] | None, e2e_note: str
) -> list[str]:
    return [
        "## 5. NFR-2 API 回應時間",
        "",
        "一般 API 應在 1 秒內回應。整合測試量的是 TestClient 送出到收到回應（不含網路）；"
        "端對端量的是瀏覽器在 docker compose 示範環境中的請求。端點中的 id 以 `{id}` 合併。",
        "",
        *_timing_block("整合測試", integration, "沒有資料（整合測試沒有記錄耗時）。"),
        "",
        *_timing_block("端對端測試", e2e, e2e_note),
    ]


def section_traceability(cases: list[Case], vitest_count: int | None) -> list[str]:
    traced = [c for c in cases if c.layer != "前端單元"]
    lines = [
        "## 6. 追溯：測試案例對應的 Story 與 FR",
        "",
        "後端案例的 Story／FR 取自 `backend/tests/traceability.yaml`（以測試檔為單位），"
        "端對端取自 Playwright 的 tag（`@story-x.y`、`@FR-n`）。",
    ]
    if vitest_count is not None:
        lines.append(
            f"前端 Vitest 單元測試（{vitest_count} 個案例）以元件為單位，沒有逐案例標註，"
            "不列入本區塊。"
        )
    unmapped = [c for c in traced if not c.stories or not c.frs]
    lines += [
        "",
        f"共 {len(traced)} 個案例，{len(traced) - len(unmapped)} 個有 Story 與 FR。",
        "",
    ]
    if unmapped:
        lines += ["沒有標註的案例：", ""]
        lines += [f"- {c.layer}：`{c.file}` {_escape(c.name)}" for c in unmapped[:50]]
        lines.append("")
    by_story: dict[str, Counter[str]] = defaultdict(Counter)
    story_frs: dict[str, set[str]] = defaultdict(set)
    for case in traced:
        for story in case.stories:
            by_story[story][case.layer] += 1
            by_story[story][case.status] += 1
            story_frs[story].update(case.frs)
    lines += [
        "### 依 Story 彙整",
        "",
        "一個測試檔可以標多個 Story，所以各列加總會大於案例總數。",
        "",
        "| Story | 單元 | 整合 | 端對端 | 合計 | 通過 | 失敗 | 略過 | FR |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for story in sorted(by_story, key=_story_key):
        c = by_story[story]
        total = c["後端單元"] + c["後端整合"] + c["e2e"]
        frs = "、".join(sorted(story_frs[story], key=_fr_key))
        lines.append(
            f"| {story} | {c['後端單元']} | {c['後端整合']} | {c['e2e']} | {total} | "
            f"{c['passed']} | {c['failed']} | {c['skipped']} | {frs} |"
        )
    by_fr: dict[str, Counter[str]] = defaultdict(Counter)
    for case in traced:
        for fr in case.frs:
            by_fr[fr][case.status] += 1
    lines += [
        "",
        "### 依需求彙整",
        "",
        "| 需求 | 案例數 | 通過 | 失敗 | 略過 |",
        "|---|---:|---:|---:|---:|",
    ]
    for fr in sorted(by_fr, key=_fr_key):
        c = by_fr[fr]
        lines.append(
            f"| {fr} | {sum(c.values())} | {c['passed']} | {c['failed']} | {c['skipped']} |"
        )
    lines += [
        "",
        "### 全部案例",
        "",
        "<details>",
        f"<summary>展開 {len(traced)} 個案例</summary>",
        "",
        "| 層級 | 檔案 | 案例 | 結果 | Story | FR |",
        "|---|---|---|---|---|---|",
    ]
    for case in traced:
        lines.append(
            f"| {case.layer} | `{case.file}` | {_escape(case.name)} | "
            f"{STATUS_LABEL[case.status]} | {'、'.join(case.stories) or '—'} | "
            f"{'、'.join(case.frs) or '—'} |"
        )
    lines += ["", "</details>"]
    return lines


def build(raw: Path) -> str:
    meta = _read_json(raw / "layers.json") or {}
    traceability = load_traceability()

    def _layer(key: str, title: str, tool: str, cases: list[Case] | None) -> Layer:
        info = meta.get(key, {})
        return Layer(
            key=key,
            title=title,
            tool=tool,
            cases=cases or [],
            exit_code=info.get("exit"),
            skipped=bool(info.get("skipped")),
            seconds=info.get("seconds"),
            has_data=cases is not None,
        )

    vitest = _junit_cases(raw / "vitest-junit.xml", "前端單元")
    unit = backend_cases(raw / "backend-unit.xml", "後端單元", traceability)
    integration = backend_cases(
        raw / "backend-integration.xml", "後端整合", traceability
    )
    playwright = _read_json(raw / "playwright.json")
    e2e, e2e_timings = e2e_cases(playwright) if playwright else (None, [])

    layers = [
        _layer("frontend_unit", "單元（前端）", "Vitest＋jsdom", vitest),
        _layer("backend_unit", "單元（後端）", "pytest -m unit", unit),
        _layer(
            "backend_integration",
            "整合（後端）",
            "pytest -m integration（PostgreSQL 18）",
            integration,
        ),
        _layer("e2e", "端對端", "Playwright（desktop、mobile-375）", e2e),
    ]
    all_cases = [case for layer in layers for case in layer.cases]
    backend = [c for c in all_cases if c.layer in ("後端單元", "後端整合")]
    coverage = _read_json(raw / "coverage.json")

    integration_rows = _read_jsonl(raw / "api-timings-integration.jsonl")
    e2e_layer = layers[3]
    if e2e_layer.skipped:
        e2e_summary, e2e_note = None, "本次略過端對端測試。"
    elif playwright is None:
        e2e_summary, e2e_note = None, "沒有資料（端對端測試沒有產生 playwright.json）。"
    else:
        e2e_summary, e2e_note = timing_summary(e2e_timings), ""

    now = datetime.now(UTC).astimezone(ZoneInfo("Asia/Taipei"))
    commit = meta.get("commit") or "未知"
    lines = [
        "# FLOW 測試報告",
        "",
        f"- 產生時間：{now:%Y-%m-%d %H:%M}（台北時間）",
        f"- 版本：`{commit}`",
        "- 指令：`bash scripts/test-all.sh"
        + (" --skip-e2e" if e2e_layer.skipped else "")
        + "`",
        "- 環境：docker compose（PostgreSQL 18）；後端測試在 backend 容器、前端單元測試在 "
        "frontend 容器、端對端在 e2e 容器執行",
        "",
        *section_overview(layers),
        "",
        *section_coverage(coverage, meta.get("coverage")),
        "",
        *section_pure_functions(coverage),
        "",
        *section_nfr1(_read_jsonl(raw / "nfr1.jsonl"), backend),
        "",
        *section_nfr2(
            timing_summary(integration_rows) if integration_rows else None,
            e2e_summary,
            e2e_note,
        ),
        "",
        *section_traceability(all_cases, len(vitest) if vitest is not None else None),
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    if len(sys.argv) != 3:
        sys.stderr.write(
            "用法：python scripts/build_test_report.py <原始輸出資料夾> <報告路徑>\n"
        )
        sys.exit(2)
    raw, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(raw), encoding="utf-8", newline="\n")
    sys.stdout.write(f"測試報告：{out}\n")


if __name__ == "__main__":
    main()
