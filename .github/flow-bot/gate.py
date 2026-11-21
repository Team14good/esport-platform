"""flow-bot 的入口：把事件與目前狀態轉成要執行的任務清單。

- 沒事做就輸出空清單，workflow 不會啟動 Claude 或 Docker（設計 6.2）。
- 對 OWNER PR 要做什麼，一律由 `pr_state_tasks` 依「目前狀態」決定，事件只是叫醒它；
  每小時的 schedule 也會把所有 OWNER PR 再判斷一次，補回排隊時被取代的 job。
- job 開始前用 `still_valid` 再確認一次，避免排隊期間狀態已改變而重複執行。
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from events import (
    Task,
    approve_requested,
    bot_rounds_last_hour,
    classify,
    has_label,
    needs_sync,
    pending_feedback,
    unresolved_trusted,
)
from plan_rules import next_story, parse_batch_order, parse_dependencies, parse_members, parse_sprint_status, started_stories

SPRINT = "_bmad-output/implementation-artifacts/sprint-status.yaml"
LABEL_WAITING = "flow-bot:等待回覆"
LABEL_PAUSED = "flow-bot:暫停"
LABEL_AWAITING_APPROVAL = "flow-bot:等待核准"
MAX_ROUNDS_PER_HOUR = 5
STORY_GROUP = "flow-bot-story"
STATE_KINDS = {"feedback", "merge", "limit", "story_impl"}


def _task(kind, *, pr=None, story=None, text=None, mode="claude", group=None, checkout="head") -> dict:
    return {
        "kind": kind,
        "pr": pr,
        "story": story,
        "text": text,
        "mode": mode,
        "group": group or (f"flow-bot-pr-{pr}" if pr is not None else STORY_GROUP),
        "checkout": checkout,
    }


def _story_of(head: str) -> str | None:
    found = started_stories([head])
    return next(iter(found)) if found else None


def _trusted(gh) -> set[str]:
    return set(parse_members(gh.file_on_main("CONTRIBUTING.md")))


def plan(event_name: str, payload: dict, owner: str, gh, now: datetime) -> list[dict]:
    trusted = _trusted(gh)
    if owner not in trusted:
        return []
    planned: list[dict] = []
    for t in classify(event_name, payload, owner, trusted):
        planned.extend(_expand(t, owner, trusted, gh, now))
    return planned


def _expand(t: Task, owner: str, trusted: set[str], gh, now: datetime) -> list[dict]:
    if t.kind == "sync_and_story":
        return _sync_and_story(owner, trusted, gh, now)
    if t.kind == "review_others":
        return [_task("review_others", pr=t.pr, mode="review", checkout="main")]
    if t.kind == "pr_check_branch":
        n = gh.pr_for_branch(t.text) if t.text else None
        return pr_state_tasks(n, owner, trusted, gh, now) if n else []
    if t.kind in ("pr_check", "approve"):
        return pr_state_tasks(t.pr, owner, trusted, gh, now)
    if t.kind in ("pause", "resume"):
        return [_task(t.kind, pr=t.pr, mode="script")]
    if t.kind == "instruct":
        pr = gh.pr(t.pr)
        if pr["author"]["login"] != owner or has_label(pr, LABEL_PAUSED):
            return []
        return [_task("instruct", pr=t.pr, text=t.text)]
    return []


def pr_state_tasks(n: int, owner: str, trusted: set[str], gh, now: datetime) -> list[dict]:
    """OWNER 的 PR 目前該做的事：story_impl、feedback（或 limit）、merge，至多一件。"""
    pr = gh.pr(n)
    if pr["author"]["login"] != owner or pr.get("state", "OPEN") != "OPEN":
        return []
    if has_label(pr, LABEL_PAUSED) or has_label(pr, LABEL_WAITING):
        return []
    comments = gh.comments(n)
    if has_label(pr, LABEL_AWAITING_APPROVAL):
        if approve_requested(comments, owner):
            return [_task("story_impl", pr=n, story=_story_of(pr["headRefName"]), group=STORY_GROUP)]
        return []
    threads = gh.threads(n)
    if pending_feedback(threads, comments, owner, trusted):
        if bot_rounds_last_hour(comments, owner, now) >= MAX_ROUNDS_PER_HOUR:
            return [_task("limit", pr=n, mode="script")]
        return [_task("feedback", pr=n)]
    if (
        not pr.get("isDraft")
        and pr.get("reviewDecision") == "APPROVED"
        and not pr.get("autoMergeRequest")
        and not unresolved_trusted(threads, trusted)
    ):
        return [_task("merge", pr=n, mode="script")]
    return []


def _sync_and_story(owner: str, trusted: set[str], gh, now: datetime) -> list[dict]:
    tasks: list[dict] = []
    for pr in gh.my_open_prs(owner):
        if has_label(pr, LABEL_PAUSED):
            continue
        if needs_sync(pr):
            tasks.append(_task("sync", pr=pr["number"]))
        tasks.extend(pr_state_tasks(pr["number"], owner, trusted, gh, now))
    story = _next_story(owner, gh)
    if story:
        tasks.append(_task("story_spec", story=story, checkout="main"))
    return tasks


def _next_story(owner: str, gh) -> str | None:
    contributing = gh.file_on_main("CONTRIBUTING.md")
    member = parse_members(contributing).get(owner)
    if not member:
        return None
    return next_story(
        parse_sprint_status(gh.file_on_main(SPRINT)),
        member,
        parse_dependencies(contributing),
        parse_batch_order(contributing, member),
        started_stories(gh.branches()),
    )


def still_valid(task: dict, owner: str, gh, now: datetime) -> bool:
    kind = task["kind"]
    if kind in STATE_KINDS:
        return kind in [t["kind"] for t in pr_state_tasks(task["pr"], owner, _trusted(gh), gh, now)]
    if kind == "sync":
        pr = gh.pr(task["pr"])
        return needs_sync(pr) and not has_label(pr, LABEL_PAUSED)
    if kind == "story_spec":
        return task["story"] not in started_stories(gh.branches())
    return True


def _write_outputs(values: dict[str, str]) -> None:
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8", newline="\n") as out:
        for key, value in values.items():
            out.write(f"{key}={value}\n")


def main() -> int:
    from ghio import RealGH

    owner = os.environ.get("FLOWBOT_OWNER") or "max930000"
    now = datetime.now(timezone.utc)
    if sys.argv[1:] == ["recheck"]:
        task = json.loads(os.environ["TASK"])
        valid = still_valid(task, owner, RealGH(), now)
        print(f"{task['kind']} 仍需執行：{valid}")
        _write_outputs({"run": str(valid).lower()})
        return 0

    payload = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text("utf-8"))
    tasks = plan(os.environ["GITHUB_EVENT_NAME"], payload, owner, RealGH(), now)
    outputs: dict[str, str] = {}
    for mode in ("script", "claude", "review"):
        chosen = [t for t in tasks if t["mode"] == mode]
        outputs[f"{mode}_tasks"] = json.dumps(chosen, ensure_ascii=False)
        outputs[f"has_{mode}"] = str(bool(chosen)).lower()
    _write_outputs(outputs)
    print(json.dumps(tasks, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
