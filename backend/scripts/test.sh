#!/usr/bin/env bash
# 用法：bash scripts/test.sh [pytest 參數]，例如 bash scripts/test.sh -k audit

set -e
set -x

FASTAPI_ENV=development coverage run -m pytest tests/ "$@"
# 只跑部分測試時 coverage 一定低於門檻（pyproject 的 fail_under），不以門檻判斷
threshold=()
if [ "$#" -gt 0 ]; then
  threshold=(--fail-under=0)
fi
coverage report "${threshold[@]}"
coverage html --title "coverage" "${threshold[@]}"
