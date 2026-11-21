import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(ROOT))


@pytest.fixture
def sprint_text() -> str:
    return (FIXTURES / "sprint-status.yaml").read_text("utf-8")


@pytest.fixture
def contributing_text() -> str:
    return (FIXTURES / "CONTRIBUTING.md").read_text("utf-8")


@pytest.fixture
def entries(sprint_text):
    from plan_rules import parse_sprint_status

    return parse_sprint_status(sprint_text)


@pytest.fixture
def deps(contributing_text):
    from plan_rules import parse_dependencies

    return parse_dependencies(contributing_text)


@pytest.fixture
def order_a(contributing_text):
    from plan_rules import parse_batch_order

    return parse_batch_order(contributing_text, "A")
