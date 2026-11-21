"""解析 sprint-status 與 CONTRIBUTING 第 7 節，決定 flow-bot 下一個要做的 Story。

只用標準函式庫：workflow 的 gate job 不安裝任何套件。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

STORY_LINE = re.compile(r"^\s+(\d+)-(\d+)-(\S+?):\s*([\w-]+)(.*)$")
OWNER_TAG = re.compile(r"負責：([A-D])")
STORY_ID = re.compile(r"\d+\.\d+")
MEMBER_CELL = re.compile(r"^([A-D])：.*?（@([\w-]+)）")
BRANCH = re.compile(r"^story/(\d+)-(\d+)(?:-|$)")


@dataclass(frozen=True)
class StoryEntry:
    key: str
    story_id: str
    status: str
    owner: str | None


def parse_sprint_status(text: str) -> list[StoryEntry]:
    entries: list[StoryEntry] = []
    in_status = False
    for line in text.splitlines():
        if line.startswith("development_status:"):
            in_status = True
            continue
        if not in_status:
            continue
        m = STORY_LINE.match(line)
        if not m:
            continue
        epic, story, slug, status, rest = m.groups()
        owner = OWNER_TAG.search(rest)
        entries.append(
            StoryEntry(
                key=f"{epic}-{story}-{slug}",
                story_id=f"{epic}.{story}",
                status=status,
                owner=owner.group(1) if owner else None,
            )
        )
    return entries


def _table_rows(text: str, header_first_cell: str) -> list[list[str]]:
    """回傳第一欄標題為 header_first_cell 的 Markdown 表格內容列（不含標題與分隔列）。"""
    rows: list[list[str]] = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        cells = _cells(line)
        if cells and cells[0] == header_first_cell:
            for body in lines[i + 2 :]:
                if not body.startswith("|"):
                    break
                rows.append(_cells(body))
            break
    return rows


def _cells(line: str) -> list[str]:
    if not line.startswith("|"):
        return []
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _section(text: str, heading_prefix: str) -> str:
    start = text.find(heading_prefix)
    if start < 0:
        return ""
    end = text.find("\n### ", start + len(heading_prefix))
    return text[start : end if end >= 0 else len(text)]


def parse_members(contributing: str) -> dict[str, str]:
    members: dict[str, str] = {}
    for row in _table_rows(_section(contributing, "### 7.1"), "組員"):
        m = MEMBER_CELL.match(row[0])
        if m:
            members[m.group(2)] = m.group(1)
    return members


def parse_dependencies(contributing: str) -> dict[str, set[str]]:
    deps: dict[str, set[str]] = {}
    for row in _table_rows(_section(contributing, "### 7.2"), "要等的 Story"):
        waited_on = set(STORY_ID.findall(row[0]))
        for waiter in STORY_ID.findall(row[1]):
            deps.setdefault(waiter, set()).update(waited_on)
    return deps


def parse_batch_order(contributing: str, member: str) -> list[str]:
    section = _section(contributing, "### 7.2")
    header = next((_cells(l) for l in section.splitlines() if _cells(l)[:1] == ["批次"]), [])
    if member not in header:
        return []
    col = header.index(member)
    order: list[str] = []
    for row in _table_rows(section, "批次"):
        if col < len(row):
            order.extend(STORY_ID.findall(row[col]))
    return order


def _id_key(story_id: str) -> tuple[int, int]:
    epic, story = story_id.split(".")
    return int(epic), int(story)


def next_story(
    entries: list[StoryEntry],
    member: str,
    deps: dict[str, set[str]],
    order: list[str],
    started: set[str],
) -> str | None:
    status = {e.story_id: e.status for e in entries}
    candidates = [
        e.story_id
        for e in entries
        if e.owner == member
        and e.status == "backlog"
        and e.story_id not in started
        and all(status.get(d) == "done" for d in deps.get(e.story_id, set()))
    ]
    if not candidates:
        return None
    rank = {s: i for i, s in enumerate(order)}
    candidates.sort(key=lambda s: (rank.get(s, len(order)), _id_key(s)))
    return candidates[0]


def all_done(entries: list[StoryEntry], member: str) -> bool:
    mine = [e for e in entries if e.owner == member]
    return bool(mine) and all(e.status == "done" for e in mine)


def started_stories(branch_names: list[str]) -> set[str]:
    started: set[str] = set()
    for name in branch_names:
        m = BRANCH.match(name)
        if m:
            started.add(f"{m.group(1)}.{m.group(2)}")
    return started
