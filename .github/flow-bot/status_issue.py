"""維護置頂的「flow-bot 狀態」issue（設計 6.7）。

「待補 AI 紀錄」區塊由 Claude 寫入與清空，這裡只原樣保留。
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone

from events import MARKER, has_label
from gate import LABEL_AWAITING_APPROVAL, LABEL_WAITING, SPRINT
from plan_rules import StoryEntry, all_done, parse_members, parse_sprint_status, started_stories

TITLE = "flow-bot 狀態"
AI_LOG = re.compile(r"<!-- ai-log:start -->\n?(.*?)<!-- ai-log:end -->", re.DOTALL)
RUN_LINE = re.compile(r"^- .*\[執行紀錄\]\(.*\)$", re.MULTILINE)
MAX_RUNS = 10


def _waiting_for(pr: dict | None) -> str:
    if pr is None:
        return "尚未開工"
    if has_label(pr, LABEL_AWAITING_APPROVAL):
        return "等你核准 spec"
    if has_label(pr, LABEL_WAITING):
        return "等你回覆"
    return "等組員審查或 CI"


def render(entries: list[StoryEntry], member: str, prs: list[dict], run_url: str, prev_body: str, now: str = "") -> str:
    pr_by_story = {}
    for pr in prs:
        for story in started_stories([pr["headRefName"]]):
            pr_by_story[story] = pr

    mine = [e for e in entries if e.owner == member]
    rows = [
        f"| {e.story_id} | {e.key} | {e.status} | "
        f"{'#' + str(pr_by_story[e.story_id]['number']) if e.story_id in pr_by_story else '—'} | "
        f"{_waiting_for(pr_by_story.get(e.story_id)) if e.status != 'done' else '—'} |"
        for e in mine
        if e.status != "done" or e.story_id in pr_by_story
    ]
    done_count = sum(1 for e in mine if e.status == "done")

    waiting = [
        f"- #{pr['number']} {pr['title']}（{_waiting_for(pr)}）"
        for pr in prs
        if has_label(pr, LABEL_AWAITING_APPROVAL) or has_label(pr, LABEL_WAITING)
    ]

    runs = RUN_LINE.findall(prev_body)
    stamp = f"{now} " if now else ""
    runs = [f"- {stamp}[執行紀錄]({run_url})"] + runs
    runs = runs[:MAX_RUNS]

    log = AI_LOG.search(prev_body)
    log_body = log.group(1) if log else ""

    parts = []
    if all_done(entries, member):
        parts.append(f"**{member} 的期末 Story 全部完成**\n")
    parts += [
        MARKER,
        "## Story 進度",
        "",
        "| Story | 名稱 | 狀態 | PR | 在等誰 |",
        "| --- | --- | --- | --- | --- |",
        *rows,
        "",
        f"已完成 {done_count} 個（含期中）。",
        "",
        "## 等你回覆",
        "",
        *(waiting or ["目前沒有。"]),
        "",
        "## 最近執行",
        "",
        *runs,
        "",
        "## 待補 AI 紀錄",
        "",
        f"<!-- ai-log:start -->\n{log_body}<!-- ai-log:end -->",
        "",
    ]
    return "\n".join(parts)


def main() -> int:
    from ghio import RealGH

    gh = RealGH()
    owner = os.environ.get("FLOWBOT_OWNER") or "max930000"
    member = parse_members(gh.file_on_main("CONTRIBUTING.md")).get(owner)
    if not member:
        print(f"CONTRIBUTING 7.1 找不到 @{owner}，不更新狀態 issue")
        return 0
    entries = parse_sprint_status(gh.file_on_main(SPRINT))
    issues = json.loads(
        gh._gh("issue", "list", "-R", gh.repo, "--state", "open", "--search", f'in:title "{TITLE}"', "--json", "number,title,body")
    )
    issue = next((i for i in issues if i["title"] == TITLE), None)
    prev = issue["body"] if issue else ""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    body = render(entries, member, gh.my_open_prs(owner), os.environ.get("RUN_URL", ""), prev, now)
    if issue:
        gh._gh("issue", "edit", str(issue["number"]), "-R", gh.repo, "--body-file", "-", stdin=body)
        number = issue["number"]
    else:
        url = gh._gh("issue", "create", "-R", gh.repo, "--title", TITLE, "--body-file", "-", stdin=body).strip()
        number = int(url.rsplit("/", 1)[-1])
        gh._gh("issue", "pin", str(number), "-R", gh.repo)
    banner = f"**{member} 的期末 Story 全部完成**"
    if banner in body and banner not in prev:
        gh._gh("issue", "comment", str(number), "-R", gh.repo, "--body-file", "-", stdin=f"{MARKER}\n@{owner} {member} 的期末 Story 全部完成，flow-bot 不再開新 Story；審查別人的 PR 會繼續，直到 `FLOWBOT_ENABLED` 關閉。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
