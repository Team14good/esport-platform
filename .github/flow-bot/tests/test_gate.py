from datetime import datetime, timedelta, timezone

from events import MARKER
from fakes import FakeGH, my_pr
from gate import plan

OWNER = "max930000"
NOW = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)


def review(state, body="x", reviewer="sususu0804"):
    return {
        "action": "submitted",
        "pull_request": {"number": 10, "user": {"login": OWNER}, "draft": False},
        "review": {"user": {"login": reviewer, "type": "User"}, "state": state, "body": body},
    }


def owner_comment(body):
    return {
        "action": "created",
        "issue": {"number": 10, "user": {"login": OWNER}, "pull_request": {"url": "x"}},
        "comment": {"user": {"login": OWNER, "type": "User"}, "body": body},
    }


def comment(login, body, minutes_ago):
    return {"author": {"login": login}, "body": body, "createdAt": (NOW - timedelta(minutes=minutes_ago)).isoformat()}


def unresolved(last="sususu0804"):
    return {"isResolved": False, "comments": {"nodes": [{"author": {"login": last}}]}}


def test_merge_skipped_when_waiting_or_paused():
    for label in ["flow-bot:等待回覆", "flow-bot:暫停"]:
        gh = FakeGH(pr=my_pr(labels=[label]))
        assert plan("pull_request_review", review("approved", body=""), OWNER, gh, NOW) == []


def test_merge_skipped_with_unresolved_thread():
    gh = FakeGH(threads=[unresolved()])
    assert plan("pull_request_review", review("approved", body=""), OWNER, gh, NOW) == []


def test_merge_planned_as_script():
    gh = FakeGH()
    assert plan("pull_request_review", review("approved", body=""), OWNER, gh, NOW) == [
        {"kind": "merge", "pr": 10, "story": None, "text": None, "mode": "script", "group": "flow-bot-pr-10", "checkout": "head"}
    ]


def test_feedback_dropped_when_nothing_pending():
    gh = FakeGH(threads=[], comments=[])
    assert plan("pull_request_review", review("changes_requested"), OWNER, gh, NOW) == []


def test_feedback_planned_for_claude():
    gh = FakeGH(threads=[unresolved()])
    [task] = plan("pull_request_review", review("changes_requested"), OWNER, gh, NOW)
    assert (task["kind"], task["mode"], task["group"], task["checkout"]) == ("feedback", "claude", "flow-bot-pr-10", "head")


def test_feedback_dropped_when_paused():
    gh = FakeGH(pr=my_pr(labels=["flow-bot:暫停"]), threads=[unresolved()])
    assert plan("pull_request_review", review("changes_requested"), OWNER, gh, NOW) == []


def test_feedback_becomes_limit_after_5_rounds():
    bot = [comment(OWNER, MARKER + " 已修正", m) for m in (5, 15, 25, 35, 45)]
    gh = FakeGH(comments=bot + [comment("sususu0804", "再改", 1)])
    [task] = plan("pull_request_review", review("changes_requested"), OWNER, gh, NOW)
    assert (task["kind"], task["mode"]) == ("limit", "script")


def test_approve_requires_awaiting_label():
    assert plan("issue_comment", owner_comment("/flow-bot approve"), OWNER, FakeGH(pr=my_pr(labels=[])), NOW) == []
    gh = FakeGH(pr=my_pr(labels=["flow-bot:等待核准"]))
    [task] = plan("issue_comment", owner_comment("/flow-bot approve"), OWNER, gh, NOW)
    assert (task["kind"], task["story"], task["group"], task["checkout"]) == ("story_impl", "1.6", "flow-bot-story", "head")


def test_instruct_planned_even_without_pending_feedback():
    [task] = plan("issue_comment", owner_comment("/flow-bot 改用 toast"), OWNER, FakeGH(), NOW)
    assert (task["kind"], task["text"], task["mode"]) == ("instruct", "改用 toast", "claude")


def test_pause_resume_are_script():
    [task] = plan("issue_comment", owner_comment("/flow-bot pause"), OWNER, FakeGH(), NOW)
    assert (task["kind"], task["mode"]) == ("pause", "script")


def test_review_others_checks_out_main():
    payload = {"action": "opened", "pull_request": {"number": 95, "user": {"login": "OG-Matcha"}, "draft": False}}
    [task] = plan("pull_request_target", payload, OWNER, FakeGH(), NOW)
    assert (task["kind"], task["pr"], task["checkout"], task["mode"]) == ("review_others", 95, "main", "claude")


def test_sync_and_story_expands():
    gh = FakeGH(
        my_open_prs=[my_pr(n=5, mergeStateStatus="BEHIND"), my_pr(n=6), my_pr(n=7, mergeStateStatus="DIRTY", labels=["flow-bot:暫停"])],
        branches=["main", "story/1-6-x"],
    )
    kinds = [(t["kind"], t["pr"], t["story"]) for t in plan("push", {"ref": "refs/heads/main"}, OWNER, gh, NOW)]
    assert kinds == [("sync", 5, None), ("story_spec", None, "4.7")]


def test_story_spec_runs_on_main_in_story_group():
    [task] = plan("schedule", {}, OWNER, FakeGH(), NOW)
    assert (task["kind"], task["story"], task["checkout"], task["group"]) == ("story_spec", "1.6", "main", "flow-bot-story")


def test_unknown_owner_gets_no_story():
    assert plan("schedule", {}, "someone-else", FakeGH(), NOW) == []
