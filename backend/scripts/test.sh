#!/usr/bin/env bash
# 用法：bash scripts/test.sh [pytest 參數]，例如 bash scripts/test.sh -k audit

set -e
set -x

# 分支覆蓋率要達 90% 以上的純函式（Story 7.3；scripts/test-all.sh 的報告也讀這份清單）
PURE_FUNCTIONS=(
  app/modules/registration/allocation.py
  app/modules/competition/bracket.py
  app/modules/competition/schedule.py
  app/modules/competition/progression.py
)

FASTAPI_ENV=development coverage run -m pytest tests/ "$@"
# 只跑部分測試時 coverage 一定低於門檻（pyproject 的 fail_under），不以門檻判斷
threshold=()
if [ "$#" -gt 0 ]; then
  threshold=(--fail-under=0)
fi
coverage report "${threshold[@]}"
coverage html --title "coverage" "${threshold[@]}"

# 純函式逐檔檢查分支覆蓋率（coverage 的 --fail-under 看的是敘述加分支的合計，不能用）
if [ "$#" -eq 0 ]; then
  set +x
  coverage json -q -o /tmp/pure-functions-coverage.json --fail-under=0
  python scripts/check_branch_coverage.py /tmp/pure-functions-coverage.json "${PURE_FUNCTIONS[@]}"
fi
