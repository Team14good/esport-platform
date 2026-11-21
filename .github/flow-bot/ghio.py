"""包裝 gh 與 git 的呼叫；測試以 tests/fakes.py 的 FakeGH 取代 RealGH。"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

PR_FIELDS = "number,author,headRefName,isDraft,labels,mergeable,mergeStateStatus,state,title,reviewDecision,autoMergeRequest"

THREADS_QUERY = """
query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      reviewThreads(first: 100) {
        nodes { isResolved comments(last: 1) { nodes { author { login } } } }
      }
    }
  }
}
"""


def run_git(repo_dir: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo_dir, check=True, capture_output=True, text=True, encoding="utf-8"
    ).stdout


class RealGH:
    def __init__(self, repo: str | None = None):
        self.repo = repo or os.environ["GITHUB_REPOSITORY"]

    def _gh(self, *args: str, stdin: str | None = None) -> str:
        return subprocess.run(
            ["gh", *args], input=stdin, check=True, capture_output=True, text=True, encoding="utf-8"
        ).stdout

    def _json(self, *args: str):
        return json.loads(self._gh(*args) or "null")

    def pr(self, n: int) -> dict:
        return self._json("pr", "view", str(n), "-R", self.repo, "--json", PR_FIELDS)

    def my_open_prs(self, owner: str) -> list[dict]:
        return self._json("pr", "list", "-R", self.repo, "--author", owner, "--state", "open", "--json", PR_FIELDS)

    def pr_for_branch(self, branch: str) -> int | None:
        found = self._json("pr", "list", "-R", self.repo, "--head", branch, "--state", "open", "--json", "number")
        return found[0]["number"] if found else None

    def branches(self) -> list[str]:
        names = self._gh("api", f"repos/{self.repo}/branches", "--paginate", "--jq", ".[].name").split()
        heads = self._json("pr", "list", "-R", self.repo, "--state", "all", "--limit", "1000", "--json", "headRefName")
        return names + [h["headRefName"] for h in heads]

    def threads(self, n: int) -> list[dict]:
        owner, name = self.repo.split("/")
        data = self._json(
            "api", "graphql", "-f", f"query={THREADS_QUERY}", "-F", f"owner={owner}", "-F", f"name={name}", "-F", f"number={n}"
        )
        return data["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"]

    def comments(self, n: int) -> list[dict]:
        """PR 留言加上有內文的 review，統一成 {author, body, createdAt}。"""
        data = self._json("pr", "view", str(n), "-R", self.repo, "--json", "comments,reviews")
        items = [
            {"author": c["author"], "body": c.get("body") or "", "createdAt": c["createdAt"]}
            for c in data.get("comments", [])
        ]
        items += [
            {"author": r["author"], "body": r["body"], "createdAt": r["submittedAt"]}
            for r in data.get("reviews", [])
            if (r.get("body") or "").strip() and r.get("submittedAt")
        ]
        return items

    def file_on_main(self, path: str) -> str:
        return self._gh("api", f"repos/{self.repo}/contents/{path}?ref=main", "-H", "Accept: application/vnd.github.raw")

    def comment(self, n: int, body: str) -> None:
        self._gh("pr", "comment", str(n), "-R", self.repo, "--body-file", "-", stdin=body)

    def add_label(self, n: int, name: str) -> None:
        self._gh("pr", "edit", str(n), "-R", self.repo, "--add-label", name)

    def remove_label(self, n: int, name: str) -> None:
        self._gh("pr", "edit", str(n), "-R", self.repo, "--remove-label", name)

    def merge_auto(self, n: int) -> None:
        self._gh("pr", "merge", str(n), "-R", self.repo, "--auto", "--squash")
