"""把 Claude 寫好的審查結果（flow-bot-review.json）以 COMMENT 送出。

review_others 的 Claude 只拿到唯讀權杖，送出 review 的是這支腳本：
event 在這裡寫死為 COMMENT，Claude 寫什麼都不會變成核准（設計 5、6.4）。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from events import MARKER

DISCLAIMER = "A 的 AI 助手自動審查，只留意見，核准由組員決定。"
NO_FINDINGS = "沒有找到需要修改的地方。"
AI_LOG = re.compile(r"(<!-- ai-log:start -->\n?)(.*?)(<!-- ai-log:end -->)", re.DOTALL)
STATUS_TITLE = "flow-bot 狀態"


def build_review(data: dict) -> dict:
    comments = [
        {"path": c["path"], "line": int(c["line"]), "side": "RIGHT", "body": c["body"]}
        for c in data.get("comments", [])
    ]
    body = (data.get("body") or "").strip() or (NO_FINDINGS if not comments else "")
    return {"event": "COMMENT", "body": f"{MARKER}\n{DISCLAIMER}\n\n{body}".rstrip(), "comments": comments}


def append_ai_log(issue_body: str, line: str) -> str:
    m = AI_LOG.search(issue_body)
    if not m:
        return f"{issue_body.rstrip()}\n\n<!-- ai-log:start -->\n{line}\n<!-- ai-log:end -->\n"
    inner = m.group(2)
    if inner and not inner.endswith("\n"):
        inner += "\n"
    return issue_body[: m.start()] + m.group(1) + inner + line + "\n" + m.group(3) + issue_body[m.end() :]


def _gh(*args: str, stdin: str | None = None) -> str:
    return subprocess.run(["gh", *args], input=stdin, check=True, capture_output=True, text=True, encoding="utf-8").stdout


def main() -> int:
    repo = os.environ["GITHUB_REPOSITORY"]
    pr = int(os.environ["PR"])
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "flow-bot-review.json")
    data = json.loads(path.read_text("utf-8"))
    review = build_review(data)
    _gh("api", f"repos/{repo}/pulls/{pr}/reviews", "--method", "POST", "--input", "-", stdin=json.dumps(review))

    author = json.loads(_gh("pr", "view", str(pr), "-R", repo, "--json", "author"))["author"]["login"]
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    summary = (data.get("summary") or "無").replace("\n", " ")
    line = f"- {today} 審查 #{pr}（{author}）：{len(review['comments'])} 則意見，{summary}"
    issues = json.loads(_gh("issue", "list", "-R", repo, "--state", "open", "--search", f'in:title "{STATUS_TITLE}"', "--json", "number,title,body"))
    issue = next((i for i in issues if i["title"] == STATUS_TITLE), None)
    if issue:
        _gh("issue", "edit", str(issue["number"]), "-R", repo, "--body-file", "-", stdin=append_ai_log(issue["body"], line))
    else:
        print(f"找不到狀態 issue，AI 紀錄未暫存：{line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
