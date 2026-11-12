---
title: '修正 B 文件的使用案例圖（另存修訂版）'
type: 'chore'
created: '2026-11-12'
status: 'in-review'
route: 'dispatch'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 對照老師範例（去年第 2 組期末版）審查 `docs/midterm/` B 的 7 張使用案例圖，發現 14 個問題：參與者缺少一般化、「訪客／觀眾」同義詞、有條件的行為用 «include»、表單欄位被畫成使用案例、漏畫代登送出與申訴後晉級、通知類案例沒有接收者、圖 6 文字重疊、使用案例沒有功能編號，且缺少一張整體圖。

**Approach:** 以最新 `main` 的 B 為底，只把參、一使用案例圖另存成修訂版，新增仿老師範例的整體使用案例圖（功能群框）與圖例，依 FR 修正 7 張分圖，產生修訂版的 PNG、PDF、Word，交組員審核。

**Decisions（2026-11-12 使用者回覆「照推薦」）：**
- 未登入者：使用案例圖的參與者一律叫「訪客」（依權限命名）；A 的利害關係人與 B 的 User Story 保留「觀眾」（依目的命名）；B 壹、二第 6 項改為「訪客」並說明大多是來觀賽的觀眾，名詞定義補一行區分兩者。帳號也能使用訪客的使用案例（寫在圖例）。
- 「時間」保留，定義為系統外部的時間流逝（期限到達時自動觸發）；不是 worker（worker 在系統邊界內）。「發送站內通知與 Email」不連「時間」，只連接收通知的帳號（2026-11-12 使用者改採此方案）。
- 2.0 刪除「瀏覽賽事列表與賽事頁」，只留在 7.0（2026-11-12 使用者看過加回的版本後決定拿掉）。
- 關聯線一律不加文字標籤（7.0「接收」、5.0「代登」、4.0「報名截止＊」都拿掉；代登與自動抽籤的條件改寫在各功能群的說明文字）。
- 6.0「申訴逾期提醒」只連「時間」，不連主辦方（避免看起來像主辦方手動觸發）。
- 不畫參與者階層圖；整體圖仿老師範例，以功能群框放入全部使用案例，繼承關係寫在圖例文字（2026-11-12 使用者要求）。
- 不標示期中後完成的使用案例（2026-11-12 使用者改為不要＊）。
- 只有 7.0 的片段案例（搜尋隊伍晉級路徑、標為已讀）不標編號，避免 7.2、7.5 重複；其他圖的編號維持（2026-11-12 使用者更正）。
- 依 PR #84 黃鉅燊的審查（2026-11-12 使用者「照建議改」）：每個使用案例一個編號，功能拆成數個案例時加一碼（如 1.1.1），「賽事開始」為 2.2.3；整體圖只畫功能群框與參與者，7.0 排最上方。取代前面「只拿掉 7.0 片段編號」與「整體圖放入全部使用案例」的決定。
- 7.4 改名「接收站內通知與 Email」，從帳號的角度描述，避免看起來像帳號發起寄信。
- 使用者逐張看過圖後核准（2026-11-12「好收尾」）。
- **另存新檔，不改原檔**（2026-11-12 使用者要求）：修訂版只收錄參、一使用案例圖，存成 `B-使用案例圖修訂版.md`、`figures/B-usecase-v2-*`、`_build/usecase-v2.js`，以 `_build/build-v2.mjs` 排版；原本的 B、圖檔、`usecase.js`、`build.mjs`、README、PDF、Word 都不動。組員審核通過後再依 `docs/midterm/使用案例修訂說明.md` 取代原檔。

## Boundaries & Constraints

**Always:** 關係依 FR 判斷：每次都發生才用 «include»，有條件才發生用 «extend»；換行 LF；文件用繁體中文。

**Never:** 不改原本的 B、A、C、D、圖檔、`usecase.js`、`build.mjs`、README、PDF、Word；不改程式與 `_bmad-output/planning-artifacts/`；不 commit（除非使用者要求）。

</frozen-after-approval>

## Code Map

- `docs/midterm/_build/usecase-v2.js` -- 修訂版的畫圖程式（`usecase.js` 加上 `width`、`rowheight`、`package`、`uc ... at` 語法，關聯線接橢圓朝向參與者的一端，並含 #83 的標籤法線偏移）。
- `docs/midterm/_build/build-v2.mjs` -- `build.mjs` 的複本，只排修訂版、載入 `usecase-v2.js`。
- `docs/midterm/figures/src/B-usecase-v2-{1..7,overview}.usecase` -- 修訂版的圖原始碼。
- `docs/midterm/B-使用案例圖修訂版.md` -- 只含參、一使用案例圖的修訂版；B 其他章節要配合改的文字（使用者類型、名詞定義、版本紀錄）列在修訂說明第三節；`docs/midterm/使用案例修訂說明.md` -- 給組員的變動說明與取代步驟。

## Tasks & Acceptance

**Execution:**
- [x] 新增 `usecase-v2.js`、`build-v2.mjs`。
- [x] 新增整體圖與 7 張分圖的 v2 原始碼。
- [x] 修訂版文件：只含參、一（圖例、整體圖、各功能群的圖與說明）。
- [x] 新增 `使用案例修訂說明.md`。
- [x] 排版修訂版並逐張檢查 PNG；確認原檔沒有變動。

**Acceptance Criteria:**
- Given 修訂版完成，when 執行 `node docs/midterm/_build/build-v2.mjs`，then 沒有畫圖錯誤，產生修訂版 PDF、Word 與 8 張 v2 圖檔。
- Given 排版後，when 執行 `git status`，then 原有的追蹤檔案沒有任何修改，只有新增檔案。

## Implementation Notes

- 第一版曾直接修改原檔並新增參與者階層圖；使用者看過後要求拿掉階層圖、整體圖改仿老師範例，最後要求另存新檔不改原檔，因此把修改搬到 v2 檔案並把原檔還原；之後使用者再指定修訂版只收錄使用案例圖一節，刪除整份 B 的複本與泳道圖複本。
- 期間 `main` 合入 #83（簡化 B、C 圖面、`usecase.js` 標籤法線偏移、4.0 重排）。本分支已 fast-forward 到 #83，修訂版以新版 B 為底套用本次修改，並把 #83 的標籤偏移移植到 `usecase-v2.js`；4.0 採本次的排版。#83 已使用版本號 1.6、1.7，修訂版記為 1.8。
- 整體圖的彩色功能群框與兩欄排版不是本 session 產生的，是在工作期間由他人修改 `B-usecase-overview.usecase` 與 `usecase.js`；依使用者意願保留，只套用「時間」與主辦方連線的修改。
- 尚未執行正式的 `bmad-code-review`；審核交由組員進行。

## Verification

**Commands:**
- `node docs/midterm/_build/build-v2.mjs` -- 2026-11-12 執行結果：11 頁，含封面與目錄，產生 .docx，更新 8 張圖檔，無錯誤。
- `git status --short` -- 只有新增檔案，沒有 `M`。
