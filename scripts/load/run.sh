#!/usr/bin/env bash
# 壓力與負載測試的一鍵執行：建立種子資料 -> 階梯加壓 -> 核對正確性。僅供本機測試，只打本機 compose。
#
# 用法（在 repo 根目錄）：
#   bash scripts/load/run.sh <viewer|checkin|registration|login|mixed|all>
#
# 前置：compose 專案已啟動（見 scripts/load/README.md），且 DEMO_PASSWORD 已設定、示範資料已載入。
# 環境變數：
#   LOAD_PROJECT   compose 專案名稱（預設 flow-load）
#   LOAD_PORT      backend 對外埠號（預設 18000，見 scripts/load/compose.load.yml，只綁 127.0.0.1）
#   STAGES         viewer、login 的人數階梯（逗號分隔；預設 viewer 25,50,75,100,150,200,400,800,1600,3200、login 50,100,200）
#   MEASURE_SECONDS viewer、login 每階量測秒數（預設 60）
#   MIX_VIEWERS    mixed 的觀眾人數（預設 75，已知不會壓垮；與 locustfile.py、README 一致）
#   MIX_POLLERS    mixed 的登入輪詢人數（預設 50）
#   MIX_SECONDS    mixed 的量測秒數（預設 300）
# 輸出在 scripts/load/reports/（已加進 .gitignore）：<情境>-<時間>_stages.csv、_endpoints.csv、_summary.json、_resources.csv、
# _seed.log、_locust.log、Locust 自己的 _stats.csv／_failures.csv／.html，與資源取樣 _docker.csv、_host.csv。
# 結束碼 0 代表：Locust 正常結束、正確性核對通過、5xx 為 0；任何一項不符就是 1（階梯找上限時最後一階失敗，結束碼為 1 是預期）。
set -euo pipefail
cd "$(dirname "$0")/../.."

SCENARIO="${1:?用法：bash scripts/load/run.sh <viewer|checkin|registration|login|mixed|all>}"
PROJECT="${LOAD_PROJECT:-flow-load}"
PORT="${LOAD_PORT:-18000}"
BASE="http://127.0.0.1:$PORT"
LOCUST_VERSION="2.43.3"
REPORTS=scripts/load/reports
mkdir -p "$REPORTS"

compose() { docker compose -p "$PROJECT" -f compose.yml -f scripts/load/compose.load.yml "$@"; }
# 在 backend 容器內執行 repo 裡的腳本（用 stdin 送入，不必改 image）
in_backend() { local script="$1"; shift; compose exec -T backend python - "$@" < "scripts/load/$script"; }
json_get() { python -c "import json,sys;print(json.load(open(sys.argv[1]))[sys.argv[2]])" "$1" "$2"; }

SAMPLER_PIDS=()
# 結束背景取樣（迴圈的子行程一併結束，避免殘留 docker／powershell）；EXIT、INT、TERM 都會呼叫
stop_samplers() {
  local pid
  for pid in "${SAMPLER_PIDS[@]:-}"; do
    [ -n "$pid" ] || continue
    pkill -P "$pid" 2>/dev/null || true
    kill "$pid" 2>/dev/null || true
  done
  SAMPLER_PIDS=()
}
trap stop_samplers EXIT INT TERM

# seed <指令> <輸出的 manifest>：stderr 存到 SEED_LOG；失敗或 manifest 不是合法 JSON 就印出 log 並回傳 1
seed() {
  local out
  if ! out="$(in_backend seed.py "$1" 2>>"$SEED_LOG")"; then
    echo "種子資料（$1）失敗，log 如下（$SEED_LOG）：" >&2; tail -n 30 "$SEED_LOG" >&2; return 1
  fi
  printf '%s\n' "$out" | tail -n 1 > "$2"
  if ! python -c "import json,sys;json.load(open(sys.argv[1], encoding='utf-8'))" "$2" 2>/dev/null; then
    echo "種子資料（$1）的輸出不是合法 JSON（$2）；log 如下（$SEED_LOG）：" >&2; tail -n 30 "$SEED_LOG" >&2; return 1
  fi
}

# 重啟 backend／worker，等 health-check 與一次公開對戰表都回 200 才繼續（被壓垮後的積壓請求要約 10 分鐘才消化完，
# 不重啟會污染下一個情境）
restart_and_wait() {
  compose restart backend worker >/dev/null
  local i
  for i in $(seq 1 60); do
    curl -sf -o /dev/null "$BASE/api/v1/utils/health-check" && break
    sleep 2
  done
  SEED_LOG="$REPORTS/restart-$(date +%Y%m%d-%H%M%S)_seed.log"
  local tmp="$REPORTS/restart-manifest.json" tid
  seed base "$tmp"
  tid="$(json_get "$tmp" tournament_id)"
  for i in $(seq 1 60); do
    [ "$(curl -s -o /dev/null -w '%{http_code}' "$BASE/api/v1/tournaments/$tid/bracket")" = 200 ] && return 0
    sleep 2
  done
  echo "重啟後 120 秒內公開對戰表沒有回 200" >&2; return 1
}

run_one() {
  local scenario="$1" stamp prefix
  stamp="$(date +%Y%m%d-%H%M%S)"
  prefix="$REPORTS/$scenario-$stamp"
  SEED_LOG="${prefix}_seed.log"
  echo "=== 情境 $scenario（輸出前綴 $prefix）"

  {
    echo "date: $(date -u +%FT%TZ)"
    echo "cpu_cores_host: ${NUMBER_OF_PROCESSORS:-unknown}"
    # 可用記憶體是 Available MBytes（含待命快取），不是 FreePhysicalMemory
    powershell -NoProfile -Command '$m=(Get-CimInstance Win32_PerfFormattedData_PerfOS_Memory).AvailableMBytes; $t=[int]((Get-CimInstance Win32_OperatingSystem).TotalVisibleMemorySize/1024); "host_available_mb: $m total_mb: $t"' 2>/dev/null || true
    docker info --format 'docker_ncpu: {{.NCPU}} docker_mem_bytes: {{.MemTotal}}' 2>/dev/null || true
  } | tee "${prefix}_env.txt"

  local manifest="${prefix}_manifest.json" checkin_manifest="" classes="" tid="" verify="" expected=""
  seed base "$manifest" || return 1
  case "$scenario" in
    viewer) classes="ViewerUser" ;;
    login) classes="LoginUser" ;;
    checkin|mixed)
      seed checkin "${prefix}_manifest-checkin.json" || return 1
      tid="$(json_get "${prefix}_manifest-checkin.json" tournament_id)"
      expected="$(python -c "import json,sys;print(len(json.load(open(sys.argv[1]))['captains']))" "${prefix}_manifest-checkin.json")"
      local wait_s
      wait_s="$(python -c "
import json,sys,datetime as d
m=json.load(open(sys.argv[1]));o=d.datetime.fromisoformat(m['opens_at'])
print(max(0,int((o-d.datetime.now(d.timezone.utc)).total_seconds())+5))" "${prefix}_manifest-checkin.json")"
      echo "報到於 ${wait_s} 秒後開放，等待中"; sleep "$wait_s"
      if [ "$scenario" = checkin ]; then
        classes="CheckinUser"; manifest="${prefix}_manifest-checkin.json"
      else
        classes="ViewerMixedUser PollerMixedUser CheckinMixedUser"; checkin_manifest="${prefix}_manifest-checkin.json"
      fi
      verify="checkin" ;;
    registration)
      seed registration "${prefix}_manifest-registration.json" || return 1
      manifest="${prefix}_manifest-registration.json"
      tid="$(json_get "$manifest" tournament_id)"
      expected="$(python -c "import json,sys;print(len(json.load(open(sys.argv[1]))['teams']))" "$manifest")"
      classes="RegistrationUser"; verify="registration" ;;
    *) echo "未知的情境：$scenario" >&2; return 2 ;;
  esac

  # 資源取樣：每一輪 docker stats --no-stream（本身約 2 秒）加 sleep 3，實際約每 5 秒一筆；主機取樣每輪 PowerShell
  # 約 2.5 秒加 sleep 2，實際也約每 5 秒一筆。主機整機 CPU% 與可用記憶體用 CIM（不用 Get-Counter：Windows PowerShell 5.1
  # 在這台沒有該模組）。用迴圈而不是串流，結束時殺掉迴圈就不會留下背景的 docker／powershell 行程。
  # shellcheck disable=SC2046
  ( while true; do
      ts="$(date -u +%H:%M:%S)"
      docker stats --no-stream --format '{{.Name}},{{.CPUPerc}},{{.MemUsage}}' $(compose ps -q) 2>/dev/null | sed "s/^/$ts,/" >> "${prefix}_docker.csv"
      sleep 3
    done ) &
  SAMPLER_PIDS+=("$!")
  ( while true; do
      ts="$(date -u +%H:%M:%S)"
      powershell -NoProfile -ExecutionPolicy Bypass -File scripts/load/host-sample.ps1 2>/dev/null | tr -d '\r' | sed "s/^/$ts,/" >> "${prefix}_host.csv"
      sleep 2
    done ) &
  SAMPLER_PIDS+=("$!")
  local since; since="$(date -u +%FT%TZ)"

  local locust_rc
  set +e
  # shellcheck disable=SC2086
  SCENARIO="$scenario" OUT_PREFIX="$prefix" MANIFEST="$manifest" MANIFEST_CHECKIN="$checkin_manifest" \
  MIX_VIEWERS="${MIX_VIEWERS:-75}" MIX_POLLERS="${MIX_POLLERS:-50}" MIX_SECONDS="${MIX_SECONDS:-300}" \
  PYTHONUTF8=1 \
    uv run --no-project --with "locust==$LOCUST_VERSION" locust -f scripts/load/locustfile.py \
      --headless --host "$BASE" --csv "$prefix" --html "$prefix.html" \
      --only-summary $classes 2>&1 | tee "${prefix}_locust.log"
  locust_rc=${PIPESTATUS[0]}
  set -e
  stop_samplers

  # 沒有結果：_stages.csv 至少要有表頭加一列資料，且有 _summary.json
  if [ "$(wc -l < "${prefix}_stages.csv" 2>/dev/null || echo 0)" -lt 2 ] || [ ! -f "${prefix}_summary.json" ]; then
    echo "Locust 沒有產生結果（結束碼 $locust_rc）" >&2; return 1
  fi

  echo "--- 各階結果（${prefix}_stages.csv）"
  cat "${prefix}_stages.csv"

  echo "--- 各階資源（backend／db 的 CPU 峰值、主機 CPU 與可用記憶體）"
  python scripts/load/summarize.py "$prefix" || true

  echo "--- 正確性核對"
  local rc=0
  if [ -n "$verify" ]; then
    in_backend verify.py "$verify" "$tid" "$expected" 2>>"$SEED_LOG" || rc=$?
  fi
  local n5xx_locust n5xx_log
  n5xx_locust="$(json_get "${prefix}_summary.json" http_5xx)"
  n5xx_log="$(compose logs --since "$since" backend 2>/dev/null | grep -cE 'HTTP/1\.[01]" 5[0-9][0-9]' || true)"
  echo "5xx（Locust 收到的回應）= $n5xx_locust；5xx（backend access log）= $n5xx_log"
  if [ "$n5xx_locust" != 0 ] || [ "$n5xx_log" != 0 ]; then rc=1; fi
  if [ "$locust_rc" != 0 ]; then rc=1; fi
  echo "locust 結束碼 $locust_rc；核對結束碼 $rc"
  return $rc
}

if [ "$SCENARIO" = all ]; then
  status=0
  for s in viewer checkin registration login mixed; do
    restart_and_wait || { status=1; continue; }
    run_one "$s" || status=1
  done
  exit $status
fi
run_one "$SCENARIO"
