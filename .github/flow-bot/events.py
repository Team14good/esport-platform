"""把 GitHub 事件分類成 flow-bot 任務，並判斷 PR 目前的狀態。

規則見設計 6.2、6.4：機器人以 OWNER 身分操作，所以 OWNER 自己的留言
只有含 `/flow-bot` 指令時才處理。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

MARKER = "<!-- flow-bot -->"
COMMAND_PREFIX = "/flow-bot"
SIMPLE_COMMANDS = {"approve", "pause", "resume", "review"}
REVIEW_TRIGGER_ACTIONS = {"opened", "ready_for_review", "reopened"}
SYNC_STATES = {"BEHIND", "DIRTY"}


@dataclass(frozen=True)
class Task:
    kind: str
    pr: int | None = None
    text: str | None = None


def is_bot(user: dict | None) -> bool:
    if not user:
        return False
    login = user.get("login", "")
    return user.get("type") == "Bot" or user.get("is_bot") is True or login.endswith("[bot]")


def _login(user: dict | None) -> str:
    return (user or {}).get("login", "")


def parse_command(body: str | None) -> Task | None:
    for line in (body or "").splitlines():
        line = line.strip()
        if not line.startswith(COMMAND_PREFIX):
            continue
        rest = line[len(COMMAND_PREFIX) :].strip()
        if rest in SIMPLE_COMMANDS:
            return Task(rest)
        if rest:
            return Task("instruct", text=rest)
    return None


def _with_pr(task: Task | None, pr: int) -> list[Task]:
    return [Task(task.kind, pr=pr, text=task.text)] if task else []


def classify(event_name: str, payload: dict, owner: str) -> list[Task]:
    if event_name == "pull_request_review":
        return _classify_review(payload, owner)
    if event_name == "issue_comment":
        return _classify_comment(payload, owner)
    if event_name == "pull_request_target":
        pr = payload.get("pull_request", {})
        if (
            payload.get("action") in REVIEW_TRIGGER_ACTIONS
            and _login(pr.get("user")) != owner
            and not pr.get("draft")
        ):
            return [Task("review_others", pr=pr["number"])]
        return []
    if event_name == "push":
        return [Task("sync_and_story")] if payload.get("ref") == "refs/heads/main" else []
    if event_name == "schedule":
        return [Task("sync_and_story")]
    if event_name == "workflow_dispatch":
        inputs = payload.get("inputs", {})
        pr = inputs.get("pr")
        return [Task(inputs["task"], pr=int(pr) if pr else None)]
    return []


def _classify_review(payload: dict, owner: str) -> list[Task]:
    if payload.get("action") != "submitted":
        return []
    pr = payload["pull_request"]
    review = payload["review"]
    number = pr["number"]
    if _login(pr.get("user")) != owner:
        return []
    reviewer = review.get("user")
    if _login(reviewer) == owner:
        return _with_pr(parse_command(review.get("body")), number)
    if is_bot(reviewer):
        return []
    if (review.get("state") or "").lower() == "approved":
        tasks = [Task("merge", pr=number)]
        if (review.get("body") or "").strip():
            tasks.append(Task("feedback", pr=number))
        return tasks
    return [Task("feedback", pr=number)]


def _classify_comment(payload: dict, owner: str) -> list[Task]:
    if payload.get("action") != "created":
        return []
    issue = payload["issue"]
    if not issue.get("pull_request"):
        return []
    number = issue["number"]
    comment = payload["comment"]
    commenter = comment.get("user")
    body = comment.get("body") or ""
    if is_bot(commenter):
        return []
    if _login(issue.get("user")) == owner:
        if _login(commenter) == owner:
            return _with_pr(parse_command(body), number)
        return [Task("feedback", pr=number)]
    command = parse_command(body)
    if command and command.kind == "review":
        return [Task("review_others", pr=number)]
    return []


def needs_sync(pr: dict) -> bool:
    return pr.get("mergeStateStatus") in SYNC_STATES or pr.get("mergeable") == "CONFLICTING"


def has_label(pr: dict, name: str) -> bool:
    return any(label.get("name") == name for label in pr.get("labels", []))


def _time(comment: dict) -> datetime:
    return datetime.fromisoformat(comment["createdAt"].replace("Z", "+00:00"))


def _is_bot_comment(comment: dict, owner: str) -> bool:
    return _login(comment.get("author")) == owner and MARKER in (comment.get("body") or "")


def pending_feedback(threads: list[dict], comments: list[dict], owner: str) -> bool:
    for t in threads:
        if t.get("isResolved"):
            continue
        nodes = t.get("comments", {}).get("nodes", [])
        if nodes and _login(nodes[-1].get("author")) != owner:
            return True
    bot_times = [_time(c) for c in comments if _is_bot_comment(c, owner)]
    last_bot = max(bot_times) if bot_times else None
    for c in comments:
        author = c.get("author")
        if _login(author) == owner or is_bot(author):
            continue
        if last_bot is None or _time(c) > last_bot:
            return True
    return False


def bot_rounds_last_hour(comments: list[dict], owner: str, now: datetime) -> int:
    since = now - timedelta(hours=1)
    return sum(1 for c in comments if _is_bot_comment(c, owner) and _time(c) >= since)
