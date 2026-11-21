from datetime import datetime, timedelta, timezone

from events import (
    MARKER,
    Task,
    bot_rounds_last_hour,
    classify,
    needs_sync,
    parse_command,
    pending_feedback,
)

OWNER = "max930000"
NOW = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)


def user(login, bot=False):
    return {"login": login, "type": "Bot" if bot else "User"}


def review_payload(author, reviewer, state, body, bot=False):
    return {
        "action": "submitted",
        "pull_request": {"number": 10, "user": user(author), "draft": False},
        "review": {"user": user(reviewer, bot), "state": state, "body": body},
    }


def comment_payload(pr_author, commenter, body, bot=False):
    return {
        "action": "created",
        "issue": {"number": 10, "user": user(pr_author), "pull_request": {"url": "x"}},
        "comment": {"user": user(commenter, bot), "body": body},
    }


def pr_payload(author, action, draft):
    return {"action": action, "pull_request": {"number": 10, "user": user(author), "draft": draft}}


def c(login, body, t=None, minutes_ago=None, bot=False):
    when = NOW - timedelta(minutes=minutes_ago) if minutes_ago is not None else NOW - timedelta(hours=10 - t)
    return {"author": user(login, bot), "body": body, "createdAt": when.isoformat()}


def thread(resolved, last):
    return {"isResolved": resolved, "comments": {"nodes": [{"author": {"login": last}}]}}


def test_teammate_changes_requested_is_feedback():
    p = review_payload(OWNER, "sususu0804", "changes_requested", "x")
    assert classify("pull_request_review", p, OWNER) == [Task("feedback", pr=10)]


def test_approve_with_body_is_merge_and_feedback():
    p = review_payload(OWNER, "OG-Matcha", "approved", "小建議")
    assert [t.kind for t in classify("pull_request_review", p, OWNER)] == ["merge", "feedback"]


def test_approve_without_body_is_merge_only():
    p = review_payload(OWNER, "OG-Matcha", "approved", "")
    assert classify("pull_request_review", p, OWNER) == [Task("merge", pr=10)]


def test_owner_plain_comment_ignored():
    p = comment_payload(OWNER, OWNER, "@sususu0804 幫我看一下")
    assert classify("issue_comment", p, OWNER) == []


def test_owner_plain_review_ignored():
    p = review_payload(OWNER, OWNER, "commented", "自己的備註")
    assert classify("pull_request_review", p, OWNER) == []


def test_owner_commands():
    assert classify("issue_comment", comment_payload(OWNER, OWNER, "/flow-bot approve"), OWNER) == [Task("approve", pr=10)]
    assert classify("issue_comment", comment_payload(OWNER, OWNER, "/flow-bot 改成用 toast"), OWNER) == [
        Task("instruct", pr=10, text="改成用 toast")
    ]


def test_parse_command_variants():
    assert parse_command("前言\n/flow-bot pause") == Task("pause")
    assert parse_command("/flow-bot resume") == Task("resume")
    assert parse_command("沒有指令") is None


def test_bot_comment_ignored():
    p = comment_payload(OWNER, "github-actions[bot]", "CI failed", bot=True)
    assert classify("issue_comment", p, OWNER) == []


def test_review_request_on_others_pr():
    p = comment_payload("OG-Matcha", "OG-Matcha", "/flow-bot review")
    assert classify("issue_comment", p, OWNER) == [Task("review_others", pr=10)]
    p2 = comment_payload("OG-Matcha", "sususu0804", "LGTM")
    assert classify("issue_comment", p2, OWNER) == []


def test_issue_comment_not_on_pr_ignored():
    p = comment_payload(OWNER, "sususu0804", "hi")
    del p["issue"]["pull_request"]
    assert classify("issue_comment", p, OWNER) == []


def test_others_pr_opened_review():
    assert classify("pull_request_target", pr_payload("OG-Matcha", "opened", draft=False), OWNER) == [
        Task("review_others", pr=10)
    ]
    assert classify("pull_request_target", pr_payload("OG-Matcha", "opened", draft=True), OWNER) == []
    assert classify("pull_request_target", pr_payload(OWNER, "opened", draft=False), OWNER) == []
    assert classify("pull_request_target", pr_payload("OG-Matcha", "synchronize", draft=False), OWNER) == []


def test_push_main_and_schedule():
    assert classify("push", {"ref": "refs/heads/main"}, OWNER) == [Task("sync_and_story")]
    assert classify("push", {"ref": "refs/heads/story/1-6"}, OWNER) == []
    assert classify("schedule", {}, OWNER) == [Task("sync_and_story")]


def test_workflow_dispatch():
    p = {"inputs": {"task": "review_others", "pr": "95"}}
    assert classify("workflow_dispatch", p, OWNER) == [Task("review_others", pr=95)]
    assert classify("workflow_dispatch", {"inputs": {"task": "sync_and_story", "pr": ""}}, OWNER) == [
        Task("sync_and_story")
    ]


def test_pending_feedback_false_after_bot_reply():
    comments = [c("sususu0804", "請改名", t=1), c(OWNER, MARKER + " 已修正", t=2)]
    assert pending_feedback([], comments, OWNER) is False


def test_pending_feedback_true_for_new_comment():
    comments = [c(OWNER, MARKER + " 已修正", t=1), c("sususu0804", "還有一個", t=2)]
    assert pending_feedback([], comments, OWNER) is True


def test_pending_feedback_ignores_bots():
    comments = [c("github-actions[bot]", "CI", t=2, bot=True)]
    assert pending_feedback([], comments, OWNER) is False


def test_pending_feedback_unresolved_thread():
    assert pending_feedback([thread(resolved=False, last="sususu0804")], [], OWNER) is True
    assert pending_feedback([thread(resolved=False, last=OWNER)], [], OWNER) is False
    assert pending_feedback([thread(resolved=True, last="sususu0804")], [], OWNER) is False


def test_needs_sync():
    assert needs_sync({"mergeStateStatus": "BEHIND", "mergeable": "MERGEABLE"})
    assert needs_sync({"mergeStateStatus": "DIRTY", "mergeable": "CONFLICTING"})
    assert not needs_sync({"mergeStateStatus": "CLEAN", "mergeable": "MERGEABLE"})


def test_bot_rounds_last_hour():
    comments = [c(OWNER, MARKER, minutes_ago=m) for m in (5, 30, 70)] + [c(OWNER, "普通留言", minutes_ago=1)]
    assert bot_rounds_last_hour(comments, OWNER, NOW) == 2
