import subprocess
from unittest.mock import ANY

import pytest

from actions import run, set_story_status
from fakes import REAL_FIXTURES, SPRINT, FakeGH, my_pr

OWNER = "max930000"


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True, encoding="utf-8").stdout


@pytest.fixture
def tmp_git_repo(tmp_path):
    origin = tmp_path / "origin.git"
    work = tmp_path / "work"
    git(tmp_path, "init", "-q", "--bare", str(origin))
    git(tmp_path, "init", "-q", "-b", "main", str(work))
    git(work, "config", "user.email", "bot@example.com")
    git(work, "config", "user.name", "bot")
    target = work / SPRINT
    target.parent.mkdir(parents=True)
    target.write_bytes(REAL_FIXTURES[SPRINT].replace("1-6-通知中心: backlog", "1-6-通知中心: review").encode())
    git(work, "add", ".")
    git(work, "commit", "-q", "-m", "init")
    git(work, "remote", "add", "origin", str(origin))
    git(work, "push", "-q", "origin", "main")
    git(work, "push", "-q", "origin", "main:story/1-6-x")
    return work


def test_set_story_status_keeps_comment():
    line = "  1-6-通知中心: review  # 負責：A（期末）"
    assert set_story_status(line, "1.6", "done") == "  1-6-通知中心: done  # 負責：A（期末）"


def test_set_story_status_does_not_touch_1_60_or_11_6():
    text = "  1-60-x: backlog\n  11-6-y: backlog\n  1-6-z: backlog\n"
    assert set_story_status(text, "1.6", "done") == "  1-60-x: backlog\n  11-6-y: backlog\n  1-6-z: done\n"


def test_merge_action_commits_and_enables_auto_merge(tmp_git_repo):
    gh = FakeGH(pr=my_pr(head="story/1-6-x"))
    run({"kind": "merge", "pr": 10}, gh, tmp_git_repo, owner=OWNER)
    assert gh.calls[-2:] == [("merge_auto", 10), ("comment", 10, ANY)]
    pushed = git(tmp_git_repo, "show", f"origin/story/1-6-x:{SPRINT}")
    assert "1-6-通知中心: done" in pushed
    assert "Story 1.6 標記 done" in git(tmp_git_repo, "log", "-1", "--format=%s", "origin/story/1-6-x")


def test_merge_action_idempotent_when_already_done(tmp_git_repo):
    gh = FakeGH(pr=my_pr(head="story/1-6-x"))
    run({"kind": "merge", "pr": 10}, gh, tmp_git_repo, owner=OWNER)
    before = git(tmp_git_repo, "rev-parse", "origin/story/1-6-x")
    run({"kind": "merge", "pr": 10}, gh, tmp_git_repo, owner=OWNER)
    assert git(tmp_git_repo, "rev-parse", "origin/story/1-6-x") == before


def test_merge_non_story_pr_only_enables_auto_merge(tmp_git_repo):
    gh = FakeGH(pr=my_pr(head="docs/final-assignment"))
    run({"kind": "merge", "pr": 96}, gh, tmp_git_repo, owner=OWNER)
    assert ("merge_auto", 96) in gh.calls


def test_pause_and_resume_labels():
    gh = FakeGH()
    run({"kind": "pause", "pr": 10}, gh, None, owner=OWNER)
    run({"kind": "resume", "pr": 10}, gh, None, owner=OWNER)
    assert ("add_label", 10, "flow-bot:暫停") in gh.calls
    assert ("remove_label", 10, "flow-bot:暫停") in gh.calls


def test_limit_labels_and_mentions_owner():
    gh = FakeGH()
    run({"kind": "limit", "pr": 10}, gh, None, owner=OWNER)
    assert ("add_label", 10, "flow-bot:等待回覆") in gh.calls
    body = [c for c in gh.calls if c[0] == "comment"][0][2]
    assert body.startswith("<!-- flow-bot -->") and "@max930000" in body


def test_all_bot_comments_carry_marker(tmp_git_repo):
    gh = FakeGH(pr=my_pr(head="story/1-6-x"))
    for kind in ["pause", "resume", "limit"]:
        run({"kind": kind, "pr": 10}, gh, None, owner=OWNER)
    run({"kind": "merge", "pr": 10}, gh, tmp_git_repo, owner=OWNER)
    assert all(c[2].startswith("<!-- flow-bot -->") for c in gh.calls if c[0] == "comment")
