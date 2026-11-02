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

### 2026-11-02｜需求／驗收條件｜Story 2.2 第二階段 spec：S25、S26、S27 畫面

- Story／範圍：2.2 第二階段（PR 未建立）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（另一個 session 交辦，在獨立 worktree 進行）
- 怎麼用：AI 先用 `gh pr list --state all` 確認沒有重複；接著讀 epic-2-context、第一階段 spec、epics.md 的 2.2 AC、EXPERIENCE.md、1.8 的元件與後端驗證規則，寫成 spec
- AI 產出：`spec-2-2-organizer-tournament-ui.md`，含 15 列 I/O Matrix 與 Code Map；從 origin/main 開 `story/2-2-ui` 分支
- 人做了什麼：決定優先期以「小時」輸入，預設 24（UX 文件標為未定）；決定 spec 約 3000 tokens 超過建議值也不拆；核准 spec
- 驗證：spec 經人核准後鎖定
- 問題與修正：交辦時 worktree 停在別人進行中的 PR #30（2.1 第二階段）分支上，AI 改從 origin/main 開新分支，避免把未合併的內容帶進來。AI 調查時發現 UX 的 reconcile 文件把優先期單位列為未定，沒有自己假設，改問人
- 成熟度：L3（AI 依既有規格整理 spec，未定事項交給人決定）
- 證據：spec 的 Decisions、Code Map

### 2026-11-02｜程式／程式生成｜Story 2.2 第二階段：S25 我的賽事、S26 建立賽事、S27 賽事總覽

- Story／範圍：2.2 第二階段（PR 未建立）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（實作子代理）
- 怎麼用：核准 spec 後，由沒有對話脈絡的子代理只依 spec 實作；主代理讀完整 diff 再對照 Tasks 與 I/O Matrix 驗收
- AI 產出：只改前端。新增 3 個畫面元件、`TournamentStatusBadge`、主辦方的查詢與 mutation、側欄設定、`taipeiLocalToIso`（台北時間轉 UTC）、3 個路由檔，並改寫 1.8 的 S25 佔位頁；新增測試檔 `organizer-tournaments.test.tsx`；從 deferred-work 刪掉 2.2 的兩筆
- 人做了什麼：核准 spec，其餘由流程完成
- 驗證：在 worktree 自建的前端映像中跑 build、typecheck、biome 都通過；單元測試 45 個檔案、535 個全部通過
- 問題與修正：worktree 沒有 `.env`，而且使用者的主資料夾已啟動同名 compose 專案，子代理沒有照 spec 跑 `docker compose`，改用 `docker build` 建獨立映像驗證，避免動到共用容器。另外，用 bind mount 跑測試時，Windows 檔案系統太慢，各檔第一個測試會逾時，與本次改動無關。動到 A 的測試檔 `backoffice-layout.test.tsx`，把佔位頁的斷言改成新行為，要在 PR 說明列出
- 成熟度：L4（spec → 子代理實作 → 自動測試，主代理依 diff 驗收）
- 證據：spec 的 Tasks、Implementation Notes；commit 未記錄

### 2026-11-02｜測試／程式審查｜Story 2.2 第二階段三人審查

- Story／範圍：2.2 第二階段（PR 未建立）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（Blind Hunter、Edge Case Hunter、Verification Gap）
- 怎麼用：三個審查者各自只看 diff，主代理逐筆查證、分類後，交回同一個實作子代理修正
- AI 產出：共 23 筆，Blind Hunter 13、Edge Case Hunter 7、Verification Gap 2＋1。其中 9 筆修正（含補測試），14 筆經查證不處理（6 筆誤報），0 筆延後；逐筆記在 Review Triage Log
- 人做了什麼：無，審查與修正都在流程內完成
- 驗證：修正後全部重新驗證，build、typecheck、biome 都通過，單元測試由 531 個增為 535 個，全部通過
- 問題與修正：
  - 審查抓到 AI 實作的錯誤：
    - 驗證期間連按「建立賽事」，或連按名額確認鈕，會呼叫兩次 API，建立重複的賽事。
    - 送出失敗後修正 BO 或開賽時間，每輪間隔、報名截止欄位的舊錯誤不會更新。
    - 背景重抓遊戲清單失敗時，即使有快取也會停用選單。
    - 直播連結長度以 UTF-16 計算，與後端算法不同。
    - 確認對話框的註解寫錯順序。
    - 頁碼超出的修正與 `GAME_NOT_FOUND` 重抓都沒有測試；把網址頁碼修正拿掉時，有賽事的主辦方會看到空狀態，測試卻照樣通過。
  - 修正連按時，子代理發現照主代理的建議在 `onSettled` 解鎖，測試中仍會送出兩次，改成只在失敗時解鎖。
  - 誤報：審查者認為 `datetime-local` 帶毫秒會被拒絕，但沒有設定 `step` 時瀏覽器的值只到分鐘。
- 成熟度：L4（多個審查者＋主代理查證＋測試驗證）
- 證據：spec 的 Review Triage Log
