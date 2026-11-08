"""檢查指定檔案的分支覆蓋率達到門檻（Story 7.3）。

`coverage report --fail-under` 判斷的是敘述加分支的合計，分支不足時可能被敘述拉高，
所以這裡讀 `coverage json` 的結果，只看分支。

用法：python scripts/check_branch_coverage.py <coverage.json> <檔案> [<檔案> ...]
"""

import json
import sys
from pathlib import Path

THRESHOLD = 90.0


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2
    files = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["files"]
    below: list[str] = []
    for path in sys.argv[2:]:
        data = files.get(path)
        if data is None:
            below.append(f"{path}（沒有覆蓋率資料）")
            continue
        summary = data["summary"]
        total = summary["num_branches"]
        covered = summary["covered_branches"]
        percent = 100.0 if total == 0 else covered / total * 100
        print(f"{path}：分支 {covered}/{total}（{percent:.1f}%）")
        if percent < THRESHOLD:
            below.append(f"{path}（{percent:.1f}%）")
    if below:
        print(f"以下純函式的分支覆蓋率低於 {THRESHOLD:.0f}%：", file=sys.stderr)
        for item in below:
            print(f"  {item}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
