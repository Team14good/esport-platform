---
title: 'Story 5.7 勝隊上傳結算截圖'
type: 'feature'
created: '2026-11-20'
status: 'done'
baseline_commit: '1df1cbe7c8bd97f7d17edbf05cf1328d8d3d58af'
route: 'dispatch'
review_loop_iteration: 1
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-5-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 系列結果送出後，場次頁只有裁判登錄的比分，沒有遊戲結算畫面可以對照；發生爭議時主辦方與觀眾無圖可查（FR-28、FR-36）。

**Approach:** competition 新增 `result_screenshot` 資料表與三支 API（勝隊隊長上傳／更換、公開下載、登入者能否上傳），圖片沿用 `core.storage.save_image`（JPG／PNG、5 MB，與段位截圖同一套驗證）。S4 左欄各局列表下方新增「結算截圖」Card：送出後所有人可見，勝隊隊長在同位置看到 Screenshot uploader。

## Boundaries & Constraints

**Always:**
- 依 epics.md Story 5.7 的原始驗收條件實作（期末 Story，不套用期中簡化）。
- 「系列結果已送出」＝場次 `outcome = played` 且 `submitted_at` 有值（申訴期、申訴中、已確認皆是）。
- 只有目前勝隊（`match.winner_id`）的隊長能上傳；上傳、更換、未上傳都不改場次狀態、期限與晉級，`confirm_match`／`auto_confirm_expired` 不讀這張表。
- 公開 API 不回傳檔案鍵值（AD-19），只回傳是否顯示區塊與上傳時間；圖片經 API 串流下載（AD-15：結算截圖公開）。
- 寫入先 `lock_match` 再檢查；檔案在所有檢查通過後才存；交易失敗刪新檔，提交後才刪舊檔（與段位截圖相同）。
- 前端只用產生的 client（圖片以 blob 下載後轉 object URL），不手寫 fetch、不直接把 API 網址放進 `<img src>`。
- 上傳寫 `audit.record`（`match.result_screenshot_uploaded`）並更新 `match.updated_at`，讓 5 秒輪詢的觀眾看到新圖。

**Never:**
- 不發通知事件（驗收條件沒有通知）；不改 `transition_match`、確認與晉級流程。
- 不改 B 的 `appeals.py`、disputes 模組既有函式；不改 `ScreenshotUploader` 既有行為（只重用）。
- 不把截圖放進示範資料（7.1）；不做刪除截圖（驗收條件只有上傳與更換）。

## Decisions

黃鉅燊於 2026-11-20 核准以下全部決定（經協調代理轉達；四個待決事項都採提案選項）：

1. **可上傳的期間**：系列結果送出後就能上傳與更換，沒有截止時間（已確認、賽事結束後仍可更換）。驗收條件只寫「之後可以更換」，沒有寫期限。
2. **判棄權、輪空、取消資格判負的場次**：沒有「送出系列結果」，不顯示「結算截圖」區塊，也不能上傳（409 `RESULT_NOT_SUBMITTED`）。
3. **勝隊因申訴更正而換人**：截圖只在「上傳的隊伍＝目前勝隊，且上傳時間不早於這次送出結果的時間」時才公開。更正後原勝隊的截圖不再顯示，區塊回到「勝隊尚未上傳結算截圖」，新勝隊隊長可上傳（覆蓋舊列，舊檔在提交後刪除）。
4. **主辦方處理申訴（S32）**：這次不改 B 的 S32 頁面；主辦方在公開的 S4 看結算截圖。「S32 加『查看場次頁』連結」記進 `deferred-work.md`，留給 B。
5. **上傳操作**：選檔後先顯示本機預覽，按「上傳截圖」（已有截圖時為「更換截圖」）才送出；上傳中顯示進度。
6. **登入要求**：上傳需 Email 已驗證（`VerifiedAccount`，與其他上傳一致）；隊長本來就都已驗證。
7. **資料表**比 B 文件（十八）多 `team_id`、`uploaded_by` 兩欄（決定 3 與操作紀錄需要）；B 文件由組長維護，PR 說明提醒同步。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 勝隊隊長首次上傳 | 申訴期、PNG ≤ 5 MB | 200；公開單場 `result_screenshot_at` 有值；公開下載回 200 `image/png` | N/A |
| 更換 | 已有截圖，再上傳 JPG | 200；下載回新圖；舊檔被刪；資料表仍只有一列 | N/A |
| 敗隊隊長、隊員、裁判、主辦方、其他帳號 | 已送出 | 不寫資料、不留檔案 | 403 `WINNING_CAPTAIN_REQUIRED` |
| 未登入 | — | — | 401 |
| 結果尚未送出／判棄權／輪空 | `outcome != played` 或無 `submitted_at` | 不寫資料 | 409 `RESULT_NOT_SUBMITTED` |
| 格式不符、檔頭不符 | GIF、宣告 PNG 實為文字 | 不寫資料、不留檔案 | 415 `UNSUPPORTED_FILE_TYPE` |
| 超過 5 MB | 5 MB＋1 byte | 同上 | 413 `FILE_TOO_LARGE` |
| 場次不屬於該賽事 | — | — | 404 `MATCH_NOT_FOUND` |
| 沒有可公開的截圖時下載 | 未上傳、或決定 3 的隱藏情況 | — | 404 `RESULT_SCREENSHOT_NOT_FOUND` |
| 沒上傳就期滿 | 申訴期滿、無截圖 | `auto_confirm_expired` 照常確認並晉級 | N/A |
| 更正結果換勝隊 | 原勝隊已上傳 → `correct_result` 改判 | 截圖不再公開；新勝隊隊長可上傳，原勝隊隊長 403 | N/A |

</frozen-after-approval>

## Code Map

- `backend/app/core/storage.py` -- `save_image`／`open_file`／`delete_file`；直接重用，不改。
- `backend/app/modules/registration/service.py:654 update_player_profile`、`router.py:60` -- 段位截圖的存檔與新舊檔清理範式（service 失敗刪新檔；router 提交失敗刪新檔、提交後刪舊檔）。
- `backend/app/modules/disputes/router.py:196 download_appeal_attachment`、`service.py:586` -- `StreamingResponse` 下載與副檔名→media type 的寫法（結算截圖改 `inline`、可快取）。
- `backend/app/modules/competition/models.py` -- 新增 `ResultScreenshot` 表、`ResultScreenshotState`；`PublicMatchDetail` 加 `result_screenshot_enabled: bool`、`result_screenshot_at: datetime | None`。
- `backend/app/modules/competition/service.py` -- `get_public_match`（:539）帶入新欄位；`_match_in_tournament`、`lock_match`、`registration_port.is_captain`、`repository.touch_match` 重用；`_SUBMITTED` 狀態集合。新邏輯放新檔 `result_screenshot.py`，`service.py` 只加薄的公開函式（比照 `appeals.py`）。
- `backend/app/modules/competition/router.py` -- 新增三個端點。
- `backend/app/alembic/versions/` -- 目前 head `f2b6d8a1c3e5`；PR #95（4.2）也接在同一個 head，後合併者要改 `down_revision`。
- `backend/tests/competition/test_score_entry.py` -- `Setup`（8 隊、M1 已報到、主辦方記分）可沿用來做「已送出」的場次；`tests/traceability.yaml` 要加新測試檔。
- `frontend/src/features/registration/ScreenshotUploader.tsx`、`screenshot-file.ts` -- 重用（disputes 已有跨 feature 匯入的先例）。
- `frontend/src/features/competition/MatchSpectatorView.tsx` -- 左欄加 `resultScreenshot` 插槽（各局列表／比分登錄面板之後；`< lg` 排在各局列表之後、同輪其他場次之前）。
- `frontend/src/routes/tournaments/$tournamentId/matches/$matchId.tsx` -- 傳入插槽；`refresh` 重抓。
- `frontend/src/features/disputes/queries.ts` -- 以 `matchQueryKey`＋`matchVersion` 組 key、`onUploadProgress` 的範式。

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/modules/competition/models.py` -- 新增 `ResultScreenshot`（`match_id` UNIQUE FK、`team_id`、`file_key`、`uploaded_by` FK、`created_at`）、`ResultScreenshotState(can_upload, reason)`、`PublicMatchDetail` 兩個欄位
- [x] `backend/app/alembic/versions/<rev>_story_5_7_result_screenshot.py` -- 建表，`down_revision = "f2b6d8a1c3e5"`
- [x] `backend/app/modules/competition/repository.py` -- `get_result_screenshot`、`save_result_screenshot`（新增或覆寫）
- [x] `backend/app/modules/competition/result_screenshot.py` -- 共用檢查 `evaluate`（已送出 → 勝隊隊長）、`upload`、`open_public`、`get_state`、`visible_at`（決定 3 的公開規則）
- [x] `backend/app/modules/competition/service.py` -- 公開函式 `upload_result_screenshot`、`open_result_screenshot`、`get_result_screenshot_state`；`get_public_match` 帶入新欄位
- [x] `backend/app/modules/competition/router.py` -- `PUT …/matches/{id}/result-screenshot`（multipart `screenshot`，`VerifiedAccount`）、`GET …/result-screenshot`（公開、`inline`）、`GET …/result-screenshot-state`（`CurrentAccount`）
- [x] `backend/tests/competition/test_result_screenshot.py`、`tests/traceability.yaml` -- 涵蓋 I/O 表每一列，含期滿自動確認與更正換勝隊
- [x] `frontend/src/client/` -- `bash scripts/generate-client.sh` 重新產生
- [x] `frontend/src/features/competition/ResultScreenshotCard.tsx`、`MatchResultScreenshot.tsx`、`result-screenshot-queries.ts` -- Card（縮圖最大寬 320px、點擊開 `Dialog`、未上傳文字、勝隊隊長的 uploader 與按鈕）
- [x] `frontend/src/features/competition/MatchSpectatorView.tsx`、`routes/…/matches/$matchId.tsx` -- 接上插槽
- [x] `frontend/tests/unit/result-screenshot.test.tsx`、`tests/e2e/` -- 元件各狀態；e2e 走真 API：勝隊隊長上傳 → 未登入觀眾看到縮圖並放大，desktop 與 mobile-375
- [x] `docs/ai-usage/D-黃鉅燊.md`、`sprint-status.yaml` -- 紀錄；5-7 改 `in-progress`

**Acceptance Criteria:**
- Given 系列結果已送出的場次，when 任何人（含未登入）開啟 S4，then 左欄各局列表下方出現「結算截圖」Card；未上傳時顯示「勝隊尚未上傳結算截圖」，已上傳時顯示最大寬 320px 的縮圖，點擊以 Dialog 放大
- Given 尚未送出系列結果（待開打、進行中）或判棄權的場次，when 開啟 S4，then 不顯示這個區塊
- Given 勝隊隊長，when 開啟已送出的場次，then 在同一張 Card 看到 Screenshot uploader；上傳成功後 5 秒內其他觀眾的頁面出現縮圖；可再次更換
- Given 敗隊隊長、裁判、主辦方或觀眾，when 開啟同一頁，then 看不到 uploader
- Given 375px 寬，when 開啟 S4，then Card 排在各局列表之後、同輪其他場次之前，頁面沒有水平捲動

## Implementation Notes

- 公開單場的布林欄位原本叫 `result_submitted`，既有測試 `test_public_match_hides_submitter`（5.4）以「回應文字不含 submitted」確認不透露送出者，因此改名為 `result_screenshot_enabled`；不改那個測試。
- `tests/competition/test_match_api.py` 的 `DETAIL_KEYS` 補上兩個新欄位（公開單場的欄位清單是白名單斷言，新增欄位必須明列）。
- 圖片查詢的 key 不放在 `matchQueryKey` 前綴底下（審查發現：S4 的 `refresh` 會讓圖片跟著重新下載）。
- 上傳時在場次鎖住的期間寫入圖片檔（最多 5 MB）：沿用報到的單一場次鎖，檔案已由 FastAPI 暫存在本機，維持現狀。

## Spec Change Log

## Review Triage Log

第 1 輪（2026-11-20，一個只拿到 diff 與期望結果的審查子代理，靜態閱讀）：

| # | 發現 | 判定 | 處理 |
|---|---|---|---|
| 1 | 圖片查詢的 key 在 `matchQueryKey` 前綴下，S4 每次 `refresh` 都重新下載圖片 | medium | 已修：key 移出前綴，補兩個單元測試（invalidate 不重抓、上傳時間改變才重抓） |
| 2 | router 提交失敗時「刪新檔、留舊檔」沒有測試 | medium | 已補 `test_commit_failure_on_replace_keeps_the_old_file_and_row` |
| 3 | 「看不到上傳區」的斷言在狀態回應處理前就執行（單元與 e2e） | medium | 已修：單元測試等回應處理完；e2e 等 `result-screenshot-state` 回應並斷言內容 |
| 4 | 已送出後被取消資格判負（`submitted_at` 仍有值）沒有測試 | low | 已補 `test_disqualified_after_submission_hides_the_screenshot_and_blocks_upload` |
| 5 | 場次鎖住期間寫入圖片檔 | low | 不改，理由見 Implementation Notes |
| 6 | 狀態查詢不含 Email 驗證，與 docstring 的「若且唯若」不符 | low | 已改 docstring（隊長建隊時都已驗證） |
| 7 | registration 未就緒時 503 訊息寫「報到」 | low | 不改（只在子系統缺函式時出現，文字問題） |

## Design Notes

- 公開規則（決定 3）集中在 `result_screenshot.visible_at(match, row)`：`outcome == played`、`submitted_at` 有值、`row.team_id == match.winner_id`、`row.created_at >= match.submitted_at`。最後一項讓「重新比賽後殘留的舊列」不會被當成新結果的截圖，不必去改 `clear_for_replay`。
- 檢查順序：404 → `lock_match` → 已送出（409）→ 勝隊隊長（403）→ 存檔。未送出時沒有勝隊，所以 409 在 403 之前。只鎖場次（與報到相同），和 `correct_result` 的場次鎖互斥。
- 圖片回應 `Cache-Control: public, max-age=31536000, immutable` 不可行（同一網址內容會換）；改用 `no-cache`＋前端 query key 帶 `result_screenshot_at`，換圖後重抓。

## Verification

**Commands:**
- `docker compose run --rm backend pytest tests/competition tests/registration tests/test_architecture.py tests/test_migrations.py tests/test_traceability.py tests/test_auth_required.py` -- expected: 全數通過
- `bash scripts/lint.sh`（或 README 的 ruff／mypy 指令）-- expected: 無錯誤
- `bun run typecheck && bunx biome check && bun run test:unit`（frontend）-- expected: 全數通過
- `docker compose --profile e2e run --rm e2e`（結算截圖的 spec，desktop＋mobile-375）-- expected: 通過
- 變異檢查：拿掉勝隊隊長判斷 → `test_result_screenshot.py` 至少一個案例失敗 → 還原
