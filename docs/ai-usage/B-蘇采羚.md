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

### 2026-11-03｜需求／設計｜Story 2.4 第二階段 spec：狀態徽章與申請主辦方 banner

- Story／範圍：2.4 第二階段（第 1、2 項；PR 未開）
- 工具：Claude Code（Opus 5.5）＋ bmad-build，由另一個 Claude Code session 交辦
- 怎麼用：依 deferred-work 的 2.4 第二階段項目、第一階段 spec、epic-2-context 與 DESIGN／EXPERIENCE 產生 spec
- AI 產出：`spec-2-4-status-badge-and-organizer-banner.md`（I/O Matrix 8 列）；1 個 Open Question（banner 文字與按鈕的兩種寫法）
- 人做了什麼：選定 banner 文字「想辦賽事？」、按鈕「申請成為主辦方」；核准 AI 自行決定的三件事（關閉狀態依帳號分開、S2 總覽「狀態」欄也換徽章、S1 分組標題維持文字）；決定第 3 項等 PR #31 合併再做
- 驗證：spec 經人核准後鎖定
- 問題與修正：AI 對照 DESIGN.md 後發現交辦內容「開放報名、進行中：live 加上進行中脈動」若照字面會讓開放報名也有脈動點，依設計表改為只有進行中有脈動點，寫進 spec。AI 第一次用 Git Bash 的 `python` 改 spec 沒有生效（這台電腦的 `python` 是 Windows 商店的別名，沒有報錯），檢查 `grep` 結果才發現，改用編輯工具
- 成熟度：L3（AI 依規格產出 spec，需要使用者察覺的選擇回到人決定）
- 證據：spec 的 Decisions

### 2026-11-03｜程式／程式生成｜Story 2.4 第二階段：S1、S2 狀態徽章與申請主辦方 banner

- Story／範圍：2.4 第二階段（PR 未開）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（實作子代理）
- 怎麼用：核准 spec 後由實作子代理依 spec 實作，審查後再由同一個子代理修正
- AI 產出：新增 `TournamentStatusBadge.tsx`、`OrganizerApplyBanner.tsx`（`useOrganizerApplyBanner` hook）；修改 `status.ts`、`TournamentList.tsx`、`TournamentPage.tsx`、`TournamentOverview.tsx`；2 個測試檔共 20 個測試；`deferred-work.md` 新增 2 筆
- 人做了什麼：核准 spec；交辦時指定原本的延後項目不可刪除
- 驗證：前端 typecheck、biome、build 通過；單元測試 49 個檔、562 個測試全部通過（`--maxWorkers=4`）；子代理以 375 px 在瀏覽器量 S1、S2 的 `scrollWidth` 為 375
- 問題與修正：實作子代理把交辦時明確要求保留的 2.4 第二階段延後項目刪掉，主代理比對 `deferred-work.md` 的 diff 發現並還原。子代理為了實測 banner，自行連到另一個 session 的 docker 堆疊並各建了一個測試帳號（未刪除），回報後主代理要求之後不再這樣做
- 成熟度：L4（spec → 子代理實作 → 主代理比對 diff → 自動測試）
- 證據：spec 的 Implementation Notes、commit 未記錄

### 2026-11-03｜測試／程式審查｜Story 2.4 第二階段三人審查

- Story／範圍：2.4 第二階段（PR 未開）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（Blind Hunter、Edge Case Hunter、Verification Gap）
- 怎麼用：三個審查者各自只看 diff，主代理逐筆查證後分類
- AI 產出：16 筆發現（Blind 13、Edge 3、Gap 0）；5 筆修正、1 筆延後、10 筆不處理，記在 spec 的 Review Triage Log
- 人做了什麼：未記錄（審查分類由 AI 完成，待人在 PR 審查時確認）
- 驗證：修正後前端 typecheck、biome、build 通過，單元測試 562 個全部通過
- 問題與修正：審查抓到 banner 元件自己包一個 `PageBannerSlot`，S1 頁面失去「同頁最多一則」的控制，與 spec 不符，改成 hook 由頁面擁有 slot。主代理修正後單獨重跑新測試時，S2 的徽章測試固定失敗（路由延遲載入的冷啟動超過 1 秒），全部一起跑時剛好通過，實作子代理與審查者都沒發現；比照既有測試加上預先載入後通過。審查者宣稱「未驗證 Email 的帳號點 banner 會卡住」，主代理查 S15 確認會引導去驗證，判定為誤報
- 成熟度：L4（多個審查者＋主代理查證＋測試驗證）
- 證據：spec 的 Review Triage Log、`deferred-work.md`
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

### 2026-11-03｜測試／測試個案修正｜Story 2.4 第二階段：依 PR #32 審查加強 banner 測試

- Story／範圍：2.4 第二階段（PR #32）
- 工具：Claude Code（Opus 5.5），未經 BMAD，由另一個 Claude Code session 轉交
- 怎麼用：照 D 在 PR #32 的審查意見第 1、2 點修改測試，再用突變檢查確認測試會失敗
- AI 產出：`organizer-apply-banner.test.tsx` 的 `settle()` 改成等 QueryClient 中帳號與申請查詢的狀態落定才斷言；加上 `beforeAll` 預先載入 S1
- 人做了什麼：D 審查時指出「不顯示」的測試可能在查詢 pending 時空過；使用者決定處理第 1、2 點、第 3 點不做
- 驗證：3 種突變（申請條件兩種、帳號條件一種）各自讓對應測試失敗，還原後 11 個全過；前端 typecheck、biome、build 通過，單元測試 662 個中 661 個通過，失敗的是 2.1 的 `admin-games.test.tsx` 偶發逾時，單獨跑全過
- 問題與修正：這是先前 AI 寫的測試的缺陷，三個 AI 審查者都沒抓到，由組員 D 在 PR 審查發現。AI 修改時第一版用了 `.at(-1)`，vitest 能跑但 typecheck 失敗（專案的 lib 設定沒有 ES2022），跑完整檢查才發現，改成索引取值
- 成熟度：L3（AI 依人的審查意見修正，並以突變檢查驗證）
- 證據：PR #32 的 review、spec 的 Implementation Notes

### 2026-11-04｜程式／程式生成｜Story 2.4 第二階段第 3 項：S1 空狀態對主辦方顯示「建立賽事」

- Story／範圍：2.4 第二階段第 3 項（PR 未開）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（oneshot 路線、Blind Hunter 審查），由另一個 Claude Code session 轉交
- 怎麼用：PR #31（S26）合併後，依 deferred-work 那筆與 EXPERIENCE.md〈通用狀態〉以 oneshot spec 實作，主辦方判斷沿用 banner 的帳號查詢
- AI 產出：`spec-2-4-s1-empty-create-tournament.md`；新增 `CreateTournamentButton.tsx`（從 S25 抽出共用）；修改 `TournamentList.tsx`、`OrganizerTournamentsPage.tsx`；測試檔 1 個、5 個測試
- 人做了什麼：決定開始做第 3 項，指定至少涵蓋主辦方、一般帳號、未登入三種身分
- 驗證：突變檢查（按鈕改為一律顯示時 2 個測試失敗）；typecheck、biome、build 通過；單元測試 703 個中 701 個通過，失敗的 2 個（2.1、2.2 的第一個測試）是本機負載下的冷啟動逾時，單獨跑全過
- 問題與修正：AI 第一版在 S1 手刻空狀態，Blind Hunter 指出 S25 與 UX-DR17 都用共用的 `EmptyState`，改用後所有人看到的 S1 空狀態也一併統一；另補上「帳號載入失敗」的測試、刪掉多餘的 re-export。審查共 9 筆：3 筆修正、6 筆不處理（理由在 spec）
- 成熟度：L4（spec → 實作 → 審查者 → 突變檢查與自動測試）
- 證據：spec 的 Implementation Notes、Review Triage Log
### 2026-11-03｜測試／程式審查｜Story 2.1 依組長審查補測試與無障礙名稱

- Story／範圍：2.1 第二階段的審查後續（PR #30 已合併，另開修正 PR）
- 工具：Claude Code（Opus 5.5），未經 BMAD
- 怎麼用：AI 讀 A（@max930000）在 PR #30 的審查意見，照意見修正，並把要延後的項目記下來
- AI 產出：「編輯」「修正名稱」按鈕的無障礙名稱帶上遊戲名稱與學校名稱（2 個元件）；新增 1 個測試：已載入、改了欄位之後，背景重抓失敗，表單與改到一半的值仍保留；更新 5 處依舊按鈕名稱尋找元素的測試；`deferred-work.md` 新增 1 筆「防連點沒有測試」
- 人做了什麼：決定先做 PR #30 的後續修正，再做 2.4 第 3 項
- 驗證：前端 build、typecheck、Biome 通過；單元測試 55 個檔案、699 個全過（4 個 worker）。把 `EditGamePage` 的判斷改回「先看錯誤、再看資料」後，新測試失敗；改回來後通過
- 問題與修正：A 在審查中指出，S36 審查時補的測試只涵蓋「第一次載入就失敗」，沒有涵蓋 PR 說明中標為風險最高的「已載入後背景重抓失敗」，把判斷順序改回去，現有測試仍全部通過。AI 先前把兩種情境當成同一件事，主代理核對時也沒有發現。這次 AI 寫的新測試，第一版用「表單元素存在」當作等待條件，但表單本來就在畫面上，等於沒有等到重抓的錯誤，自行檢查後改成等請求結束、畫面重新渲染。另外 Biome 抓到一處換行格式不合規則
- 成熟度：L3（AI 依人的審查意見修正，並以故意改壞程式碼的方式確認測試有效）
- 證據：PR #30 的 A 審查意見；commit 未記錄

### 2026-11-04｜程式／程式生成｜Story 7.1 示範資料的 tournaments 步驟

- Story／範圍：7.1 第二階段的 tournaments 步驟（B 負責；分支 `story/7-1-tournaments`）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（實作子代理、Blind Hunter、Edge Case Hunter、Verification Gap）
- 怎麼用：D 請 B 補上建立示範賽事並寫入 `context.tournament_to_draw` 的步驟；AI 查 planning 文件後列出 4 個開放問題（每題附建議值），人決定後由子代理實作，主代理接手驗證，三個審查者審查
- AI 產出：`demo_data/tournaments.py`（兩款遊戲＋段位表＋「FLOW 校園盃 特戰英豪」）；`STEPS` 新增一行；測試 1 個檔案；`deferred-work.md` 拆出只剩 C 的 registration 那一筆，並新增 1 筆延後項目
- 人做了什麼：決定示範賽事維持開放報名（不照 D 原本說的「已截止報名」，避免狀態和未來的截止時間矛盾）、不放直播連結（與 7.1 AC 不同，理由是一般賽事通常沒有）、遊戲與段位數值與賽事時間採 AI 的建議值；核准 spec
- 驗證：以 compose 實際啟動，log 顯示建立兩款遊戲與賽事，competition 步驟從「No demo tournament to draw」變成 `REGISTRATION_UNAVAILABLE`（等 C）；後端 1477 個測試全過、覆蓋率 97%，lint 通過
- 問題與修正：AI 發現 D 要的「已截止報名」和 2.2 的「報名截止必須晚於現在」互相矛盾，查到 D 的 `draw` 也接受開放報名，交給人選擇。人第一次只回答了一題，AI 沒有把其他建議值當成決定，而是再確認一次。實作子代理在驗證階段停滯 10 分鐘被中止（本機 `python` 是 Microsoft Store 空殼），主代理接手。接手後發現 A 的 `test_init_twice_keeps_demo_account_count` 失敗：它把所有含 `already exists, skipped` 的 log 都算成帳號數；沒有改 A 的測試，而是把本步驟對既有遊戲與賽事的 log 改成較準確的 `reused`。自己的兩個測試單獨跑會過、全部跑會失敗，原因是測試資料庫有併發測試提交的資料，改成只看示範資料自己的遊戲與操作紀錄。審查 14 筆：6 筆修正（包括測試與註解宣稱 savepoint 會撤銷資料，但實際上沒有東西可撤銷）、1 筆延後（保留資料庫超過 7 天會沿用過期賽事）、2 筆誤報、5 筆不處理
- 成熟度：L4（spec → 子代理實作 → 主代理驗證 → 多個審查者 → 測試）
- 證據：`spec-7-1-tournaments-demo-step.md` 的 Decisions、Implementation Notes、Review Triage Log；commit 未記錄
