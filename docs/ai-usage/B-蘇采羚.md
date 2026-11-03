# 蘇采羚 的 AI 使用紀錄

格式與等級定義見 [README](README.md)。只在檔尾新增，最新的在最下面。

### 2026-10-29｜需求／設計｜Story 2.1 spec：拆出後端第一階段

- Story／範圍：2.1（PR #9）
- 工具：Claude Code（Opus 5.5）＋ bmad-build
- 怎麼用：以 bmad-build 讀 epic-2-context 與既有程式，產生 spec，列出需要人決定的問題
- AI 產出：`spec-2-1-game-settings-and-school-list.md`（I/O Matrix 10 列）；`deferred-work.md` 新增 2 筆（第二階段畫面、移到 2.2 的快照驗收）
- 人做了什麼：回答 2 個 Open Questions：後台版面（A 的 1.8）還沒好，決定先做後端、畫面等 1.8；需要 Tournament 的兩條 AC 移到 2.2 驗收
- 驗證：spec 經人核准後鎖定 `<frozen-after-approval>`
- 問題與修正：第一版 spec 把前後端一起寫，約 3400 tokens，超過 bmad-build 建議的 1600；AI 依 SCOPE STANDARD 指出後，配合人的決定改成只做後端，約 2200 tokens
- 成熟度：L3（AI 依 epic context 與既有程式產出 spec，範圍與驗收由人決定）
- 證據：`_bmad-output/implementation-artifacts/spec-2-1-game-settings-and-school-list.md` 的 Decisions

### 2026-10-29｜程式／程式生成｜Story 2.1 第一階段：遊戲設定與學校清單的後端

- Story／範圍：2.1（PR #9）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（實作子代理）
- 怎麼用：核准 spec 後，由不帶對話脈絡的實作子代理只依 spec 實作
- AI 產出：`game_title`、`rank_tier` 兩張表與遷移檔；遊戲 API 4 支（`/admin/games`）、學校 API 2 支（`/admin/schools`）；公開函式 `tournaments.service.get_game()` 供 2.2 使用；共用測試工具 `tests/helpers.py`；重新產生 `frontend/src/client`
- 人做了什麼：核准 spec；決定分兩階段
- 驗證：後端 319 個測試全過、覆蓋率 95%；`scripts/lint.sh`（mypy、ty、ruff）、前端 build 與 typecheck 通過
- 問題與修正：子代理第一次執行時對話中斷，沒有寫出任何程式，以 `git status` 確認後讓它接續完成。另外 uv 在 Windows 安裝 Python 3.14 時回報連結錯誤，AI 確認直譯器本身可用後改以 `UV_PYTHON` 指定，bmad-build 才能執行
- 成熟度：L4（固定流程：spec → 子代理實作 → 自動測試，人只在 checkpoint 決策）
- 證據：PR #9、spec 的 Implementation Notes、commit 未記錄

### 2026-10-29｜測試／程式審查｜Story 2.1 三個審查者審查與修正

- Story／範圍：2.1（PR #9）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（Blind Hunter、Edge Case Hunter、Verification Gap 三個審查子代理）
- 怎麼用：三個審查者各自只看 diff 審查，主代理逐筆查證後分類為 patch、defer 或不處理
- AI 產出：17 筆發現（Blind Hunter 14、Edge Case Hunter 3、Verification Gap 0）；4 筆修正、1 筆延後、12 筆不處理（逐筆理由記在 spec 的 Review Triage Log）；新增 4 個測試
- 人做了什麼：未記錄（審查分類由 AI 完成，待人在 PR 審查時確認）
- 驗證：修正後後端測試由 315 個增為 319 個，全部通過，覆蓋率 95%
- 問題與修正：審查抓到實作的錯誤：段位名稱的驗證不分大小寫，但資料庫唯一限制區分大小寫，繞過 API 的寫入可存入「Diamond」與「diamond」，改成 `lower(btrim(name))` 唯一索引；重名判斷以錯誤訊息字串比對索引名稱，前綴相同的索引也會命中，改成比對 `diag.constraint_name`；競態與 404 測試沒有檢查錯誤代碼與「沒有寫入操作紀錄」。另有 1 筆既有問題（Pydantic 內建 422 訊息是英文）記進 `deferred-work.md`
- 成熟度：L4（多個審查者＋主代理查證＋測試驗證，人只在 PR 決策）
- 證據：spec 的 Review Triage Log、`deferred-work.md`

### 2026-10-30｜設計／介面約定｜tournaments 模組介面約定

- Story／範圍：CONTRIBUTING 6.5 約定介面；回覆 `contracts/competition.md`〈三〉第 1、3 項
- 工具：Claude Code（Opus 5.5）＋ Explore 子代理
- 怎麼用：請 AI 整理設計文件、epic 2～7 context、D 的 competition 約定與 A 已推上的分支中，其他模組對 tournaments 的需求，寫成約定文件
- AI 產出：`contracts/tournaments.md`（4 個 schema、9 個公開函式、7 種狀態轉換）；同步修改 `competition.md` 的欄位名稱與待確認事項、`contracts/README.md`
- 人做了什麼：決定申訴相關的 4 個 competition 函式由自己實作、D 審查
- 驗證：未記錄（待 C、D 在 PR 確認）
- 問題與修正：AI 對照各方需求時發現名稱不一致：D 的約定把每局預估時間叫 `game_minutes_per_game`，2.1 已實作的 `GameTitle` 與設計文件叫 `game_minutes`，統一為後者並改 D 的文件；也找到 A 的 5.2 分支已假設 `lock_tournament` 回傳 `status` 與 `appeal_minutes`，納入 `TournamentRead`
- 成熟度：L3（AI 依既有規格彙整並提出介面，人做決策，組員審查）
- 證據：`_bmad-output/implementation-artifacts/contracts/tournaments.md`

### 2026-10-30｜需求／設計｜Story 2.2 spec：建立賽事的後端

- Story／範圍：2.2（PR #15）；附帶回寫 Story 2.1 第一階段的 commit `d4227cd`
- 工具：Claude Code（Opus 5.5）＋ bmad-build（Explore 子代理調查程式）
- 怎麼用：以 bmad-build 依 epic-2-context、tournaments 介面約定與 A 的 1.8 分支產生 spec，列出需要人決定的問題
- AI 產出：`spec-2-2-create-tournament.md`（I/O Matrix 17 列）；`deferred-work.md` 新增第二階段畫面與「名額超過 128 提醒」2 筆
- 人做了什麼：回答 3 個問題：先做後端、開賽與報名截止必須晚於現在、名額上限；實作開始後把名額改為「128 是提醒門檻、不是上限，超過時畫面彈出確認」
- 驗證：spec 經人核准後鎖定；名額規則變更以人修改 Decisions 後通知實作子代理
- 問題與修正：AI 起初只提供「上限 128／不設上限」兩個選項，沒想到「提醒但可確認」的做法，由人提出；AI 依此把規則拆成後端（不限）與第二階段畫面（提醒）兩部分
- 成熟度：L3（AI 依規格產出 spec，範圍與規則由人決定）
- 證據：spec 的 Decisions、`deferred-work.md`

### 2026-10-30｜程式／程式生成｜Story 2.2 第一階段：Tournament 資料表、建立賽事 API、自動開放報名

- Story／範圍：2.2（PR #15）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（實作子代理）
- 怎麼用：核准 spec 後，由不帶對話脈絡的實作子代理只依 spec 實作
- AI 產出：`tournament` 表與遷移檔（含 `audit_log.tournament_id` 外鍵）；API 4 支（`/games`、`/organizer/tournaments`）；`Organizer` 權限、`core/authz.py`；介面約定的 6 個公開函式；worker 工作 `open_registrations`；重新產生 `frontend/src/client`
- 人做了什麼：核准 spec；實作中途修改名額規則
- 驗證：後端 463 個測試全過、覆蓋率 95%；lint、前端 build 與 typecheck 通過
- 問題與修正：實作中途收到兩次名額規則變更（先上限 128、再改回不設上限），子代理照最後的規則實作，測試確認名額 128、129、200 都能建立，程式中沒有殘留 128 的限制
- 成熟度：L4（固定流程：spec → 子代理實作 → 自動測試，人只在 checkpoint 決策）
- 證據：PR #15、spec 的 Implementation Notes、commit 未記錄

### 2026-10-30｜測試／程式審查｜Story 2.2 三個審查者審查與修正

- Story／範圍：2.2（PR #15）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（Blind Hunter、Edge Case Hunter、Verification Gap）
- 怎麼用：三個審查者各自只看 diff，主代理逐筆查證後分類
- AI 產出：23 筆發現（Blind 13、Edge 9、Gap 1）；4 筆修正、1 筆延後、18 筆不處理（理由記在 spec 的 Review Triage Log）；新增 3 個測試、修改 2 個
- 人做了什麼：未記錄（審查分類由 AI 完成，待人在 PR 審查時確認）
- 驗證：修正後測試由 458 增為 463 個，全部通過
- 問題與修正：審查抓到 worker「鎖定後重新檢查」的分支沒有測試，拿掉這段檢查也不會有測試失敗；一個測試只檢查測試自己定義的集合（循環斷言），沒有呼叫 service；建立賽事時以 `FOR UPDATE` 鎖遊戲，讓同一款遊戲的建立互相排隊，改成 `FOR SHARE`。另有一筆審查者宣稱「只載入 core 的腳本會找不到 tournament 表」，主代理在容器實測後判定為誤報。「報名截止後沒有工作轉成 closed」屬於 C 的 3.6，記進 `deferred-work.md`
- 成熟度：L4（多個審查者＋主代理實測查證＋測試驗證）
- 證據：spec 的 Review Triage Log、`deferred-work.md`

### 2026-11-02｜需求／設計｜Story 2.4 spec：公開賽事列表與賽事頁

- Story／範圍：2.4（PR #29）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（Explore 子代理調查程式與組員分支）
- 怎麼用：以 bmad-build 依 epic-2-context、介面約定與 A、C、D 尚未合併的分支產生 spec
- AI 產出：`spec-2-4-public-tournament-pages.md`（I/O Matrix 11 列）；`deferred-work.md` 新增第二階段 1 筆
- 人做了什麼：決定拆兩階段、S1 分組順序（觀眾最關心的在前）；審查後兩度決定倒數文字（報名開始寫「開放報名」、歸零寫「報名開放中 · 系統處理中」），並同意第二次以小修正處理、不還原重做
- 驗證：spec 經人核准後鎖定；兩次修改凍結區塊都由人決定
- 問題與修正：AI 調查時先找出 A 的 5.8 已在 S2 底下建了場次頁，若照一般寫法加外框路由會把 S4 包進 S2，因此改用 `index.tsx`。但 AI 寫 spec 時規定所有倒數都寫「截止」，沒想到報名開始也用同一個元件，造成報名開始被標成「截止」，第一輪審查才發現
- 成熟度：L3（AI 依規格與組員程式產出 spec，規則由人決定）
- 證據：spec 的 Decisions、Spec Change Log

### 2026-11-02｜程式／程式生成｜Story 2.4 第一階段：公開 API、S1、S2 總覽、Countdown、Page banner

- Story／範圍：2.4（PR #29）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（實作子代理，intent_gap 後重新實作一次）
- 怎麼用：核准 spec 後由實作子代理依 spec 實作；第一輪審查發現 intent_gap，依流程還原程式、人修改 spec 後重新實作（沿用第一輪 patch 中做對的部分）
- AI 產出：公開 API 2 支與 `PublicTournament`；S1 賽事列表、S2 賽事頁總覽；全站共用的 Countdown、Page banner 元件；重新產生 client 與路由檔
- 人做了什麼：核准兩版 spec；回答倒數文字的兩個問題
- 驗證：後端 948 個測試、覆蓋率 96%；前端 287 個單元測試（24 個檔案）連跑多次皆通過；lint、build、typecheck、biome 通過；實作子代理在瀏覽器以 375 px 檢查 S1、S2 沒有橫向捲軸
- 問題與修正：第一輪的 patch 是 BOM＋CRLF，無法直接套用，重新實作的子代理轉成 LF 後套用。另外子代理回報：新增 3 個測試檔後，前端單元測試在並行負載下偶爾冷啟動逾時（既有問題，已記在 deferred-work）
- 成熟度：L4（spec → 子代理實作 → 自動測試；intent_gap 依流程回到人決定）
- 證據：PR #29、spec 的 Implementation Notes、commit 未記錄

### 2026-11-02｜測試／程式審查｜Story 2.4 兩輪三人審查

- Story／範圍：2.4（PR #29）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（Blind Hunter、Edge Case Hunter、Verification Gap，兩輪）
- 怎麼用：每輪三個審查者各自只看 diff，主代理逐筆查證後分類
- AI 產出：第一輪 20 筆（1 筆 intent_gap 導致還原重做，10 筆改寫進 spec 的 Design Notes、1 筆延後）；第二輪 17 筆（1 筆 intent_gap 經人同意當小修正，7 筆修正、2 筆延後）；共 28 列記在 Review Triage Log
- 人做了什麼：兩次決定倒數文字；決定第二次不還原重做
- 驗證：修正後全部測試通過；第二輪修正的「deadline 改變時閃錯數字」先確認測試在修正前會失敗
- 問題與修正：審查抓到的 AI 錯誤包括：報名開始倒數寫成「截止」、歸零又寫「已截止」（兩次都源自 spec）；分頁型別在 5.8 合併後會讓別人的 PR typecheck 失敗；離開賽事頁後分頁標題沒有還原；公開 API 的時間欄位對調也不會有測試失敗。審查者宣稱 S2 漏了優先期結束倒數，主代理對照 epics.md 判定該倒數在主辦方的 S27，屬誤報
- 成熟度：L4（多個審查者＋主代理查證＋測試驗證；需要決定的事回到人）
- 證據：spec 的 Review Triage Log、Spec Change Log、`deferred-work.md`

### 2026-11-02｜測試／CI｜Story 2.2 修正 CI 失敗：兩個 Alembic head

- Story／範圍：2.2（PR #15）
- 工具：Claude Code（Opus 5.5），未經 BMAD
- 怎麼用：只下「2.2 給我修好」，AI 自己找出 PR #15、讀 CI log 與組員留言，判斷要修什麼
- AI 產出：遷移檔 `e4b8c1d2a6f7` 的 `down_revision` 與檔頭 `Revises:` 改成 1.7 的 `c7e2a4d9b8f1`（2 行）；更新 PR 說明的遷移順序
- 人做了什麼：同意 commit、push 並更新 PR 說明
- 驗證：容器內 `alembic heads` 只剩一個 head；後端測試 1002 個通過、1 個失敗，失敗的是寄信測試，因第一次只啟動 db 與 backend、沒有 mailpit，補上 mailpit 後重跑該測試檔 26 個全過；ruff check 與 format 通過
- 問題與修正：本機 `story/2-2` 落後遠端 3 個 commit（A 已合併 main），AI 先比對遠端才發現，改為同步後再修，避免在舊版上修改；為了不蓋掉使用者正在跑的 2.4 容器，AI 另開 git worktree，並用暫時的 compose 設定清掉對外 port，在獨立的 compose 專案跑測試
- 成熟度：L3（AI 依 CONTRIBUTING 第 4 節與審查意見修正，人決定是否推上去）
- 證據：PR #15、CI run 41384713533（修正前失敗）

### 2026-11-02｜需求／設計｜Story 2.1 第二階段 spec：S36 遊戲設定與學校清單畫面

- Story／範圍：2.1 第二階段（分支 `story/2-1-ui`，PR 未建立）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（Explore 子代理調查 1.8 的後台版面與前端寫法）
- 怎麼用：問 AI「2.1 現在可以動工了嗎」，AI 確認 1.8 已合併、沒有人重複後，以 bmad-build 依 epic-2-context、第一階段 spec 與 UX 文件產生第二階段 spec
- AI 產出：`spec-2-1-s36-game-settings-and-school-list-ui.md`（I/O Matrix 10 列）；1 個需要人決定的問題（側欄入口兩個項目或一個項目＋Tabs）
- 人做了什麼：選擇側欄放兩個項目；核准 spec；審查時決定遊戲列表「點名稱」進編輯頁即可，不做點整列
- 驗證：spec 經人核准後鎖定；兩個決定都寫進 spec 的 Decisions
- 問題與修正：AI 寫的凍結區塊自相矛盾：I/O Matrix 寫「點列進編輯頁」，Never 又寫「不改 1.8 既有元件」，而 1.8 的 Data table 沒有列點擊功能。實作子代理只能做名稱連結，Blind Hunter 審查時指出偏離凍結區塊，交由人決定後記入 Decisions。spec 長度約 7,400 字元，超過 BMAD 建議的上限，AI 提出後人選擇保留整份
- 成熟度：L3（AI 依既有規格產出 spec，規則由人決定）
- 證據：spec 的 Decisions、Review Triage Log #8

### 2026-11-02｜程式／程式生成｜Story 2.1 第二階段：S36 遊戲設定與學校清單畫面

- Story／範圍：2.1 第二階段（分支 `story/2-1-ui`）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（不帶對話脈絡的實作子代理）
- 怎麼用：核准 spec 後，由實作子代理只依 spec 實作；主代理讀 diff 逐項核對任務與 I/O Matrix 的測試覆蓋
- AI 產出：新增 13 個前端檔案（遊戲列表、新增／編輯頁與共用表單、學校清單與 Dialog、4 個路由、側欄 2 個項目、重新產生 `routeTree.gen.ts`）；單元測試 2 個檔案、24 個
- 人做了什麼：核准 spec；確認實作時自訂的畫面文字與行為（學校空狀態文案、新增時不預選 BO、編輯後留在編輯頁）
- 驗證：主代理在獨立的 compose 專案重新 build 後執行，前端 build、typecheck、Biome 通過，單元測試 30 個檔案、329 個全過
- 問題與修正：子代理的回報與 diff 一致；它主動在 Implementation Notes 列出 spec 沒規定、由它自行決定的 5 件事，讓人確認
- 成熟度：L4（spec → 子代理實作 → 主代理依 diff 核對 → 自動測試）
- 證據：spec 的 Tasks、Implementation Notes；commit 未記錄

### 2026-11-02｜測試／程式審查｜Story 2.1 第二階段：三個審查者審查與修正

- Story／範圍：2.1 第二階段（分支 `story/2-1-ui`）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（Blind Hunter、Edge Case Hunter、Verification Gap）
- 怎麼用：三個審查者各自只看 diff（Edge Case Hunter 最後才讀 spec），主代理逐筆查證後分類
- AI 產出：28 筆發現；12 筆修正、1 筆交由人決定、1 筆誤報、14 筆不處理（理由記在 spec 的 Review Triage Log），沒有延後項目；新增 9 個測試（S36 測試由 24 個增為 33 個）
- 人做了什麼：決定 1 筆凍結區塊的衝突（點名稱即可）
- 驗證：修正後前端 build、typecheck、Biome 通過，單元測試 338 個全過；後端 1003 個測試全過、覆蓋率 96%，lint 通過
- 問題與修正：審查找到實作的 3 個實際問題：網址的遊戲 id 不是 UUID 時後端回 422，畫面顯示英文驗證訊息；已載入後背景重抓失敗，表單被錯誤畫面取代，未儲存的修改消失；注音輸入法打出的全形數字「５」被判為「請輸入整數」。另外段位名稱比對用 `toLowerCase()`，後端用 `casefold()`，ß 與 SS 前端會放行。「路由產生檔沒有被審查」一筆為誤報：產生檔刻意不放進審查的 diff，build 通過。主代理在獨立的 compose 專案驗證時重新 build 了共用名稱的 `flow-backend:latest` 映像，事後才發現 compose 檔固定了這個映像名稱
- 成熟度：L4（多個審查者＋主代理查證＋測試驗證，人只決定凍結區塊）
- 證據：spec 的 Review Triage Log
