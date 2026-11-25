---
title: '壓力與負載測試：觀眾輪詢、報到尖峰、報名尖峰、登入尖峰'
type: 'chore'
created: '2026-11-25'
status: 'done'
baseline_commit: '563db53'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/CLAUDE.md'
  - '{project-root}/README.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** A 文件 v1.2 曾經拿掉壓力測試，所以系統在多人同時使用時表現如何，目前沒有任何量測。NFR-2（一般 API 1 秒內）只量過單一使用者，NFR-1（200 筆同時報名不超收）只在測試程式裡用執行緒測過，沒有經過 HTTP 與真實伺服器設定。擁有者 11/25 決定趁進度有餘裕補做，結果要放進 F 測試報告。

**Approach:** 用 Locust 寫可重複執行的負載腳本，打本機 compose 起的完整系統。
- 先用種子腳本建立固定的測試資料。
- 分四個情境逐步加壓，找出 NFR-2 還成立的最大負載與系統的瓶頸。
- 每個情境跑完都檢查資料正確性：不超收、不重複報到、沒有 5xx。

## Boundaries & Constraints

**Always:**
- 定位是「補充量測」，不改 NFR，也不改 A／PRD 的承諾；說明文件要寫明這點，以及測試環境是單機 compose（寫出 CPU 核心數與可用記憶體），數字不代表正式環境。
- 只新增檔案，放在 `scripts/load/`：locustfile、種子腳本、執行腳本、`README.md`（怎麼跑＋本次結果表）。
  - 不改任何產品程式，也不改既有測試。
  - 如果發現效能 bug，記進 `deferred-work.md`，不在這裡修。
- Locust 用 `uv run --with locust==<固定版本>` 執行，不加進專案的依賴。產生的 HTML／CSV 報告輸出到 `scripts/load/reports/`，並加進 `.gitignore`。
- 種子資料要透過既有的 service 或示範資料函式建立，在 backend 容器內執行，例如 `docker compose exec backend python -m ...`。建立的帳號要有已知的測試密碼，並在 `scripts/load/README.md` 註明「僅供本機測試」。
- 輪詢頻率照前端實際的常數：
  - 對戰表與單場頁每 5 秒一次（`BRACKET_POLL_INTERVAL_MS`、`MATCH_POLL_INTERVAL_MS`）。
  - 未讀通知每 30 秒一次。
  - 下一場每 60 秒一次。
- 每個情境用階梯加壓。每一階至少 60 秒，記錄每階的 p50、p95、p99、RPS 與錯誤率，在 p95 超過 1 秒或錯誤率超過 1% 時停止。

**Never:**
- 不打任何非本機的主機。
- 不放進 CI。
- 不把報告檔、密碼以外的真實個資 commit 進 repo。
- 不為了數字好看而調整伺服器設定（worker 數、連線池）；預設值是什麼就量什麼，README 寫出當時的設定。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 觀眾輪詢 | 一場已抽籤、進行中的 32 隊賽事；觀眾依 5 秒輪詢公開對戰表與單場頁，人數階梯 50→100→200→400→… | 每階的 p95 與錯誤率；找出 p95 < 1 秒的最大人數 | 4xx／5xx 計入錯誤率並列出前幾名的錯誤內容 |
| 報到尖峰 | 16 場同時開放報到，32 位隊長在 1 秒內同時報到 | 全部成功、每隊恰好一筆報到紀錄、p95 | 事後用資料庫查詢核對筆數 |
| 報名尖峰 | 名額 N 的賽事，200 隊經 HTTP 同時報名 | 正取恰好 N 隊，其餘進候補或被拒；p95 | 事後核對正取數不超過名額 |
| 登入尖峰 | 50→100→200 個帳號同時登入（密碼雜湊很耗 CPU） | 每階的 p95；找出登入是否為瓶頸 | 401 以外的錯誤計入 |
| 混合情境 | 觀眾輪詢＋登入使用者輪詢通知與下一場，同時進行報到 | 在觀眾輪詢找到的上限附近跑 5 分鐘，看 p95 是否仍 < 1 秒 | 同上 |

</frozen-after-approval>

## Code Map

- `frontend/src/features/competition/use-bracket-polling.ts`、`use-match-polling.ts`、`next-match-queries.ts`、`frontend/src/features/notifications/queries.ts`：前端輪詢間隔與它們呼叫的 API。
- `frontend/src/client/sdk.gen.ts`：各 API 的實際路徑與方法。
- `backend/app/demo_data/`：示範資料（7.1），種子腳本可以參考或重用。
- `backend/tests/registration/test_nfr1_registration_report.py`、`backend/tests/competition/*_concurrency.py`：既有的併發測試，種子資料與核對方式可以參考。
- `backend/app/core/security.py`：密碼雜湊（argon2／bcrypt）。
- `compose.yml`、`README.md`：怎麼啟動、backend 的 worker 數與資料庫設定。
- `docs/midterm/A-軟體專案管理規劃文件.md:7`：v1.2 移除壓力測試的紀錄。PRD 的 NFR-1、NFR-2 在 `_bmad-output/planning-artifacts/prds/` 底下。

## Tasks & Acceptance

**Execution:**
- [x] `scripts/load/seed.py`（或放在 backend 內、可用 `python -m` 執行的模組）：建立四個情境需要的賽事、隊伍、帳號，可重複執行。
- [x] `scripts/load/locustfile.py`：五個情境各一個 User class 或 tag，可以用參數選擇。
- [x] `scripts/load/run.sh`：一鍵跑指定情境的階梯加壓，輸出到 `scripts/load/reports/`。
- [x] `scripts/load/verify.py`（或併入 seed）：跑完核對正確性，包括正取數、報到筆數、5xx。
- [x] 實際跑完五個情境，把結果表寫進 `scripts/load/README.md`，包括環境、設定、每階數字、上限、瓶頸觀察、正確性核對結果。
- [x] `.gitignore`：加入 `scripts/load/reports/`。
- [x] `deferred-work.md`：只有發現效能問題時才新增。

**Acceptance Criteria:**
- Given 乾淨的 compose 環境，when 照 `scripts/load/README.md` 的步驟執行，then 另一個人可以重現同一組情境並得到報告。
- Given 跑完所有情境，when 看 README 的結果表，then 每個情境都有實測數字與正確性核對結果，沒有估計值。

## Implementation Notes

- 與規劃不同的地方：
  - 觀眾階梯改為 25→50→…，登入另加 5～40 的補充階梯。
  - 種子資料改用 stdin 送進 backend 容器執行。
  - 為了不和其他 worktree 衝突，另加 `compose.load.yml`（專案名稱 `flow-load`、只綁本機）。
  - 另加 `summarize.py`、`host-sample.ps1`，記錄資源用量並判斷瓶頸。
- 「伺服器卡死不恢復」的初版結論經實測推翻：800 人壓垮後約 9 分鐘自己恢復。py-spy 看到 40 條 AnyIO 執行緒都卡在 `QueuePool._do_get`。
- 對照實驗（診斷用，未提交）：連線池放大到 40 沒有改善；執行緒池放大到 1000 後 RPS 從 1.5 升到 70，1 分鐘內恢復。根因確認為同步依賴與執行緒池互等。
- 縮小版 `run.sh all` 五個情境都實際跑過。registration 照舊出現 500，所以結束碼 1，屬預期。trap 只驗證了「Locust 被殺後會清掉取樣行程」，沒有驗證對整個行程群組按 Ctrl-C 的情況。

## Spec Change Log

## Review Triage Log

第 1 輪（Blind Hunter＝BH、Edge Case Hunter＝ECH、Verification Gap＝VG）：

| # | 來源 | 判定 | 證據／處理 |
|---|------|------|-----------|
| 1 | BH、ECH | medium → patch | 「只打本機」檢查用 `startswith`＋`assert`，且寫在 Locust 事件處理器裡（2.43 會吞掉例外只記 log），非本機主機仍會被打。改用 `urlparse` 精確比對 hostname，不符就 `runner.quit()` 並以非零結束。 |
| 2 | BH、ECH | medium → patch | `compose.load.yml` 的 backend 綁 0.0.0.0:18000，固定密碼的 432 個帳號對區網開放；改綁 127.0.0.1。 |
| 3 | BH、ECH | low → patch | `run.sh`：沒有 trap，中斷後取樣迴圈殘留；提早 return 沒恢復 `set -e`；種子 stderr 被丟掉；`_stages.csv` 一定有標題列，使「沒有結果」的檢查失效；login／viewer 不看 Locust 結束碼。 |
| 4 | BH、ECH | low → patch | `all` 沒跑 mixed，情境之間也沒有照 README 的建議重啟或等待恢復。 |
| 5 | BH、VG | low → patch | 文件不一致：取樣間隔（三處說法不同）、「可用記憶體」實為 FreePhysicalMemory、Email 網域、`MIX_VIEWERS` 預設值、GET 重試次數（docstring 一次，實際 total=2）。 |
| 6 | BH | low → patch | `verify.py` 把 200／32 寫死；改從 manifest 讀。 |
| 7 | BH、ECH | low → patch | 尖峰閘門逾時放行沒有紀錄；補記到齊人數與實際送出時間分布。 |
| 8 | ECH | low → patch | token 預載遇到連線錯誤就整個失敗、失敗後測試照跑；改為重試，失敗就停止並以非零結束。 |
| 9 | ECH | low → patch | 量測起點在預載之前，預載時間吃掉量測窗；改從預載完成後起算。報到情境加 `until_idle`。 |
| 10 | ECH | low → patch | `summarize.py` 跨 UTC 午夜與格式錯誤列會讓整份摘要失敗。 |
| 11 | BH | low → patch | 依賴 Locust 私有屬性 `_cp_last_run`：加上版本註記與屬性不存在時報錯。 |
| 12 | BH | low → patch | 登入結果表混用不同次執行，沒標來源；補上每列的執行時間。 |
| 13 | BH | medium → patch（診斷） | 根因（同步依賴與執行緒池互等）只有推論；做一次不提交的對照實驗驗證。 |
| 14 | BH | low → 處理於 PR 說明 | 報名尖峰 129 筆 500、約 9 分鐘無法服務，需要明確交給負責人決定；PR 說明點名 core 負責人，並列入 F 報告揭露。 |
| 15 | ECH | low → patch | compose `!override` 需要 Compose v2.24.4 以上，README 註明。 |
| 16 | ECH | low → reject | Docker VM 時鐘漂移超過 5 秒才會發生，日常少見。 |
| 17 | ECH | low → reject | 只跑 checkin／registration 時，也要先有示範賽事才能種子；README 已要求先載入示範資料。 |
| 18 | ECH | low → reject | `match_ids` 空陣列、沒有學校資料：種子腳本已先驗證示範賽事存在。 |
| 19 | BH | low → 主代理處理 | spec 狀態、Tasks 與 Implementation Notes 沒更新：由主代理收尾。 |

## Verification

**Commands:**
- `docker compose up -d --build --wait`（worktree 需要先從 `I:\大學課程\軟工\espory-platform\.env` 複製 `.env`）：結束碼 0。
- 種子腳本執行後，查資料庫確認賽事與帳號已建立：要有實際的查詢輸出。
- `bash scripts/load/run.sh <情境>`，五個情境各跑一次：每次都產生 CSV，並貼出每階的 p95 與錯誤率。
- 核對腳本：輸出「正取 = N ≤ 名額」「報到筆數 = 32」「5xx = 0」，或照實列出不符的地方。
- 收尾 `docker compose down -v`（確保種子資料不殘留），並刪除 worktree 裡的 `.env`。

**Manual checks:**
- 本機記憶體吃緊（約 5 GB 可用），Locust 和 compose 要一起跑；記錄當時的可用記憶體。如果是機器本身先撐不住，在 README 照實寫出來。
