#! /usr/bin/env bash
# 重新產生前端 API client（frontend/src/client）。只需要 Docker，本機不必安裝 uv 或 bun：
#   1. 在 backend image 裡，以目前的 backend/app 匯出 OpenAPI 規格到 frontend/openapi.json
#   2. 在 frontend image（Bun 1.4）裡執行 openapi-ts 產生 client，再用 Biome 格式化
#   3. 把產生的 client 寫回 frontend/src/client
# 用法：bash scripts/generate-client.sh（在專案根目錄或任何位置執行皆可）

set -euo pipefail

# Git Bash（Windows）不要改寫傳給 docker 的 /app 路徑
export MSYS_NO_PATHCONV=1

cd "$(dirname "$0")/.."

tmp="$(mktemp -d)"
trap 'rm -rf -- "${tmp:?}"' EXIT

echo "==> Exporting OpenAPI schema from backend" >&2
# 先清掉 image 裡舊的 backend/app 再解開：tar 只會覆蓋與新增，主機上已刪除或改名的檔案
# 若留在 image 裡，舊的路由會被匯出到 OpenAPI，混進產生的 client
tar -cf - backend/app \
  | docker compose run --rm --no-deps -T backend bash -c '
      rm -rf /app/backend/app &&
      tar -xf - -C /app &&
      python -c "import json, app.main; print(json.dumps(app.main.app.openapi()))"
    ' > "$tmp/openapi.json"
cp "$tmp/openapi.json" frontend/openapi.json

echo "==> Generating client with openapi-ts and formatting with Biome" >&2
tar -cf - -C frontend openapi.json openapi-ts.config.ts biome.json \
  | docker compose run --rm --no-deps -T frontend sh -c '
      tar -xf - -C /app/frontend &&
      bun run generate-client >&2 &&
      bunx biome format --write src/client >&2 &&
      tar -cf - src/client
    ' > "$tmp/client.tar"

mkdir "$tmp/out"
tar -xf "$tmp/client.tar" -C "$tmp/out"
rm -rf -- frontend/src/client
cp -R "$tmp/out/src/client" frontend/src/client

echo "==> frontend/src/client regenerated" >&2
