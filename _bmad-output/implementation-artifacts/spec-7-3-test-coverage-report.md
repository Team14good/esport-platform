---
title: 'Story 7.3 測試覆蓋率與測試報告素材'
type: 'chore'
created: '2026-11-08'
status: 'in-review'
baseline_commit: '453b84764d3a0eb4987f4531783000e96bb5c732'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-7-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 目前三層測試要分開跑（後端 `scripts/test.sh`、前端 `bun run test:unit`、e2e 用 compose 的 `e2e` profile），覆蓋率沒有量分支，NFR-1 的「同時登錄同一場次」沒有測試，API 回應時間只有 e2e 的附件、沒有彙整，測試也沒有統一對應到 Story／FR。E 測試計畫與 F 測試報告沒有可以直接引用的素材。

**Approach:** 新增一支總指令腳本，依序跑單元、整合、端對端三層，最後產生一份繁中 Markdown 測試報告，內容包括各層結果、後端覆蓋率、純函式分支覆蓋率、NFR-1 併發比對、NFR-2 回應時間彙整，以及每個測試案例對應的 Story 與 FR。

## Boundaries & Constraints

**Always:**
- 測試一律連 compose 的 PostgreSQL 18（AD-16）。後端測試在 backend 容器裡執行。
- 分層與 Story／FR 對應的單一來源是一份對應檔：後端每個測試檔都要標層級（unit／integration）、Story、FR，並由測試檢查每個檔都有標。e2e 沿用 Playwright 既有的 `tag`（`@story-x.y`、`@FR-n`）。
- 純函式 `allocation.py`、`bracket.py`、`schedule.py`、`progression.py` 的分支覆蓋率要達 90% 以上，由 `scripts/test.sh` 強制，CI 因此也會檢查。
- 報告裡的數字只取自當次執行的輸出（junit、coverage json、Playwright json、計時檔），不寫死。

**Never:**
- 不修改其他組員的測試函式或 service 既有函式；只新增檔案。
- 不做壓力測試（PRD 已排除 Locust）。
- 產生的報告與覆蓋率 HTML 不 commit（放 `reports/`，加進 .gitignore）。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 全部通過 | `bash scripts/test-all.sh` | 依序跑三層；產出 `reports/test-report.md` 與 `reports/coverage/index.html`；結束碼 0 | N/A |
| 某層失敗 | 整合測試有失敗 | 其餘層照跑；報告標出失敗的案例；結束碼非 0 | 不中途停止 |
| 略過 e2e | `--skip-e2e` | 報告的 e2e 區塊註明「本次略過」 | N/A |
| 測試檔沒標註 | 新增的測試檔沒寫進對應檔 | 對應檔檢查測試失敗，訊息列出檔名 | N/A |
| 分支覆蓋率不足 | 四個純函式任一低於 90% | `scripts/test.sh` 失敗並列出檔案 | N/A |
| 同時登錄同一場次 | 多個執行緒同時對同一場次、同一局送出比分 | 只留一筆該局紀錄，沒有覆蓋或重複；報告列出送出數與實際筆數 | 其餘請求收到業務錯誤 |

## Decisions（2026-11-08 使用者決定）

- **標註粒度**：用集中對應檔，每個後端測試檔一列；報告列出每個案例，並帶上所在檔案的標註。不改任何人的測試檔。
- **NFR-1 的 200 筆報名**：7.3 自建 3.4 流程的情境（優先期內平行送出 200 筆 → 優先期結束分配 → 記錄正取數與名額）。#59 合併後，報告也會列出 C 的先搶期併發測試結果。
- **e2e**：總指令預設三層都跑，`--skip-e2e` 可以略過。
- **spec 長度**：約 2,500 token，保留完整，不拆開。

</frozen-after-approval>

## Code Map

- `backend/scripts/test.sh` -- 目前跑 `coverage run -m pytest tests/`，再做 report／html。這裡要加上分支覆蓋率的門檻檢查
- `backend/pyproject.toml:72-82` -- `[tool.coverage.run]` 沒有 `branch`、`fail_under=85`；`[tool.pytest.ini_options]`（`:66`）沒有註冊任何 marker
- `backend/tests/conftest.py:97-121` -- `client` fixture（A 的檔案）。在這裡掛 httpx event hook 記錄每次 API 的耗時，寫到計時檔
- `backend/tests/registration/test_submit_registration.py:889` -- 平行送出的寫法：`threading.Barrier` 加上各自的 `Session(engine)`、finally 清資料。只參考，不修改
- `backend/tests/registration/test_settlement_concurrency.py` -- 結算併發的寫法，可以參考
- `backend/app/modules/competition/service.py:1332` `record_game`、`:1304` -- 登錄比分前會 `lock_match`。併發測試走這支 API
- `backend/app/worker/jobs.py` -- 優先期結束分配的工作，選項 2A 要用
- `frontend/playwright.config.ts` -- reporter 目前是 list 加 html（CI 用 blob），要再加 json 輸出
- `frontend/tests/e2e/support/fixtures.ts:15-103` -- 已經記錄每次 API 的 `durationMs`，以附件 `api-timings.json` 掛在測試報告上
- `compose.yml:140-169` -- `e2e` 服務（profile `e2e`），會把 `playwright-report`、`test-results` 寫回本機
- `_bmad-output/planning-artifacts/prds/prd-se-final-project-2026-10-14/prd.md:580-581` -- NFR-1、NFR-2 的定義；FR 編號格式是 `FR-n`
- `deferred-work.md` 中「純函式 90% 分支覆蓋率 CI 沒有強制」那一項 -- 本 Story 完成後刪除

## Tasks & Acceptance

**Execution:**
- [x] `backend/tests/traceability.yaml`（新） -- 每個後端測試檔一列：`layer`、`stories`、`frs` -- 分層與追溯的單一來源
- [x] `backend/tests/conftest.py` -- 依對應檔替每個收集到的案例加上 `unit`／`integration` marker；`client` 記錄 API 耗時，寫到 `$TEST_TIMINGS_FILE`（有設才寫）
- [x] `backend/tests/test_traceability.py`（新） -- 檢查每個 `test_*.py` 都在對應檔裡、沒有多餘的列、Story 和 FR 的格式正確
- [x] `backend/pyproject.toml` -- 註冊兩個 marker；coverage 開 `branch = true`（整體低於 85% 時先停下來回報）
- [x] `backend/scripts/test.sh` -- 加上 `coverage report --include=<四個純函式> --fail-under=90`
- [x] `backend/tests/competition/test_score_concurrency.py`（新） -- 同時登錄同一場次同一局，斷言只有一筆紀錄，並記錄數字
- [x] `backend/tests/registration/test_nfr1_registration_report.py`（新） -- 200 筆平行送出並分配，記錄正取數與名額
- [x] `frontend/playwright.config.ts` -- 設了 `PLAYWRIGHT_JSON_OUTPUT` 時加上 json reporter
- [x] `scripts/test-all.sh`（新） -- 依序執行單元（前端 vitest、後端 `-m unit`）、整合（後端 `-m integration`，coverage 用 append）、e2e，任何一層失敗都繼續，最後產生報告
- [x] `backend/scripts/build_test_report.py`（新） -- 讀 junit、coverage json、Playwright json、計時檔與 NFR-1 記錄，輸出 `reports/test-report.md`
- [x] `.gitignore`、`README.md` -- 忽略 `reports/`；README 補上總指令的說明

**Acceptance Criteria:**
- Given compose 已啟動，when 執行 `bash scripts/test-all.sh`，then 報告依序列出三層的通過、失敗、略過數，後端整體覆蓋率，以及四個純函式的分支覆蓋率（都 ≥ 90%）。
- Given 報告，when 看 NFR-2 區塊，then 分開列出整合與 e2e 的 API 回應時間（筆數、P50、P95、最大值、超過 1 秒的端點）。
- Given 報告，when 看追溯區塊，then 每個測試案例都有 Story 與 FR，並附上依 Story 彙整的案例數。

## Verification

**Commands:**
- `docker compose exec -T backend bash scripts/test.sh` -- expected: 全部通過，整體 ≥ 85%，四個純函式的分支覆蓋率 ≥ 90%
- `bash scripts/test-all.sh --skip-e2e` -- expected: 結束碼 0，`reports/test-report.md` 有各個區塊
- `bash scripts/test-all.sh` -- expected: e2e 區塊有結果和回應時間

## Implementation Notes

- **同時登錄同一局不會收到業務錯誤**：依 5.3 的規則，局號不大於目前局數就是「覆寫」，所以 8 個同時登錄第 1 局的請求在 `lock_match` 下依序執行，第一個新增、其餘覆寫，全部成功。I/O 矩陣「其餘請求收到業務錯誤」對這個情境不成立；`test_score_concurrency.py` 改為斷言只留一筆、沒有唯一鍵衝突（500）、每次寫入各有一筆操作紀錄、勝局數與最後留下的那一局一致。另加一個「8 個請求同時送出系列結果」的情境：只有一個成功、其餘 7 個收到業務錯誤。兩個情境都把 `lock_match` 換成不加鎖的讀取後會失敗（已在容器內暫時修改驗證過）。是否要調整 I/O 矩陣的文字，請人決定。
- **200 筆報名的分配**：優先期結束時直接呼叫 `registration.service.settle_priority_window`，沒有走 `worker/jobs.allocate_priority_windows`；後者會挑測試資料庫裡所有到期的賽事（其他併發測試提交的資料），結果會受測試順序影響。200 隊各 1 人、分屬初始資料的 139 所學校，用 32 條連線送出。
- **併發測試留下的資料**：比照既有的併發測試，被操作紀錄參照的賽事與帳號刪不掉；兩支新測試結束時刪除隊伍、報名、結算、對戰表、場次、局、報到紀錄與新增的事件，並把賽事改為已取消，worker 工作不會再挑到。
- **純函式門檻**：`coverage report --fail-under` 判斷的是敘述加分支的合計，分支不足時可能被敘述拉高，所以新增 `backend/scripts/check_branch_coverage.py`，讀 `coverage json` 逐檔只看分支（AC 要的是分支覆蓋率）。清單寫在 `test.sh` 的 `PURE_FUNCTIONS`，`test-all.sh` 與報告都讀這份。
- **API 耗時**：記錄在 `tests/report_support.py`（`client` fixture 掛 httpx event hook），只有設了 `TEST_TIMINGS_FILE` 才寫檔；登入（`POST /api/v1/access-tokens`）和 e2e 一樣只記錄不判定 1 秒。
- **前端 Vitest 沒有逐案例標註**：spec 只要求後端對應檔與 e2e tag，報告的追溯區塊不含前端單元測試，只列結果數字。
- **test-all.sh 預設先 build**：容器是 build 時複製原始碼，預設 `docker compose up -d --build --wait`，`--no-build` 可略過。
- **#59 合併後**：C 的 `test_first_come_concurrency.py`、`test_first_come_submission.py` 要加進 `tests/traceability.yaml`，否則 `test_traceability.py` 會失敗；標上 `NFR-1` 後就會出現在報告的 NFR-1 區塊。
- `deferred-work.md` 刪除兩項（4.3 的 competition 純函式 90% 與 3.4 的 `AllocationPolicy` 90%），都由本 Story 的 `test.sh` 強制處理。
- **I/O 矩陣與實際行為的差異（凍結區塊未修改，待人決定是否調整文字）**：「同時登錄同一場次」一列寫「其餘請求收到業務錯誤」，這是寫 spec 時沒有查 5.3 規則的假設。實際上 8 個請求全部成功、依序覆寫，只留一筆（2026-11-08 實測：送出 8、成功 8、非預期錯誤 0、實際 1 筆）。使用者指示跑完沒問題就直接開 PR，所以測試維持實際行為，差異寫在這裡和 PR 說明。「其餘請求收到業務錯誤」只在「同時送出系列結果」成立（成功 1、業務錯誤 7）。
- **驗證方式**：
  - 2026-11-08 實跑 `scripts/test-all.sh`（含 e2e）一次：Vitest 831 通過、後端單元 791 通過、整合 1230 通過、e2e 12 通過 60 略過（13.7 分鐘）。略過的 60 個是 7.2 第三階段還沒接上的步驟。
  - 之後再跑 `--skip-e2e` 一次，結果相同；後端整體覆蓋率 97.0%（分支 95.6%），NFR-2 整合 P95 52 ms、e2e P95 109 ms，都沒有超過 1 秒的端點；200 筆報名：送出 200、資料庫 200 筆、正取 32、名額 32、候補 168。
  - 第二次的 Vitest 耗時 3512 秒，第一次含 e2e 全程也才約 16 分鐘，所以是當時機器的異常，不是測試本身；報告上的耗時是當次實測值。
  - 矩陣的「某層失敗」：以竄改的 junit 與結束碼餵報告腳本（報告列出失敗案例與結束碼），腳本流程沒有 `set -e`、`record` 累計結束碼（讀程式確認），沒有實際注入失敗跑過一次總指令。
  - 矩陣的「分支覆蓋率不足」：以竄改的 coverage json 測 `check_branch_coverage.py`（低於門檻與沒有資料都結束碼 1）。「測試檔沒標註」：暫時新增未登記的測試檔，`test_every_test_file_is_listed` 失敗。
- **其他 PR 要注意**：本 Story 合併後，新增後端測試檔都要加進 `tests/traceability.yaml`，否則 CI 失敗。#56、#57、#59 若有新增測試檔，合併 main 後要補一列。

## Spec Change Log

## Review Triage Log
