from datetime import datetime, timedelta, timezone

from events import MARKER
from fakes import FakeGH, my_pr
from gate import plan, still_valid

OWNER = "max930000"
NOW = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)
APPROVED = dict(reviewDecision="APPROVED")


def relay(n=10):
    return {"workflow_run": {"event": "pull_request_review", "head_branch": "story/1-6-x", "pull_requests": [{"number": n}]}}


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


def kinds(tasks):
    return [t["kind"] for t in tasks]


# --- merge（I4、I5、Focus 3）---

def test_merge_planned_as_script_when_approved():
    assert plan("workflow_run", relay(), OWNER, FakeGH(pr=my_pr(**APPROVED)), NOW) == [
        {"kind": "merge", "pr": 10, "story": None, "text": None, "mode": "script", "group": "flow-bot-pr-10", "checkout": "head"}
    ]


def test_no_merge_without_approval_decision():
    assert plan("workflow_run", relay(), OWNER, FakeGH(pr=my_pr(reviewDecision="CHANGES_REQUESTED")), NOW) == []


def test_merge_skipped_when_waiting_paused_or_awaiting_spec_approval():
    for label in ["flow-bot:等待回覆", "flow-bot:暫停", "flow-bot:等待核准"]:
        gh = FakeGH(pr=my_pr(labels=[label], **APPROVED))
        assert "merge" not in kinds(plan("workflow_run", relay(), OWNER, gh, NOW))


def test_merge_skipped_for_draft():
    assert plan("workflow_run", relay(), OWNER, FakeGH(pr=my_pr(isDraft=True, **APPROVED)), NOW) == []


def test_merge_skipped_when_auto_merge_already_on():
    assert plan("workflow_run", relay(), OWNER, FakeGH(pr=my_pr(autoMergeRequest={"mergeMethod": "SQUASH"}, **APPROVED)), NOW) == []


def test_merge_waits_for_pending_feedback():
    gh = FakeGH(pr=my_pr(**APPROVED), comments=[comment("OG-Matcha", "LGTM，但 X 要改名", 1)])
    assert kinds(plan("workflow_run", relay(), OWNER, gh, NOW)) == ["feedback"]


def test_merge_not_blocked_by_bot_thread():
    gh = FakeGH(pr=my_pr(**APPROVED), threads=[unresolved(last="Copilot")])
    assert kinds(plan("workflow_run", relay(), OWNER, gh, NOW)) == ["merge"]


def test_merge_blocked_by_teammate_thread():
    gh = FakeGH(pr=my_pr(**APPROVED), threads=[unresolved(last="sususu0804")])
    assert kinds(plan("workflow_run", relay(), OWNER, gh, NOW)) == ["feedback"]


# --- feedback ---

def test_feedback_dropped_when_nothing_pending():
    assert plan("workflow_run", relay(), OWNER, FakeGH(), NOW) == []


def test_feedback_planned_for_claude():
    [task] = plan("workflow_run", relay(), OWNER, FakeGH(threads=[unresolved()]), NOW)
    assert (task["kind"], task["mode"], task["group"], task["checkout"]) == ("feedback", "claude", "flow-bot-pr-10", "head")


def test_feedback_dropped_when_paused_or_waiting():
    for label in ["flow-bot:暫停", "flow-bot:等待回覆"]:
        assert plan("workflow_run", relay(), OWNER, FakeGH(pr=my_pr(labels=[label]), threads=[unresolved()]), NOW) == []


def test_feedback_becomes_limit_after_5_rounds():
    bot = [comment(OWNER, MARKER + " 已修正", m) for m in (5, 15, 25, 35, 45)]
    gh = FakeGH(comments=bot + [comment("sususu0804", "再改", 1)])
    [task] = plan("workflow_run", relay(), OWNER, gh, NOW)
    assert (task["kind"], task["mode"]) == ("limit", "script")


def test_relay_without_pr_number_resolves_branch():
    payload = {"workflow_run": {"event": "pull_request_review", "head_branch": "story/1-6-x", "pull_requests": []}}
    assert kinds(plan("workflow_run", payload, OWNER, FakeGH(pr=my_pr(**APPROVED)), NOW)) == ["merge"]


def test_teammate_pr_check_on_someone_elses_pr_ignored():
    assert plan("workflow_run", relay(), OWNER, FakeGH(pr=my_pr(author="OG-Matcha", **APPROVED)), NOW) == []


# --- 核准 spec（C3、I3）---

def test_approve_requires_awaiting_label():
    gh = FakeGH(pr=my_pr(), comments=[comment(OWNER, "/flow-bot approve", 1)])
    assert plan("issue_comment", owner_comment("/flow-bot approve"), OWNER, gh, NOW) == []


def test_approve_starts_story_impl():
    gh = FakeGH(pr=my_pr(labels=["flow-bot:等待核准"]), comments=[comment(OWNER, MARKER + " 請核准", 5), comment(OWNER, "/flow-bot approve", 1)])
    [task] = plan("issue_comment", owner_comment("/flow-bot approve"), OWNER, gh, NOW)
    assert (task["kind"], task["story"], task["group"], task["checkout"]) == ("story_impl", "1.6", "flow-bot-story", "head")


def test_sweep_recovers_lost_approval():
    pr = my_pr(n=10, labels=["flow-bot:等待核准"])
    gh = FakeGH(my_open_prs=[pr], branches=["story/1-6-x"], comments=[comment(OWNER, "/flow-bot approve", 1)])
    assert ("story_impl", 10) in [(t["kind"], t["pr"]) for t in plan("schedule", {}, OWNER, gh, NOW)]


# --- 其他 ---

def test_instruct_planned_even_when_waiting():
    gh = FakeGH(pr=my_pr(labels=["flow-bot:等待回覆"]))
    [task] = plan("issue_comment", owner_comment("/flow-bot 改用 toast"), OWNER, gh, NOW)
    assert (task["kind"], task["text"], task["mode"]) == ("instruct", "改用 toast", "claude")


def test_instruct_dropped_when_paused():
    gh = FakeGH(pr=my_pr(labels=["flow-bot:暫停"]))
    assert plan("issue_comment", owner_comment("/flow-bot 改用 toast"), OWNER, gh, NOW) == []


def test_pause_resume_are_script():
    [task] = plan("issue_comment", owner_comment("/flow-bot pause"), OWNER, FakeGH(), NOW)
    assert (task["kind"], task["mode"]) == ("pause", "script")


def test_review_others_is_review_mode_on_main():
    payload = {"action": "opened", "pull_request": {"number": 95, "user": {"login": "OG-Matcha"}, "draft": False}}
    [task] = plan("pull_request_target", payload, OWNER, FakeGH(), NOW)
    assert (task["kind"], task["pr"], task["checkout"], task["mode"]) == ("review_others", 95, "main", "review")


def test_sync_and_story_expands():
    gh = FakeGH(
        my_open_prs=[my_pr(n=5, mergeStateStatus="BEHIND"), my_pr(n=6), my_pr(n=7, mergeStateStatus="DIRTY", labels=["flow-bot:暫停"])],
        branches=["main", "story/1-6-x"],
    )
    got = [(t["kind"], t["pr"], t["story"]) for t in plan("push", {"ref": "refs/heads/main"}, OWNER, gh, NOW)]
    assert got == [("sync", 5, None), ("story_spec", None, "4.7")]


def test_sweep_also_plans_merge_and_feedback():
    gh = FakeGH(my_open_prs=[my_pr(n=5, **APPROVED)], branches=["story/1-6-x"])
    assert ("merge", 5) in [(t["kind"], t["pr"]) for t in plan("schedule", {}, OWNER, gh, NOW)]


def test_story_spec_runs_on_main_in_story_group():
    [task] = plan("schedule", {}, OWNER, FakeGH(), NOW)
    assert (task["kind"], task["story"], task["checkout"], task["group"]) == ("story_spec", "1.6", "main", "flow-bot-story")


def test_unknown_owner_gets_nothing():
    assert plan("schedule", {}, "someone-else", FakeGH(), NOW) == []


# --- job 開始時重新確認（I2）---

def test_still_valid_feedback_false_after_handled():
    task = {"kind": "feedback", "pr": 10}
    assert still_valid(task, OWNER, FakeGH(threads=[unresolved()]), NOW) is True
    assert still_valid(task, OWNER, FakeGH(), NOW) is False


def test_still_valid_story_impl_false_once_label_removed():
    task = {"kind": "story_impl", "pr": 10}
    assert still_valid(task, OWNER, FakeGH(pr=my_pr(), comments=[comment(OWNER, "/flow-bot approve", 1)]), NOW) is False


def test_still_valid_story_spec_false_once_started():
    task = {"kind": "story_spec", "story": "1.6"}
    assert still_valid(task, OWNER, FakeGH(branches=[]), NOW) is True
    assert still_valid(task, OWNER, FakeGH(branches=["story/1-6-x"]), NOW) is False


def test_still_valid_sync_false_when_clean():
    assert still_valid({"kind": "sync", "pr": 10}, OWNER, FakeGH(pr=my_pr(mergeStateStatus="CLEAN")), NOW) is False
    assert still_valid({"kind": "sync", "pr": 10}, OWNER, FakeGH(pr=my_pr(mergeStateStatus="BEHIND")), NOW) is True


def test_still_valid_merge_false_after_auto_merge_on():
    gh = FakeGH(pr=my_pr(autoMergeRequest={"mergeMethod": "SQUASH"}, **APPROVED))
    assert still_valid({"kind": "merge", "pr": 10}, OWNER, gh, NOW) is False
