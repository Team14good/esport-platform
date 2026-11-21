"""規則寫死、不需要 Claude 的任務：暫停／恢復、輪數上限、標記 done 並開 auto-merge。"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

from events import MARKER
from gate import LABEL_PAUSED, LABEL_WAITING, MAX_ROUNDS_PER_HOUR, SPRINT, _story_of
from ghio import run_git


def set_story_status(text: str, story_id: str, status: str) -> str:
    epic, story = story_id.split(".")
    pattern = re.compile(rf"^(\s+{epic}-{story}-\S+?:\s*)[\w-]+", re.MULTILINE)
    return pattern.sub(lambda m: m.group(1) + status, text, count=1)


def _say(gh, pr: int, text: str) -> None:
    gh.comment(pr, f"{MARKER}\n{text}")


def run(task: dict, gh, repo_dir: Path | None, owner: str) -> None:
    kind, pr = task["kind"], task["pr"]
    if kind == "pause":
        gh.add_label(pr, LABEL_PAUSED)
        _say(gh, pr, "flow-bot 已暫停這個 PR。要恢復時留言 `/flow-bot resume`。")
    elif kind == "resume":
        gh.remove_label(pr, LABEL_PAUSED)
        _say(gh, pr, "flow-bot 已恢復處理這個 PR。")
    elif kind == "limit":
        gh.add_label(pr, LABEL_WAITING)
        _say(
            gh,
            pr,
            f"@{owner} 這個 PR 在 1 小時內已自動修正 {MAX_ROUNDS_PER_HOUR} 輪，flow-bot 先停下，"
            "避免和審查者無限來回。看過後留言 `/flow-bot <指示>` 讓我繼續。",
        )
    elif kind == "merge":
        _merge(gh, pr, repo_dir)
    else:
        raise ValueError(f"不是腳本任務：{kind}")


def _merge(gh, pr: int, repo_dir: Path) -> None:
    head = gh.pr(pr)["headRefName"]
    story = _story_of(head)
    if story:
        run_git(repo_dir, "fetch", "-q", "origin", head)
        run_git(repo_dir, "checkout", "-q", "-B", head, f"origin/{head}")
        path = repo_dir / SPRINT
        before = path.read_bytes().decode("utf-8")
        after = set_story_status(before, story, "done")
        if after != before:
            path.write_bytes(after.encode("utf-8"))
            run_git(repo_dir, "add", SPRINT)
            run_git(repo_dir, "commit", "-q", "-m", f"chore: Story {story} 標記 done")
            run_git(repo_dir, "push", "-q", "origin", f"HEAD:{head}")
    gh.merge_auto(pr)
    done_note = f"sprint-status 的 Story {story} 已改為 `done`，" if story else ""
    _say(gh, pr, f"組員已核准。{done_note}已開啟 auto-merge（squash），CI 通過且跟上 `main` 後會自動合併。")


def main() -> int:
    from ghio import RealGH

    task = json.loads(sys.argv[1])
    owner = os.environ.get("FLOWBOT_OWNER") or "max930000"
    run(task, RealGH(), Path.cwd(), owner)
    return 0


if __name__ == "__main__":
    sys.exit(main())
