"""把 GitHub 事件分類成 flow-bot 任務，並判斷 PR 目前的狀態。

規則見設計 6.2、6.4：
- 只理會組員（CONTRIBUTING 7.1 的成員，trusted）。repo 是公開的，陌生人與 bot 一律忽略。
- 機器人以 OWNER 身分操作，所以 OWNER 的留言含 MARKER 就是機器人自己留的，一律忽略；
  其餘 OWNER 留言只有含 `/flow-bot` 指令時才處理。
- 組員在 OWNER PR 上的留言與審查只產生 `pr_check`，實際要做什麼由 gate 依目前狀態決定。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

MARKER = "<!-- flow-bot -->"
COMMAND_PREFIX = "/flow-bot"
SIMPLE_COMMANDS = {"approve", "pause", "resume", "review"}
REVIEW_TRIGGER_ACTIONS = {"opened", "ready_for_review", "reopened"}
SYNC_STATES = {"BEHIND", "DIRTY"}
PR_DISPATCH_TASKS = {"review_others": "review_others", "feedback": "pr_check"}


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


def _owner_command(body: str | None) -> Task | None:
    """OWNER 留言裡的指令；含 MARKER 的是機器人自己留的，不算。"""
    if MARKER in (body or ""):
        return None
    return parse_command(body)


def classify(event_name: str, payload: dict, owner: str, trusted: set[str]) -> list[Task]:
    if event_name == "workflow_run":
        return _classify_relay(payload)
    if event_name == "issue_comment":
        return _classify_comment(payload, owner, trusted)
    if event_name == "pull_request_target":
        pr = payload.get("pull_request", {})
        author = _login(pr.get("user"))
        if (
            payload.get("action") in REVIEW_TRIGGER_ACTIONS
            and author != owner
            and author in trusted
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
        task, pr = inputs.get("task"), inputs.get("pr")
        if task in PR_DISPATCH_TASKS:
            return [Task(PR_DISPATCH_TASKS[task], pr=int(pr))] if pr else []
        return [Task(task)] if task else []
    return []


def _classify_relay(payload: dict) -> list[Task]:
    """flow-bot-relay（pull_request_review 觸發、不帶 secret）完成後的 workflow_run 事件。"""
    run = payload.get("workflow_run", {})
    if run.get("event") != "pull_request_review":
        return []
    prs = run.get("pull_requests") or []
    if prs:
        return [Task("pr_check", pr=prs[0]["number"])]
    return [Task("pr_check_branch", text=run.get("head_branch"))]


def _classify_comment(payload: dict, owner: str, trusted: set[str]) -> list[Task]:
    if payload.get("action") != "created":
        return []
    issue = payload["issue"]
    if not issue.get("pull_request"):
        return []
    number = issue["number"]
    comment = payload["comment"]
    commenter = comment.get("user")
    login = _login(commenter)
    if is_bot(commenter) or login not in trusted:
        return []
    body = comment.get("body") or ""
    pr_author = _login(issue.get("user"))
    if pr_author == owner:
        if login == owner:
            command = _owner_command(body)
            return [Task(command.kind, pr=number, text=command.text)] if command else []
        return [Task("pr_check", pr=number)]
    command = parse_command(body)
    if command and command.kind == "review" and pr_author in trusted:
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


def _last_bot_time(comments: list[dict], owner: str) -> datetime | None:
    times = [_time(c) for c in comments if _is_bot_comment(c, owner)]
    return max(times) if times else None


def _last_author(thread: dict) -> str:
    nodes = thread.get("comments", {}).get("nodes", [])
    return _login(nodes[-1].get("author")) if nodes else ""


def unresolved_trusted(threads: list[dict], trusted: set[str]) -> bool:
    """有組員參與、尚未解決的 review thread（bot 開的 thread 不算）。"""
    return any(not t.get("isResolved") and _last_author(t) in trusted for t in threads)


def pending_feedback(threads: list[dict], comments: list[dict], owner: str, trusted: set[str]) -> bool:
    teammates = trusted - {owner}
    if any(not t.get("isResolved") and _last_author(t) in teammates for t in threads):
        return True
    last_bot = _last_bot_time(comments, owner)
    return any(
        _login(c.get("author")) in teammates and (last_bot is None or _time(c) > last_bot) for c in comments
    )


def approve_requested(comments: list[dict], owner: str) -> bool:
    """OWNER 在機器人最後一則留言之後，留了 `/flow-bot approve`。"""
    last_bot = _last_bot_time(comments, owner)
    for c in comments:
        if _login(c.get("author")) != owner:
            continue
        command = _owner_command(c.get("body"))
        if command and command.kind == "approve" and (last_bot is None or _time(c) > last_bot):
            return True
    return False


def bot_rounds_last_hour(comments: list[dict], owner: str, now: datetime) -> int:
    since = now - timedelta(hours=1)
    return sum(1 for c in comments if _is_bot_comment(c, owner) and _time(c) >= since)
