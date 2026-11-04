---
title: 'Story 7.1（第二階段）：示範資料的 tournaments 步驟'
type: 'feature'
created: '2026-11-04'
status: 'done'
baseline_commit: 'f831e28e9a68fc4266bdd76bb5127e95e1d2110b'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-7-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** D 的 competition 步驟（PR #36）會替 `context.tournament_to_draw` 指定的賽事抽籤，但目前沒有步驟建立遊戲與賽事，也沒有人寫入這個欄位，啟動時只記錄「No demo tournament to draw」並略過。

**Approach:** 新增 tournaments 步驟：透過 tournaments 的公開 service 建立《英雄聯盟》（`win_loss`）、《特戰英豪》（`rounds`）兩款遊戲與段位對照表，以及一場 32 隊、校園賽的《特戰英豪》示範賽事（不放直播連結，見 Decisions），把賽事 id 寫進 `context.tournament_to_draw`。

## Boundaries & Constraints

**Always:**
- 只呼叫 tournaments、identity `service.py` 的公開函式，不直接寫資料表；不 commit（由 `initial_data` 負責）。
- 可重複執行：遊戲依名稱、賽事依「主辦方＋名稱」判斷已存在就略過，不覆寫既有欄位；再次啟動仍把已存在的示範賽事 id 寫進 `context.tournament_to_draw`。
- 賽事的主辦方是 `context.accounts["organizer"]`；遊戲的操作者是第一個平台管理員（`settings.FIRST_ADMIN_EMAIL`）。
- 所有時間以 `core.clock.now()` 為基準計算。
- 步驟放在 `STEPS` 的 `accounts.seed` 之後、`competition.seed` 之前；`demo_data/__init__.py`（A 的檔案）只新增 import 與這一行。

**Never:**
- 不建立「自訂」模式的《英雄聯盟》賽事（期中版規則）。
- 不建立隊伍與報名（C 的 registration 步驟）、不抽籤（D 的 competition 步驟）、不放裁判（2.7 第二階段後再補）。
- 不改 tournaments 既有函式的行為。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 全新資料庫 | 有 organizer 帳號、平台管理員 | 建立兩款遊戲、一場示範賽事；`context.tournament_to_draw` 為賽事 id | N/A |
| 再次啟動 | 遊戲與賽事已存在 | 不重複建立、不寫新的操作紀錄；`context.tournament_to_draw` 仍為同一場 | N/A |
| 遊戲同名已存在 | 有人先建了「特戰英豪」 | 沿用既有遊戲，不修改它的設定 | N/A |
| 沒有 organizer | `context.accounts` 沒有 `organizer` | 只建遊戲，略過賽事並記錄 log；`tournament_to_draw` 維持 None | 不拋錯 |
| 與 competition 串接 | 依 `STEPS` 順序執行 | competition 步驟讀得到 `tournament_to_draw`（registration 未就緒時由它自己略過） | N/A |

## Decisions

- 2026-11-04（使用者）：示範賽事建立後維持「開放報名」（`open`），不轉成 `closed`。D 的 `draw` 接受 `open`，會先呼叫 registration 的 `finalize_for_draw`（等同主辦方提前抽籤），抽完即為「賽程已公布」；避免 `closed` 狀態卻顯示未來報名截止時間的矛盾。PR 說明要請 D 確認 competition 步驟在 `open` 時也能正常抽籤。
- 2026-11-04（使用者）：示範賽事不放直播連結（`livestream_url` 留空）。理由：直播連結是選填，有直播時由主辦方自己填，一般賽事通常沒有，示範資料照一般情況。與 epics.md Story 7.1 AC「附直播連結」不同，S2 總覽因此不會出現「觀看直播」；PR 說明要註明這項差異。
- 2026-11-04（使用者）：兩款遊戲的設定（《特戰英豪》依 PRD 第 46 行與規程參考，其餘文件沒有寫，採建議值）：
  - 《特戰英豪》：`rounds`、先發 5、替補 1、BO3、每局預估 40 分鐘。
  - 《英雄聯盟》：`win_loss`、先發 5、替補 1、BO3、每局預估 35 分鐘。
- 2026-11-04（使用者）：段位對照表（不分 1～3 階）：
  - 《特戰英豪》：無排位 0、鐵牌 5、銅牌 15、銀牌 30、金牌 50、白金 75、鑽石 105、超凡入聖 140、神話 170、輻能戰魂 200。
  - 《英雄聯盟》：無排位 0、鐵牌 5、銅牌 15、銀牌 30、金牌 50、白金 70、翡翠 90、鑽石 115、大師 145、宗師 170、菁英 200。
- 2026-11-04（使用者）：示範賽事：名稱「FLOW 校園盃 特戰英豪」、名額 32、報名開始＝`now()`－1 小時、報名截止＝`now()`＋3 天、優先期 24 小時、開賽＝`now()`＋7 天、每輪間隔 180 分鐘（下限 15＋3×40＋30＝165）、棄權與申訴期用預設值（15、30 分鐘）。

</frozen-after-approval>

## Code Map

- `backend/app/demo_data/__init__.py` -- `STEPS`（目前 `accounts.seed`、`competition.seed`）；模組說明寫明新增步驟的方式。
- `backend/app/demo_data/context.py` -- `DemoContext.accounts`、`tournament_to_draw` 已存在，不必新增欄位。
- `backend/app/demo_data/accounts.py` -- 「先查是否存在、存在就 log 略過」的寫法照抄。
- `backend/app/demo_data/competition.py` -- 讀 `tournament_to_draw`；`draw` 接受 `open`／`closed`，開賽時間已過會被拒絕並略過。
- `backend/app/modules/tournaments/service.py:80` `list_games`、`:97` `create_game`、`:316` `create_tournament`（`_validate_schedule:271` 的日期規則）、`:438` `list_organizer_tournaments`、`:450` `transition_tournament`（`open → closed` 允許）。
- `backend/app/modules/tournaments/models.py` -- `GameIn`、`RankTierIn`、`TournamentCreate:348`。
- `backend/app/modules/identity/service.py:125` `find_account_id_by_email` -- 取平台管理員 id。
- `backend/tests/competition/test_demo_data.py`、`backend/tests/identity/test_demo_data.py` -- 示範資料測試的寫法；`frozen_clock` fixture。

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/demo_data/tournaments.py` -- `seed(session, context)`：兩款遊戲＋示範賽事＋寫入 `tournament_to_draw`
- [x] `backend/app/demo_data/__init__.py` -- import 並把 `tournaments.seed` 放在 `accounts.seed` 與 `competition.seed` 之間
- [x] `backend/tests/tournaments/test_demo_data.py` -- I/O 矩陣每一列；步驟順序；呼叫兩次不重複建立、不多寫操作紀錄
- [x] `_bmad-output/implementation-artifacts/deferred-work.md` -- 刪除 7.1 competition 步驟「沒有上游步驟寫入 tournament_to_draw」那一筆中屬於 B 的部分（若整筆只剩 C 的 registration 未完成，改為新增一筆只寫 C 的部分，原筆刪除）

**Acceptance Criteria:**
- Given 全新資料庫且設定了 `DEMO_PASSWORD`，when `docker compose up`，then backend log 出現示範遊戲與賽事的建立紀錄，且 competition 步驟不再記錄「No demo tournament to draw」

## Implementation Notes

- 實作子代理寫完 `tournaments.py`、測試與 `STEPS` 後，在驗證階段停滯超過 10 分鐘被中止（本機 `python` 是 Microsoft Store 空殼，無法在主機執行）；主代理接手，在容器內跑測試並完成其餘任務。
- 已存在的遊戲與賽事記錄 `already exists, reused`（不是 `skipped`）：步驟對兩者是「沿用」（仍把賽事 id 寫進 `tournament_to_draw`），字面較準確；也避免 A 的 `tests/identity/test_demo_data.py::test_init_twice_keeps_demo_account_count` 把所有含 `already exists, skipped` 的 log 都算進「管理員＋四個示範帳號」而失敗。A 的測試未修改。
- 建立賽事包在 `session.begin_nested()`：沿用的同名遊戲設定若讓每輪間隔低於下限（`FieldError` 是 `BusinessError` 的子類別），記錄 log 後略過賽事，遊戲保留，`tournament_to_draw` 為 None。`create_tournament` 目前在寫入前就完成所有檢查，savepoint 實際上沒有東西可撤銷，是防範之後先寫入再失敗時連帶撤銷前面步驟的資料（審查 #6）。
- 測試只檢查示範資料自己的遊戲與操作紀錄（依名稱、entity_id 篩選）：測試資料庫留有其他併發測試提交的資料，全部一起跑時「遊戲列表為空」「操作紀錄只有三筆」的寫法會失敗，單獨跑才通過。
- 以 compose 實際啟動確認：建立兩款遊戲與賽事，competition 步驟改為記錄 `REGISTRATION_UNAVAILABLE` 並略過抽籤（等 C 的 registration）。

## Spec Change Log

## Review Triage Log

第一輪（2026-11-04）：Blind Hunter 12 筆、Edge Case Hunter 4 筆、Verification Gap 0 筆（Other 1 筆）。

| # | 來源 | 發現 | 判定 | 處理 |
|---|------|------|------|------|
| 1 | Blind、Edge | 保留資料庫、超過 7 天再啟動時沿用已過開賽時間的示範賽事，抽籤一直被拒 | low：凍結區塊規定已存在就沿用、不覆寫；Demo 前 `down -v` 即可；自動處理要人決定另建或改寫 | defer |
| 2 | Blind | 賽事以完全相同的名稱比對，遊戲則去空白、不分大小寫 | low：直接修正為同一個正規化 | patch |
| 3 | Blind | 第二次執行的測試以全域筆數比較 | false：兩次呼叫在同一個測試交易內，之間沒有其他連線提交；測試資料庫每次重建、不平行執行 | 不處理 |
| 4 | Blind、Edge | 「沒有第一個管理員」的測試假設該 Email 不存在 | low：`session_factory` 也會回滾，目前不會遇到；直接 monkeypatch 成一定不存在的 Email | patch |
| 5 | Blind | 示範遊戲名稱可能與測試資料庫裡已提交的遊戲衝突 | low：會真正提交的只有併發測試，沒有用這兩個名稱 | 不處理 |
| 6 | Blind、Gap | 測試與註解說 savepoint 只撤銷建立賽事，但 `create_tournament` 在寫入前就檢查完，沒有東西被撤銷，拿掉 savepoint 測試仍過 | low：說法誤導；修正註解與 Implementation Notes，測試改為斷言既有遊戲設定不變 | patch |
| 7 | Blind | `load()` 測試只斷言某行 log 不存在，沒證明 competition 拿到 id | low：改斷言 competition 的 log 帶有示範賽事 id | patch |
| 8 | Blind | I/O 矩陣沒有「找不到第一個管理員」 | low：修正方式是改凍結區塊；已有測試 | 不處理 |
| 9 | Blind | 模組說明寫「略過」，程式是沿用 | low | patch |
| 10 | Blind | 新的延後項目放在別的 spec 的標題下 | low：該筆是本分支新增，搬到本 spec 的標題 | patch |
| 11 | Blind | Verification 寫死本機路徑 | low：修正方式是改本 spec | 不處理 |
| 12 | Blind | spec 狀態早於審查紀錄、PR 說明的要求沒有追蹤 | false：審查紀錄即本表；PR 說明在開 PR 時處理 | 不處理 |
| 13 | Edge | `list_games` 與 `create_game` 之間有人同名建立，`GAME_NAME_TAKEN` 讓整段示範資料回滾 | low：示範資料只在單一 backend 啟動時執行 | 不處理 |
| 14 | Edge | `FIRST_ADMIN_EMAIL` 的帳號存在但不是平台管理員 | low：`initial_data` 先以這個 Email 建立平台管理員 | 不處理 |

## Verification

所有檔案與指令都在 `C:\Users\grace\espory-7-1-tournaments`（分支 `story/7-1-tournaments`）；compose 指令可在主資料夾 `C:\Users\grace\espory-platform` 以 `-v` 掛載本工作區執行，或另指定 compose 專案名稱。

**Commands:**
- `bash scripts/test.sh`（backend 容器內）-- 全部通過、覆蓋率門檻通過
- `bash scripts/lint.sh`（backend 容器內）-- 通過
