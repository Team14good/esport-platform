from datetime import datetime, timedelta, timezone

from events import (
    MARKER,
    Task,
    approve_requested,
    bot_rounds_last_hour,
    classify,
    needs_sync,
    parse_command,
    pending_feedback,
    unresolved_trusted,
)

OWNER = "max930000"
TRUSTED = {"max930000", "sususu0804", "happyhappy-happy", "OG-Matcha"}
NOW = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)


def user(login, bot=False):
    return {"login": login, "type": "Bot" if bot else "User"}


def comment_payload(pr_author, commenter, body, bot=False, on_pr=True):
    issue = {"number": 10, "user": user(pr_author)}
    if on_pr:
        issue["pull_request"] = {"url": "x"}
    return {"action": "created", "issue": issue, "comment": {"user": user(commenter, bot), "body": body}}


def pr_payload(author, action, draft):
    return {"action": action, "pull_request": {"number": 10, "user": user(author), "draft": draft}}


def relay_payload(prs, head_branch="story/1-6-x", event="pull_request_review"):
    return {"workflow_run": {"event": event, "head_branch": head_branch, "pull_requests": [{"number": n} for n in prs]}}


def c(login, body, t=None, minutes_ago=None):
    when = NOW - timedelta(minutes=minutes_ago) if minutes_ago is not None else NOW - timedelta(hours=10 - t)
    return {"author": {"login": login}, "body": body, "createdAt": when.isoformat()}


def thread(resolved, last):
    return {"isResolved": resolved, "comments": {"nodes": [{"author": {"login": last}}]}}


def cls(event, payload):
    return classify(event, payload, OWNER, TRUSTED)


# --- 事件分類 ---

def test_review_relay_becomes_pr_check():
    assert cls("workflow_run", relay_payload([10])) == [Task("pr_check", pr=10)]


def test_review_relay_without_pr_number_uses_branch():
    assert cls("workflow_run", relay_payload([])) == [Task("pr_check_branch", text="story/1-6-x")]


def test_relay_from_other_event_ignored():
    assert cls("workflow_run", relay_payload([10], event="push")) == []


def test_teammate_comment_on_own_pr_is_pr_check():
    assert cls("issue_comment", comment_payload(OWNER, "sususu0804", "請改名")) == [Task("pr_check", pr=10)]


def test_stranger_comment_on_own_pr_ignored():
    assert cls("issue_comment", comment_payload(OWNER, "random-stranger", "/flow-bot approve")) == []


def test_owner_plain_comment_ignored():
    assert cls("issue_comment", comment_payload(OWNER, OWNER, "@sususu0804 幫我看一下")) == []


def test_bot_own_comment_with_command_line_ignored():
    body = f"{MARKER}\n請核准 spec，核准方式：\n\n```\n/flow-bot approve\n```"
    assert cls("issue_comment", comment_payload(OWNER, OWNER, body)) == []


def test_owner_commands():
    assert cls("issue_comment", comment_payload(OWNER, OWNER, "/flow-bot approve")) == [Task("approve", pr=10)]
    assert cls("issue_comment", comment_payload(OWNER, OWNER, "/flow-bot 改成用 toast")) == [
        Task("instruct", pr=10, text="改成用 toast")
    ]


def test_parse_command_variants():
    assert parse_command("前言\n/flow-bot pause") == Task("pause")
    assert parse_command("/flow-bot resume") == Task("resume")
    assert parse_command("沒有指令") is None


def test_bot_comment_ignored():
    assert cls("issue_comment", comment_payload(OWNER, "github-actions[bot]", "CI failed", bot=True)) == []


def test_review_request_on_teammate_pr():
    assert cls("issue_comment", comment_payload("OG-Matcha", "OG-Matcha", "/flow-bot review")) == [Task("review_others", pr=10)]
    assert cls("issue_comment", comment_payload("OG-Matcha", "sususu0804", "LGTM")) == []


def test_review_request_from_stranger_or_on_stranger_pr_ignored():
    assert cls("issue_comment", comment_payload("OG-Matcha", "random-stranger", "/flow-bot review")) == []
    assert cls("issue_comment", comment_payload("random-stranger", "OG-Matcha", "/flow-bot review")) == []


def test_issue_comment_not_on_pr_ignored():
    assert cls("issue_comment", comment_payload(OWNER, "sususu0804", "hi", on_pr=False)) == []


def test_teammate_pr_opened_review():
    assert cls("pull_request_target", pr_payload("OG-Matcha", "opened", draft=False)) == [Task("review_others", pr=10)]
    assert cls("pull_request_target", pr_payload("OG-Matcha", "opened", draft=True)) == []
    assert cls("pull_request_target", pr_payload(OWNER, "opened", draft=False)) == []
    assert cls("pull_request_target", pr_payload("OG-Matcha", "synchronize", draft=False)) == []


def test_stranger_fork_pr_not_reviewed():
    assert cls("pull_request_target", pr_payload("random-stranger", "opened", draft=False)) == []


def test_push_main_and_schedule():
    assert cls("push", {"ref": "refs/heads/main"}) == [Task("sync_and_story")]
    assert cls("push", {"ref": "refs/heads/story/1-6"}) == []
    assert cls("schedule", {}) == [Task("sync_and_story")]


def test_workflow_dispatch():
    assert cls("workflow_dispatch", {"inputs": {"task": "review_others", "pr": "95"}}) == [Task("review_others", pr=95)]
    assert cls("workflow_dispatch", {"inputs": {"task": "sync_and_story", "pr": ""}}) == [Task("sync_and_story")]


def test_workflow_dispatch_pr_task_without_pr_ignored():
    assert cls("workflow_dispatch", {"inputs": {"task": "review_others", "pr": ""}}) == []
    assert cls("workflow_dispatch", {"inputs": {"task": "feedback", "pr": ""}}) == []


def test_workflow_dispatch_feedback_is_pr_check():
    assert cls("workflow_dispatch", {"inputs": {"task": "feedback", "pr": "12"}}) == [Task("pr_check", pr=12)]


# --- PR 狀態 ---

def test_pending_feedback_false_after_bot_reply():
    comments = [c("sususu0804", "請改名", t=1), c(OWNER, MARKER + " 已修正", t=2)]
    assert pending_feedback([], comments, OWNER, TRUSTED) is False


def test_pending_feedback_true_for_new_comment():
    comments = [c(OWNER, MARKER + " 已修正", t=1), c("sususu0804", "還有一個", t=2)]
    assert pending_feedback([], comments, OWNER, TRUSTED) is True


def test_pending_feedback_ignores_untrusted_and_bots():
    comments = [c("github-actions", "CI", t=2), c("Copilot", "建議", t=2), c("random-stranger", "改這個", t=2)]
    assert pending_feedback([], comments, OWNER, TRUSTED) is False


def test_pending_feedback_unresolved_thread():
    assert pending_feedback([thread(False, "sususu0804")], [], OWNER, TRUSTED) is True
    assert pending_feedback([thread(False, OWNER)], [], OWNER, TRUSTED) is False
    assert pending_feedback([thread(True, "sususu0804")], [], OWNER, TRUSTED) is False
    assert pending_feedback([thread(False, "Copilot")], [], OWNER, TRUSTED) is False


def test_unresolved_trusted_ignores_bot_threads():
    assert unresolved_trusted([thread(False, "Copilot")], TRUSTED) is False
    assert unresolved_trusted([thread(False, OWNER)], TRUSTED) is True


def test_approve_requested_after_bot_request():
    comments = [c(OWNER, MARKER + "\n請核准\n/flow-bot approve", t=1), c(OWNER, "/flow-bot approve", t=2)]
    assert approve_requested(comments, OWNER) is True


def test_approve_not_requested_by_bot_comment_alone():
    assert approve_requested([c(OWNER, MARKER + "\n/flow-bot approve", t=1)], OWNER) is False


def test_approve_superseded_by_later_bot_comment():
    comments = [c(OWNER, "/flow-bot approve", t=1), c(OWNER, MARKER + " 已開始實作", t=2)]
    assert approve_requested(comments, OWNER) is False


def test_needs_sync():
    assert needs_sync({"mergeStateStatus": "BEHIND", "mergeable": "MERGEABLE"})
    assert needs_sync({"mergeStateStatus": "DIRTY", "mergeable": "CONFLICTING"})
    assert not needs_sync({"mergeStateStatus": "CLEAN", "mergeable": "MERGEABLE"})


def test_bot_rounds_last_hour():
    comments = [c(OWNER, MARKER, minutes_ago=m) for m in (5, 30, 70)] + [c(OWNER, "普通留言", minutes_ago=1)]
    assert bot_rounds_last_hour(comments, OWNER, NOW) == 2
