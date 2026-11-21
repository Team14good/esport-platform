"""Claude 任務結束後的保險：找出這次執行期間 OWNER 送出的核准，撤銷並讓 job 失敗。

flow-bot 永遠不核准任何 PR（設計 5、6.8）；這支腳本確保萬一發生也會被撤回並被看見。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def approvals_since(reviews_by_pr: dict[int, list[dict]], owner: str, since: datetime) -> list[tuple[int, int]]:
    found = []
    for pr, reviews in reviews_by_pr.items():
        for r in reviews:
            if (
                r.get("user", {}).get("login") == owner
                and r.get("state") == "APPROVED"
                and r.get("submitted_at")
                and _parse(r["submitted_at"]) >= since
            ):
                found.append((pr, r["id"]))
    return found


def _gh(*args: str) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True, encoding="utf-8").stdout


def main() -> int:
    repo = os.environ["GITHUB_REPOSITORY"]
    owner = os.environ.get("FLOWBOT_OWNER") or "max930000"
    since = _parse(os.environ["SINCE"])
    prs = json.loads(_gh("pr", "list", "-R", repo, "--state", "open", "--json", "number"))
    reviews = {p["number"]: json.loads(_gh("api", f"repos/{repo}/pulls/{p['number']}/reviews", "--paginate")) for p in prs}
    bad = approvals_since(reviews, owner, since)
    for pr, review_id in bad:
        _gh(
            "api", "--method", "PUT", f"repos/{repo}/pulls/{pr}/reviews/{review_id}/dismissals",
            "-f", "message=flow-bot 不得核准 PR，這個核准已自動撤銷。", "-f", "event=DISMISS",
        )
        print(f"::error::flow-bot 在 PR #{pr} 送出了核准（review {review_id}），已撤銷")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
