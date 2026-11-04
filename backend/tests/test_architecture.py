"""架構規則的靜態檢查（AD-2、AD-3、AD-5、AD-13）。

用 `ast` 解析 `app/` 的原始碼，不匯入、不連資料庫。規則只寫在文件裡時，
AI 或人為了方便直接越界不會有任何提醒；寫成測試後，違規就是紅燈。

每條規則都是一個「(相對路徑, 原始碼) → 違規清單」的函式：掃全專案的測試
要求清單為空，負面測試餵入故意違規的程式片段，確認檢查本身抓得到。
"""

import ast
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parents[1] / "app"

# AD-3：核心流程的呼叫方向。排在前面的模組可以呼叫排在後面的任一模組（可以跳級），
# 反方向禁止（2026-11-04 決定）。
CALL_ORDER = ["disputes", "competition", "registration", "tournaments", "identity"]
# notifications 不在鏈上：處理事件時可以呼叫任何模組的 service，但沒有模組可以呼叫它。
NOTIFICATIONS = "notifications"
MODULES = [*CALL_ORDER, NOTIFICATIONS]

# AD-2：跨模組只能 import 對方的這些子模組。
#   service — 公開函式（AD-2 本體）
#   models  — 只限型別（StrEnum、*Read schema、事件 payload），不能是 table=True 的
#             資料表類別（2026-11-04 決定）
#   identity.deps — router 用來宣告帳號層級權限（AD-10），只限 router.py
PUBLIC_SUBMODULE = "service"
TYPES_SUBMODULE = "models"
AUTH_DEPS = ("identity", "deps")

# AD-5：只有進入點能提交交易。模組裡只有 router.py 可以；worker、initial_data 不屬於
# 任何模組，本來就不掃。
TRANSACTION_METHODS = {"commit", "rollback"}

# AD-13：只有 core/clock.py 能取得目前時間。
CLOCK_FILE = "core/clock.py"
FORBIDDEN_TIME_ATTRS = {
    "datetime": {"now", "utcnow", "today"},
    "date": {"today"},
    "time": {"time"},
}


@dataclass(frozen=True)
class Violation:
    path: str
    line: int
    rule: str
    detail: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line} {self.rule} {self.detail}"


@dataclass(frozen=True)
class ImportRef:
    """一個 import 指到 `app.modules` 底下的什麼。"""

    line: int
    module: str | None  # 目標模組；`from app import modules` 這種整包匯入時為 None
    submodule: str | None  # service、models、deps……；只匯入套件本身時為 None
    names: tuple[str, ...]  # `from app.modules.x.models import A, B` 的 A、B


def _owner(rel: str) -> str | None:
    """檔案所屬的模組；不在 modules/<模組>/ 底下時為 None。"""
    parts = rel.split("/")
    if len(parts) >= 3 and parts[0] == "modules" and parts[1] in MODULES:
        return parts[1]
    return None


def _module_refs(tree: ast.AST) -> Iterator[ImportRef]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield from _ref_from_dotted(node.lineno, alias.name, ())
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names = tuple(alias.name for alias in node.names)
            parts = node.module.split(".")
            if parts == ["app"] and "modules" in names:
                yield ImportRef(node.lineno, None, None, ())
            elif parts == ["app", "modules"]:
                # from app.modules import registration → 匯入整個模組套件
                for name in names:
                    yield ImportRef(node.lineno, name, None, ())
            elif len(parts) == 3 and parts[:2] == ["app", "modules"]:
                # from app.modules.x import service, models → 各自是子模組
                for name in names:
                    yield ImportRef(node.lineno, parts[2], name, ())
            else:
                yield from _ref_from_dotted(node.lineno, node.module, names)


def _ref_from_dotted(
    line: int, dotted: str, names: tuple[str, ...]
) -> Iterator[ImportRef]:
    parts = dotted.split(".")
    if parts[:2] != ["app", "modules"]:
        return
    if len(parts) == 2:
        yield ImportRef(line, None, None, ())
        return
    submodule = parts[3] if len(parts) > 3 else None
    yield ImportRef(line, parts[2], submodule, names)


@cache
def table_classes(module: str) -> frozenset[str]:
    """`modules/<module>/models.py` 裡 `table=True` 的類別名稱。"""
    tree = ast.parse((APP_DIR / "modules" / module / "models.py").read_text("utf-8"))
    return frozenset(
        node.name
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and any(
            kw.arg == "table"
            and isinstance(kw.value, ast.Constant)
            and kw.value.value is True
            for kw in node.keywords
        )
    )


def check_module_boundaries(rel: str, source: str) -> list[Violation]:
    """AD-2（只經 service）與 AD-3（呼叫方向、notifications、core）。"""
    tree = ast.parse(source)
    owner = _owner(rel)
    is_core = rel.startswith("core/")
    if owner is None and not is_core:
        return []  # 進入點（api、worker、main、initial_data、demo_data）可以組裝任何模組

    found: list[Violation] = []
    for ref in _module_refs(tree):
        if is_core:
            found.append(Violation(rel, ref.line, "AD-3", "core 不得 import 任何模組"))
            continue
        assert owner is not None  # 不是 core，就一定在某個模組裡（上面已排除進入點）
        target = ref.module
        if target == owner:
            continue
        if target is None or target not in MODULES:
            found.append(
                Violation(rel, ref.line, "AD-2", "要 import 具體模組的 service")
            )
            continue

        if target == NOTIFICATIONS:
            found.append(
                Violation(
                    rel, ref.line, "AD-3", "不得呼叫 notifications，請改發 outbox 事件"
                )
            )
            continue
        if owner != NOTIFICATIONS and CALL_ORDER.index(owner) > CALL_ORDER.index(
            target
        ):
            found.append(
                Violation(rel, ref.line, "AD-3", f"{owner} 不得呼叫上游的 {target}")
            )
            continue

        found.extend(_check_submodule(rel, ref, target))
    return found


def _check_submodule(rel: str, ref: ImportRef, target: str) -> list[Violation]:
    if ref.submodule == PUBLIC_SUBMODULE:
        return []
    if (target, ref.submodule) == AUTH_DEPS and rel.endswith("/router.py"):
        return []
    if ref.submodule == TYPES_SUBMODULE and ref.names:
        tables = sorted(set(ref.names) & table_classes(target))
        if not tables:
            return []
        return [
            Violation(
                rel,
                ref.line,
                "AD-2",
                f"不得 import {target} 的資料表類別 {', '.join(tables)}，"
                f"請呼叫 {target}.service",
            )
        ]
    shown = ".".join(p for p in (target, ref.submodule) if p)
    return [
        Violation(
            rel, ref.line, "AD-2", f"跨模組只能經 {target}.service，不得 import {shown}"
        )
    ]


def check_transactions(rel: str, source: str) -> list[Violation]:
    """AD-5：模組裡只有 router.py 可以 commit／rollback。"""
    if _owner(rel) is None and not rel.startswith("core/"):
        return []
    if rel.endswith("/router.py"):
        return []
    return [
        Violation(
            rel, node.lineno, "AD-5", f"只有 router 能 {node.func.attr}()，請交給進入點"
        )
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in TRANSACTION_METHODS
    ]


def check_clock(rel: str, source: str) -> list[Violation]:
    """AD-13：目前時間只能經 `core.clock.now()` 取得。"""
    if rel == CLOCK_FILE:
        return []
    tree = ast.parse(source)
    # 名稱 → 它代表 datetime／date／time 中的哪一個（處理 `import datetime as dt`、
    # `from datetime import datetime as DT` 這類別名）
    kinds: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in ("datetime", "time"):
                    kinds[alias.asname or alias.name] = f"{alias.name}-module"
        elif isinstance(node, ast.ImportFrom) and node.module == "datetime":
            for alias in node.names:
                if alias.name in ("datetime", "date"):
                    kinds[alias.asname or alias.name] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module == "time":
            for alias in node.names:
                if alias.name == "time":
                    kinds[alias.asname or alias.name] = "time-function"

    found: list[Violation] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            kind = _attribute_kind(node.value, kinds)
            if kind and node.attr in FORBIDDEN_TIME_ATTRS.get(kind, set()):
                found.append(
                    Violation(
                        rel,
                        node.lineno,
                        "AD-13",
                        f"不得用 {kind}.{node.attr}，請改用 clock.now()",
                    )
                )
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and kinds.get(node.func.id) == "time-function"
        ):
            found.append(
                Violation(
                    rel, node.lineno, "AD-13", "不得用 time.time，請改用 clock.now()"
                )
            )
    return found


def _attribute_kind(value: ast.expr, kinds: dict[str, str]) -> str | None:
    """`X.now` 的 X 是 datetime、date 還是 time。"""
    if isinstance(value, ast.Name):
        kind = kinds.get(value.id)
        if kind == "datetime-module":
            return None  # `datetime.now` 在這裡是模組的屬性，下面的 Attribute 會處理
        if kind == "time-module":
            return "time"
        return kind if kind in ("datetime", "date") else None
    if (
        isinstance(value, ast.Attribute)
        and isinstance(value.value, ast.Name)
        and kinds.get(value.value.id) == "datetime-module"
        and value.attr in ("datetime", "date")
    ):
        return value.attr  # datetime.datetime.now
    return None


def _sources() -> list[tuple[str, str]]:
    return [
        (path.relative_to(APP_DIR).as_posix(), path.read_text(encoding="utf-8"))
        for path in sorted(APP_DIR.rglob("*.py"))
        if "alembic" not in path.relative_to(APP_DIR).parts
    ]


def _report(violations: list[Violation]) -> str:
    return "\n".join(str(v) for v in violations)


# ---------- 掃整個 app/ ----------


@pytest.mark.parametrize(
    "check", [check_module_boundaries, check_transactions, check_clock]
)
def test_app_follows_architecture_rules(
    check: Callable[[str, str], list[Violation]],
) -> None:
    violations = [v for rel, src in _sources() for v in check(rel, src)]

    assert not violations, "\n" + _report(violations)


def test_scan_covers_every_module() -> None:
    scanned = {_owner(rel) for rel, _ in _sources()}

    assert set(MODULES) <= scanned


def test_table_class_lookup_finds_known_tables() -> None:
    assert {"Tournament", "GameTitle", "RankTier"} <= table_classes("tournaments")
    assert "TournamentStatus" not in table_classes("tournaments")


# ---------- 負面測試：檢查本身要抓得到違規 ----------


def _rules(violations: list[Violation]) -> list[str]:
    return [v.rule for v in violations]


@pytest.mark.parametrize(
    ("rel", "source"),
    [
        (
            "modules/registration/service.py",
            "from app.modules.tournaments import repository",
        ),
        (
            "modules/registration/service.py",
            "import app.modules.tournaments.repository",
        ),
        (
            "modules/registration/service.py",
            "from app.modules.tournaments.repository import x",
        ),
        ("modules/registration/service.py", "from app.modules import tournaments"),
        (
            "modules/registration/service.py",
            "from app.modules.tournaments import models",
        ),
        (
            "modules/competition/service.py",
            "from app.modules.tournaments.models import Tournament",
        ),
        (
            "modules/competition/service.py",
            "from app.modules.identity.deps import CurrentAccount",
        ),
    ],
)
def test_cross_module_internals_are_rejected(rel: str, source: str) -> None:
    violations = check_module_boundaries(rel, source)

    assert _rules(violations) == ["AD-2"], _report(violations)
    assert violations[0].path == rel and violations[0].line == 1


@pytest.mark.parametrize(
    ("rel", "source"),
    [
        (
            "modules/registration/service.py",
            "from app.modules.tournaments import service as t",
        ),
        (
            "modules/registration/service.py",
            "from app.modules.tournaments.service import lock",
        ),
        ("modules/competition/service.py", "from app.modules.identity import service"),
        (
            "modules/competition/models.py",
            "from app.modules.tournaments.models import ScoreType",
        ),
        (
            "modules/registration/service.py",
            "from app.modules.tournaments.models import TournamentRead, TournamentStatus",
        ),
        (
            "modules/tournaments/router.py",
            "from app.modules.identity.deps import Organizer",
        ),
        (
            "modules/notifications/service.py",
            "from app.modules.registration import service",
        ),
        (
            "modules/registration/service.py",
            "from app.modules.registration import repository",
        ),
        ("worker/jobs.py", "from app.modules.notifications import service"),
        ("api/main.py", "from app.modules.disputes.router import router"),
    ],
)
def test_allowed_imports_pass(rel: str, source: str) -> None:
    assert check_module_boundaries(rel, source) == []


@pytest.mark.parametrize(
    ("rel", "source"),
    [
        (
            "modules/tournaments/service.py",
            "from app.modules.registration import service",
        ),
        ("modules/identity/service.py", "import app.modules.disputes.service"),
        (
            "modules/registration/service.py",
            "from app.modules.notifications import service",
        ),
        (
            "modules/competition/forfeit_job.py",
            "from app.modules.notifications.email import x",
        ),
        ("core/audit.py", "import app.modules.identity.models"),
        ("core/audit.py", "from app import modules"),
        ("core/audit.py", "from app.modules.identity.models import Account"),
    ],
)
def test_wrong_direction_is_rejected(rel: str, source: str) -> None:
    violations = check_module_boundaries(rel, source)

    assert _rules(violations) == ["AD-3"], _report(violations)


@pytest.mark.parametrize(
    "rel",
    [
        "modules/competition/service.py",
        "modules/competition/repository.py",
        "modules/competition/forfeit_job.py",
        "core/audit.py",
    ],
)
@pytest.mark.parametrize("method", ["commit", "rollback"])
def test_commit_outside_router_is_rejected(rel: str, method: str) -> None:
    violations = check_transactions(rel, f"def f(session):\n    session.{method}()\n")

    assert _rules(violations) == ["AD-5"], _report(violations)
    assert violations[0].line == 2


@pytest.mark.parametrize(
    "rel", ["modules/competition/router.py", "worker/__init__.py", "initial_data.py"]
)
def test_commit_in_entry_points_is_allowed(rel: str) -> None:
    assert check_transactions(rel, "session.commit()\nsession.rollback()\n") == []


@pytest.mark.parametrize(
    "source",
    [
        "from datetime import UTC, datetime\nx = datetime.now(UTC)",
        "from datetime import datetime\nx = datetime.utcnow()",
        "from datetime import datetime as DT\nx = DT.now()",
        "from datetime import date\nx = date.today()",
        "import datetime\nx = datetime.datetime.now()",
        "import datetime as dt\nx = dt.date.today()",
        "import time\nx = time.time()",
        "from time import time\nx = time()",
        "from datetime import datetime\nf = Field(default_factory=datetime.now)",
    ],
)
def test_reading_wall_clock_is_rejected(source: str) -> None:
    violations = check_clock("modules/competition/service.py", source)

    assert _rules(violations) == ["AD-13"], _report(violations)
    assert violations[0].line == 2


@pytest.mark.parametrize(
    ("rel", "source"),
    [
        (
            "modules/competition/service.py",
            "from app.core import clock\nx = clock.now()",
        ),
        ("modules/competition/forfeit.py", "def judge(now):\n    return now"),
        ("modules/competition/models.py", "from datetime import datetime\nx: datetime"),
        ("core/clock.py", "from datetime import UTC, datetime\nx = datetime.now(UTC)"),
    ],
)
def test_clock_usage_is_allowed(rel: str, source: str) -> None:
    assert check_clock(rel, source) == []
