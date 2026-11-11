---
title: '期中文件 A～D 依實作同步'
type: 'chore'
created: '2026-11-11'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `docs/midterm/` 的 A～D 停在 2026-10-28，當時只完成 Story 1.1～1.5；現在第一批 35 個 Story 已完成（`main` 的 `6d2c5a7`），類別圖、資料表、API、時程都和程式不一致，期中報告（11/18）要交。

**Approach:** 以程式碼與各 spec 的 Decisions 為準修正四份 Markdown，新增版本紀錄，再重新產生 PDF 與 Word。

**Decisions（2026-11-11 使用者授權「按照最推薦的方式」）：**
- 文件仍描述完整設計：已實作的部分與程式一致；擱置的 15 個 Story（1.6、2.3、2.5、2.6、2.8、3.7～3.11、4.2、4.5、4.7、5.7、6.3）的需求保留並標示「期中後」，不刪除。
- D 的類別圖只畫目前存在的類別與公開函式，期中後才有的集中列在貳、九。
- A 的角色分工表以組員 10/28 手動修改的版本為準，不改動；另補實作階段依模組的分工。
- 從最新 `main` 開 `docs/midterm-sync`；不 commit。

## Boundaries & Constraints

**Always:** 數字與名稱只取自程式、`sprint-status.yaml`、spec；介面與文件用繁體中文；換行 LF。

**Never:** 不改程式與 `_bmad-output/planning-artifacts/`；不在文件寫尚未實作卻宣稱完成的內容；不把擱置 Story 的需求刪掉。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 已實作的資料表 | 例如 MATCH | 欄位與 `models.py` 相同 | N/A |
| 擱置的資料表 | ROUND_SETTING、RESULT_SCREENSHOT、NOTIFICATION | 保留說明並標示期中後 | N/A |
| 重新排版 | `node docs/midterm/_build/build.mjs` | 四份 PDF 與 Word 都更新，沒有畫圖錯誤 | 有錯誤時修 Markdown 後重跑 |

</frozen-after-approval>

## Code Map

- `backend/app/modules/*/models.py`、`service.py`、`router.py`、`worker/jobs.py`、`core/*`：欄位、函式、API、定時工作的依據。
- `_bmad-output/implementation-artifacts/sprint-status.yaml`、`spec-*.md` 的 Decisions、`epics.md`〈期中範圍〉：進度與定案規則。
- `docs/midterm/{A,B,C,D}-*.md`、`docs/midterm/README.md`：修改對象；`docs/midterm/_build/build.mjs`：排版。

## Tasks & Acceptance

- [x] `docs/midterm/D-物件設計文件.md`：類別圖、職責、協作、列舉依程式更新，新增貳、九。
- [x] `docs/midterm/C-軟體設計文件.md`：模組資料、worker、API 表、權限與事件說明依程式更新。
- [x] `docs/midterm/B-軟體需求分析文件.md`：新增期中範圍、ERD 與資料表依程式更新、補各 Story 定案的規則。
- [x] `docs/midterm/A-軟體專案管理規劃文件.md`：進度、里程碑、甘特圖、實作分工更新。
- [x] `docs/midterm/README.md`：新增本次修訂紀錄。
- [x] 執行排版並檢查輸出。

**AC:** Given 四份 Markdown 更新完成，When 執行 `node docs/midterm/_build/build.mjs`，Then 四份 PDF、Word 重新產生且沒有畫圖錯誤。

## Spec Change Log
