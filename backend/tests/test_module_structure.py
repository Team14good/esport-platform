"""模組化單體的結構（AD-1、AD-3）。"""

import importlib
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi import APIRouter

APP_DIR = Path(__file__).resolve().parents[1] / "app"
MODULES = [
    "identity",
    "tournaments",
    "registration",
    "competition",
    "disputes",
    "notifications",
]
LAYER_FILES = ["router.py", "service.py", "repository.py", "models.py"]


def test_module_list_is_fixed() -> None:
    found = sorted(
        path.name
        for path in (APP_DIR / "modules").iterdir()
        if path.is_dir() and path.name != "__pycache__"
    )

    assert found == sorted(MODULES)


@pytest.mark.parametrize("module", MODULES)
def test_each_module_has_the_four_layer_files(module: str) -> None:
    module_dir = APP_DIR / "modules" / module

    for name in ["__init__.py", *LAYER_FILES]:
        assert (module_dir / name).is_file(), f"{module}/{name} is missing"


@pytest.mark.parametrize("module", MODULES)
def test_each_module_router_is_an_api_router(module: str) -> None:
    router_module = importlib.import_module(f"app.modules.{module}.router")

    assert isinstance(router_module.router, APIRouter)


def test_importing_modules_registers_every_table() -> None:
    # 在全新的程序裡檢查：只匯入 app.modules 就能讓跨模組外鍵解析（worker 的情境）
    script = (
        "import uuid, app.modules\n"
        "from sqlmodel import SQLModel\n"
        "from app.core.audit import AuditLog\n"
        "assert 'account' in SQLModel.metadata.tables\n"
        "[fk] = AuditLog.__table__.c.actor_id.foreign_keys\n"
        "assert fk.column.table.name == 'account'\n"
    )

    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=False
    )

    assert result.returncode == 0, result.stderr


def test_core_does_not_import_modules() -> None:
    for path in (APP_DIR / "core").glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "app.modules" not in source, f"core/{path.name} imports a module"
