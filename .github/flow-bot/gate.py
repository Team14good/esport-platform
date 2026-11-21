"""flow-bot 的入口：把事件與目前狀態轉成要執行的任務清單。

沒事做就輸出空清單，workflow 不會啟動 Claude 或 Docker（設計 6.2）。
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from events import Task, bot_rounds_last_hour, classify, has_label, needs_sync, pending_feedback
from plan_rules import next_story, parse_batch_order, parse_dependencies, parse_members, parse_sprint_status, started_stories

SPRINT = "_bmad-output/implementation-artifacts/sprint-status.yaml"
LABEL_WAITING = "flow-bot:等待回覆"
LABEL_PAUSED = "flow-bot:暫停"
LABEL_AWAITING_APPROVAL = "flow-bot:等待核准"
MAX_ROUNDS_PER_HOUR = 5
STORY_GROUP = "flow-bot-story"


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


def plan(event_name: str, payload: dict, owner: str, gh, now: datetime) -> list[dict]:
    planned: list[dict] = []
    for t in classify(event_name, payload, owner):
        planned.extend(_expand(t, owner, gh, now))
    return planned


def _expand(t: Task, owner: str, gh, now: datetime) -> list[dict]:
    if t.kind == "sync_and_story":
        return _sync_and_story(owner, gh)
    if t.kind == "review_others":
        return [_task("review_others", pr=t.pr, checkout="main")]

    pr = gh.pr(t.pr)
    paused = has_label(pr, LABEL_PAUSED)

    if t.kind in ("pause", "resume"):
        return [_task(t.kind, pr=t.pr, mode="script")]
    if t.kind == "instruct":
        return [] if paused else [_task("instruct", pr=t.pr, text=t.text)]
    if t.kind == "feedback":
        if paused:
            return []
        comments = gh.comments(t.pr)
        if not pending_feedback(gh.threads(t.pr), comments, owner):
            return []
        if bot_rounds_last_hour(comments, owner, now) >= MAX_ROUNDS_PER_HOUR:
            return [_task("limit", pr=t.pr, mode="script")]
        return [_task("feedback", pr=t.pr)]
    if t.kind == "merge":
        if paused or has_label(pr, LABEL_WAITING):
            return []
        if any(not th.get("isResolved") for th in gh.threads(t.pr)):
            return []
        return [_task("merge", pr=t.pr, mode="script")]
    if t.kind == "approve":
        if not has_label(pr, LABEL_AWAITING_APPROVAL):
            return []
        return [_task("story_impl", pr=t.pr, story=_story_of(pr["headRefName"]), group=STORY_GROUP)]
    return []


def _sync_and_story(owner: str, gh) -> list[dict]:
    tasks = [
        _task("sync", pr=pr["number"])
        for pr in gh.my_open_prs(owner)
        if needs_sync(pr) and not has_label(pr, LABEL_PAUSED)
    ]
    contributing = gh.file_on_main("CONTRIBUTING.md")
    member = parse_members(contributing).get(owner)
    if member:
        entries = parse_sprint_status(gh.file_on_main(SPRINT))
        story = next_story(
            entries,
            member,
            parse_dependencies(contributing),
            parse_batch_order(contributing, member),
            started_stories(gh.branches()),
        )
        if story:
            tasks.append(_task("story_spec", story=story, checkout="main"))
    return tasks


def main() -> int:
    from ghio import RealGH

    event_name = os.environ["GITHUB_EVENT_NAME"]
    payload = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text("utf-8"))
    owner = os.environ.get("FLOWBOT_OWNER") or "max930000"
    tasks = plan(event_name, payload, owner, RealGH(), datetime.now(timezone.utc))
    script = [t for t in tasks if t["mode"] == "script"]
    claude = [t for t in tasks if t["mode"] == "claude"]
    lines = {
        "tasks": json.dumps(tasks, ensure_ascii=False),
        "script_tasks": json.dumps(script, ensure_ascii=False),
        "claude_tasks": json.dumps(claude, ensure_ascii=False),
        "has_script": str(bool(script)).lower(),
        "has_claude": str(bool(claude)).lower(),
    }
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8", newline="\n") as out:
        for key, value in lines.items():
            out.write(f"{key}={value}\n")
    print(json.dumps(tasks, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
