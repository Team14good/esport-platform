from datetime import datetime, timezone

from events import MARKER
from guard import approvals_since
from post_review import append_ai_log, build_review

OWNER = "max930000"
SINCE = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)


def test_build_review_forces_comment_event():
    data = {"event": "APPROVE", "body": "看起來不錯", "comments": [{"path": "a.py", "line": 3, "body": "這裡會 None"}], "summary": "a.py None"}
    review = build_review(data)
    assert review["event"] == "COMMENT"
    assert review["body"].startswith(MARKER + "\nA 的 AI 助手自動審查，只留意見，核准由組員決定。")
    assert review["comments"] == [{"path": "a.py", "line": 3, "side": "RIGHT", "body": "這裡會 None"}]


def test_build_review_empty_findings():
    review = build_review({"body": "", "comments": []})
    assert "沒有找到需要修改的地方" in review["body"]
    assert review["comments"] == []


def test_append_ai_log_inserts_inside_block():
    body = "x\n<!-- ai-log:start -->\n- 舊的\n<!-- ai-log:end -->\n"
    out = append_ai_log(body, "- 新的")
    assert "- 舊的\n- 新的\n<!-- ai-log:end -->" in out


def test_append_ai_log_creates_block_when_missing():
    assert "<!-- ai-log:start -->\n- 新的\n<!-- ai-log:end -->" in append_ai_log("", "- 新的")


def review(pr_user, state, at):
    return {"id": 1, "user": {"login": pr_user}, "state": state, "submitted_at": at}


def test_approvals_since_finds_owner_approval_during_run():
    reviews = {95: [review(OWNER, "APPROVED", "2026-11-21T12:05:00Z"), review("OG-Matcha", "APPROVED", "2026-11-21T12:06:00Z")]}
    assert approvals_since(reviews, OWNER, SINCE) == [(95, 1)]


def test_approvals_since_ignores_old_and_comment_reviews():
    reviews = {95: [review(OWNER, "APPROVED", "2026-11-21T11:00:00Z"), review(OWNER, "COMMENTED", "2026-11-21T12:05:00Z")]}
    assert approvals_since(reviews, OWNER, SINCE) == []
