#!/usr/bin/env bash
# 測試總指令（Story 7.3）：依序跑單元、整合、端對端三層，最後產生繁中測試報告。
#
# 用法：bash scripts/test-all.sh [--skip-e2e] [--no-build]
#   --skip-e2e  略過端對端測試（報告的 e2e 區塊註明「本次略過」）
#   --no-build  不重新 build 容器（容器是 build 時複製原始碼，預設先 build 才會測到目前的程式）
#
# 產出（都不 commit）：
#   reports/test-report.md       測試報告
#   reports/coverage/index.html  後端覆蓋率 HTML
#   reports/raw/                 原始輸出（JUnit、coverage.json、Playwright json、計時檔）
#
# 任何一層失敗都會繼續跑完其餘層並產生報告，最後以非 0 結束。

set -u
# Windows 的 Git Bash 會把 /tmp/... 這類參數改寫成 Windows 路徑，容器內的路徑要原樣傳入
export MSYS_NO_PATHCONV=1

skip_e2e=0
build=1
for arg in "$@"; do
  case "$arg" in
    --skip-e2e) skip_e2e=1 ;;
    --no-build) build=0 ;;
    *)
      echo "不認得的參數：$arg（可用 --skip-e2e、--no-build）" >&2
      exit 2
      ;;
  esac
done

cd "$(dirname "$0")/.." || exit 1

REPORTS=reports
RAW="$REPORTS/raw"
# 容器內的暫存資料夾（backend、frontend 各一份）
WORK=/tmp/test-all
PURE_FUNCTIONS=$(sed -n '/^PURE_FUNCTIONS=(/,/^)/p' backend/scripts/test.sh | sed '1d;$d' | xargs | tr ' ' ',')

rm -rf "$REPORTS"
mkdir -p "$RAW"

step() {
  echo
  echo "==== $1 ===="
}

if [ "$build" -eq 1 ]; then
  step "重新 build 並啟動 compose"
  docker compose up -d --build --wait || exit 1
  if [ "$skip_e2e" -eq 0 ]; then
    docker compose --profile e2e build e2e || exit 1
  fi
fi

overall=0
layers_json=""

# record <key> <結束碼> <開始秒數>
record() {
  local seconds=$(($(date +%s) - $3))
  layers_json="${layers_json}\"$1\": {\"exit\": $2, \"skipped\": false, \"seconds\": $seconds},"
  if [ "$2" -ne 0 ]; then
    overall=1
  fi
}

# ---------------------------------------------------------------- 1. 單元：前端
step "1/3 單元測試：前端（Vitest）"
started=$(date +%s)
docker compose exec -T frontend sh -c \
  "rm -rf $WORK && mkdir -p $WORK && bun run test:unit --reporter=default --reporter=junit --outputFile.junit=$WORK/vitest-junit.xml"
record frontend_unit $? "$started"
docker compose cp "frontend:$WORK/vitest-junit.xml" "$RAW/" >/dev/null 2>&1

# ---------------------------------------------------------------- 1. 單元：後端
step "1/3 單元測試：後端（pytest -m unit）"
started=$(date +%s)
docker compose exec -T backend bash -c \
  "rm -rf $WORK && mkdir -p $WORK && coverage erase && FASTAPI_ENV=development coverage run -m pytest tests/ -m unit -p no:cacheprovider --junitxml=$WORK/backend-unit.xml"
record backend_unit $? "$started"

# ---------------------------------------------------------------- 2. 整合：後端
step "2/3 整合測試：後端（pytest -m integration，PostgreSQL 18）"
started=$(date +%s)
docker compose exec -T backend bash -c \
  "FASTAPI_ENV=development TEST_TIMINGS_FILE=$WORK/api-timings-integration.jsonl TEST_NFR1_FILE=$WORK/nfr1.jsonl coverage run --append -m pytest tests/ -m integration -p no:cacheprovider --junitxml=$WORK/backend-integration.xml"
record backend_integration $? "$started"

step "後端覆蓋率（整體 85%、純函式逐檔 90%）"
started=$(date +%s)
docker compose exec -T backend bash -c "
  coverage json -o $WORK/coverage.json --fail-under=0 -q
  coverage html -d $WORK/coverage --title coverage --fail-under=0 -q
  status=0
  coverage report --include='$PURE_FUNCTIONS' --fail-under=0
  python scripts/check_branch_coverage.py $WORK/coverage.json \$(echo '$PURE_FUNCTIONS' | tr ',' ' ') || status=1
  if ! coverage report >/dev/null; then
    echo '後端整體覆蓋率低於 85%' >&2
    status=1
  fi
  exit \$status
"
record coverage $? "$started"

# ---------------------------------------------------------------- 3. 端對端
if [ "$skip_e2e" -eq 1 ]; then
  step "3/3 端對端測試：本次略過（--skip-e2e）"
  layers_json="${layers_json}\"e2e\": {\"exit\": null, \"skipped\": true, \"seconds\": null},"
else
  step "3/3 端對端測試（Playwright）"
  started=$(date +%s)
  # test-results/ 是掛載回主機的資料夾；json 寫在這裡才拿得到
  docker compose --profile e2e run --rm -e PLAYWRIGHT_JSON_OUTPUT=test-results/playwright.json e2e
  record e2e $? "$started"
  cp frontend/test-results/playwright.json "$RAW/" 2>/dev/null
fi

# ---------------------------------------------------------------- 報告
step "產生測試報告"
commit=$(git rev-parse --short HEAD 2>/dev/null || echo "")
if [ -n "$commit" ] && [ -n "$(git status --porcelain 2>/dev/null)" ]; then
  commit="$commit（工作目錄有未提交的變更）"
fi
printf '{%s "commit": "%s"}\n' "$layers_json" "$commit" >"$RAW/layers.json"

docker compose cp "$RAW/." "backend:$WORK/" >/dev/null &&
  docker compose exec -T backend python scripts/build_test_report.py "$WORK" "$WORK/test-report.md" &&
  docker compose cp "backend:$WORK/." "$RAW/" >/dev/null
report_status=$?
if [ "$report_status" -ne 0 ]; then
  echo "產生測試報告失敗" >&2
  overall=1
else
  mv "$RAW/test-report.md" "$REPORTS/test-report.md"
  rm -rf "$REPORTS/coverage"
  mv "$RAW/coverage" "$REPORTS/coverage"
  echo
  echo "測試報告：$REPORTS/test-report.md"
  echo "覆蓋率 HTML：$REPORTS/coverage/index.html"
fi

if [ "$overall" -ne 0 ]; then
  echo "有測試或檢查沒有通過，詳見報告的〈各層結果〉。" >&2
fi
exit "$overall"
