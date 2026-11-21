from dataclasses import replace

import pytest

from plan_rules import parse_sprint_status
from status_issue import render

RUN = "https://github.com/x/y/actions/runs/1"


@pytest.fixture
def ENTRIES(sprint_text):
    return parse_sprint_status(sprint_text)


def pr(n, labels=(), title="t", head="story/1-6-x"):
    return {"number": n, "labels": [{"name": l} for l in labels], "title": title, "headRefName": head, "isDraft": False}


def test_render_keeps_ai_log_block(ENTRIES):
    prev = "x\n<!-- ai-log:start -->\n- 審查 #95：3 則\n<!-- ai-log:end -->\n"
    assert "- 審查 #95：3 則" in render(ENTRIES, "A", [], RUN, prev)


def test_render_has_empty_ai_log_block_first_time(ENTRIES):
    out = render(ENTRIES, "A", [], RUN, "")
    assert "<!-- ai-log:start -->" in out and "<!-- ai-log:end -->" in out


def test_render_lists_waiting_prs(ENTRIES):
    out = render(ENTRIES, "A", [pr(10, labels=["flow-bot:等待核准"], title="feat: Story 1.6 通知中心")], RUN, "")
    assert "#10" in out.split("## 等你回覆")[1].split("##")[0]


def test_render_story_table_links_pr(ENTRIES):
    out = render(ENTRIES, "A", [pr(10, title="feat: Story 1.6 通知中心")], RUN, "")
    row = next(l for l in out.splitlines() if l.startswith("| 1.6"))
    assert "#10" in row and "backlog" in row


def test_render_all_done_banner(ENTRIES):
    done = [replace(e, status="done") if e.owner == "A" else e for e in ENTRIES]
    assert render(done, "A", [], RUN, "").startswith("**A 的期末 Story 全部完成**")


def test_recent_runs_capped_at_10(ENTRIES):
    prev = render(ENTRIES, "A", [], "run-0", "")
    for i in range(1, 12):
        prev = render(ENTRIES, "A", [], f"run-{i}", prev)
    runs = prev.split("## 最近執行")[1].split("##")[0]
    assert runs.count("run-") == 10 and "run-11" in runs and "run-1)" not in runs
