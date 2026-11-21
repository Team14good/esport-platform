"""測試用的假 GH，記錄呼叫並回傳預設資料。"""

from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SPRINT = "_bmad-output/implementation-artifacts/sprint-status.yaml"
REAL_FIXTURES = {
    SPRINT: (FIXTURES / "sprint-status.yaml").read_text("utf-8"),
    "CONTRIBUTING.md": (FIXTURES / "CONTRIBUTING.md").read_text("utf-8"),
}


def my_pr(n=10, labels=(), head="story/1-6-x", mergeStateStatus="CLEAN", mergeable="MERGEABLE", author="max930000",
          reviewDecision="REVIEW_REQUIRED", isDraft=False, autoMergeRequest=None, state="OPEN"):
    return {
        "number": n,
        "author": {"login": author},
        "headRefName": head,
        "isDraft": isDraft,
        "reviewDecision": reviewDecision,
        "autoMergeRequest": autoMergeRequest,
        "labels": [{"name": name} for name in labels],
        "mergeable": mergeable,
        "mergeStateStatus": mergeStateStatus,
        "state": state,
        "title": f"PR {n}",
    }


class FakeGH:
    def __init__(self, pr=None, threads=(), comments=(), my_open_prs=(), branches=(), files=None):
        self._pr = pr or my_pr()
        self._threads = list(threads)
        self._comments = list(comments)
        self._my_open_prs = list(my_open_prs)
        self._branches = list(branches)
        self._files = files or REAL_FIXTURES
        self.calls = []

    def pr(self, n):
        for p in self._my_open_prs:
            if p["number"] == n:
                return p
        return dict(self._pr, number=n)

    def pr_for_branch(self, branch):
        return self._pr["number"] if self._pr["headRefName"] == branch else None

    def my_open_prs(self, owner):
        return self._my_open_prs

    def branches(self):
        return self._branches

    def threads(self, n):
        return self._threads

    def comments(self, n):
        return self._comments

    def file_on_main(self, path):
        return self._files[path]

    def comment(self, n, body):
        self.calls.append(("comment", n, body))

    def add_label(self, n, name):
        self.calls.append(("add_label", n, name))

    def remove_label(self, n, name):
        self.calls.append(("remove_label", n, name))

    def merge_auto(self, n):
        self.calls.append(("merge_auto", n))
