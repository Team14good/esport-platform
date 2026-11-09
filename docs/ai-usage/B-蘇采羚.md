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

### 2026-11-04｜需求／設計｜Story 2.7 第一階段 spec：邀請裁判的後端

- Story／範圍：2.7 第一階段（分支 `story/2-7`，PR 未建立）
- 工具：Claude Code（Opus 5.5）＋ bmad-build
- 怎麼用：接續 11/2 的 spec 草稿，AI 查 planning 文件後提出兩個開放問題；實作後又提出兩個新問題
- AI 產出：`spec-2-7-referee-invitation.md` 的 Decisions 4 條、I/O 矩陣新增 2 列（主辦方接受 409、已結束／已取消 409）
- 人做了什麼：決定主辦方不能接受自己賽事的裁判邀請（沒有裁判時由主辦方代登）；已結束、已取消拒絕；第一階段就重新產生前端 client；已是裁判的人用過期連結維持 409
- 驗證：spec 經人核准後鎖定；決定都寫進 Decisions
- 問題與修正：AI 查遍 PRD、epics、架構、UX，確認文件沒有規定「主辦方能否當裁判」，才交給人決定。人的第一次回答提到「改由選手自己登錄比分」，與 FR-26 衝突，AI 沒有照做，而是先確認意思。AI 把人沒有回答的「範圍維持兩階段」自行寫進 Decisions，寫完後自己發現並刪除。草稿凍結區塊寫「第一階段不重新產生 client」，AI 實作後讀 CI 設定才發現這樣 CI 一定失敗（2.1、2.2 都有產生），由人改為要產生。草稿的遷移 `down_revision` 也已經過時（main 之後多了 4 支遷移）
- 成熟度：L3（AI 依既有規格產出 spec，規則由人決定）
- 證據：spec 的 Decisions

### 2026-11-04｜程式／程式生成｜Story 2.7 第一階段：裁判邀請資料表、5 支 API、is_referee／list_referees

- Story／範圍：2.7 第一階段（分支 `story/2-7`）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（實作子代理）
- 怎麼用：核准 spec 後，由不帶對話脈絡的實作子代理只依 spec 實作；主代理讀 diff 逐項核對
- AI 產出：`referee_invitation`、`tournament_referee` 兩張表與 1 支遷移；5 支 API；tournaments 6 個公開函式；`core.authz` 2 個裁判判斷函式；identity 只新增 `get_display_names`；重新產生 `frontend/src/client`（新增 382 行）；測試 2 個檔案
- 人做了什麼：核准 spec；實作中回答 2 個新問題
- 驗證：子代理回報 1489 個測試通過；主代理讀 diff 確認檢查順序與兩個決定都有實作，I/O 矩陣每列都有測試
- 問題與修正：子代理自己抓到 3 個錯誤：以 `rowcount` 判斷是否新增裁判，結果判斷錯誤、少寫操作紀錄，冪等測試抓到後改用 RETURNING；推進凍結時鐘 7 天後 access token 過期，改成重新登入；ruff format 順手改到別人的 2 個測試檔，已還原。實作期間 `story/2-7` 被快轉到新的 main，主代理產生審查 diff 時發現混入 PR #37、#38 的檔案，改成和 HEAD 比對
- 成熟度：L4（spec → 子代理實作 → 主代理依 diff 核對 → 自動測試）
- 證據：spec 的 Implementation Notes；commit 未記錄

### 2026-11-04｜測試／程式審查｜Story 2.7 第一階段三個審查者審查與修正

- Story／範圍：2.7 第一階段（分支 `story/2-7`）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（Blind Hunter、Edge Case Hunter、Verification Gap）
- 怎麼用：三個審查者各自只看 diff，主代理逐筆查證後分類
- AI 產出：21 筆發現；10 筆修正、1 筆延後、1 筆誤報、7 筆不處理，另 2 筆與其他筆重複（理由記在 spec 的 Review Triage Log）；測試增為 `test_referees.py` 35 個測試函式、`test_authz.py` 4 個
- 人做了什麼：未記錄（分類由 AI 完成，待組員在 PR 審查時確認）
- 驗證：修正後後端 1495 個測試全過、覆蓋率 97%；lint（mypy、ty、ruff）通過；Alembic 只有一個 head；前端 typecheck、build、Biome 通過
- 問題與修正：兩個審查者指出可能死結：接受邀請先以 FOR SHARE 鎖邀請，新增裁判時的外鍵檢查要對賽事列取 FOR KEY SHARE；重新產生邀請先以 FOR UPDATE 鎖賽事，再更新邀請，兩邊交叉等待。主代理查到 `lock_tournament` 確實是 FOR UPDATE，兩個外鍵都指向 `tournament`，判定成立。實作子代理在 spec 寫的「接受不鎖賽事就不會死結」是錯的，改成兩邊都先鎖賽事。原本的併發測試用 `sleep(0.5)` 判斷「另一邊在等鎖」並不可靠，改成查 `pg_stat_activity`。子代理自己承認，新增的反方向測試沒有直接重現舊程式的死結（要在 service 中間插入停點）。token 長度上限改變了 OpenAPI，client 又重新產生一次
- 成熟度：L4（多個審查者＋主代理查證＋測試驗證）
- 證據：spec 的 Review Triage Log、`deferred-work.md`
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

### 2026-11-04｜專案管理與流程／文件｜依 D 的審查補示範資料說明

- Story／範圍：7.1 tournaments 步驟（PR #42）的審查後續
- 工具：Claude Code（Opus 5.5），未經 BMAD
- 怎麼用：使用者問「所有留言都有看嗎」，AI 承認先前只看了開著的 PR、每則只讀前 200 字，補查今天有更新的 17 個 PR 全部留言（含行內），找出 PR #42 的 D 審查有兩點建議還沒處理
- AI 產出：README 示範資料段落更新（遊戲與示範賽事已存在、Demo 前 `docker compose down -v`）；`demo_data/__init__.py` 擴充說明新增「略過訊息不要用 `already exists, skipped`」；刪除已完成的 2.4 第二階段延後項目
- 人做了什麼：要求先做這個小 PR
- 驗證：ruff check、format 通過；只改說明文字
- 問題與修正：AI 前一次回報「所有留言都看過」時，實際只查了開著的 PR、截斷長度，也沒查行內留言與已合併 PR，漏掉 PR #42、#38 的審查內容；被使用者追問後才補查並修正
- 成熟度：L2（AI 產出文件修改，範圍由人決定）
- 證據：PR #42 的 D 審查；commit 未記錄

### 2026-11-05｜設計／介面約定｜Epic 6 disputes 模組介面約定（提議）

- Story／範圍：Epic 6 前置（6.1、6.2、6.4、6.5），CONTRIBUTING 6.5；分支 `docs/disputes-contract`
- 工具：Claude Code（Opus 5.5），未經 BMAD
- 怎麼用：AI 讀 epic-6-context、架構 D-5、competition 與 tournaments 約定，並直接查 disputes 骨架、competition 的場次狀態轉換表、registration 的報名狀態轉換表與 `core.storage`，寫出約定提議
- AI 產出：`contracts/disputes.md`（Appeal、Report 欄位；disputes 公開函式 11 個、API 11 支、錯誤碼、事件 4 個；B 在 competition 新增的 5 個函式與用到 D 的函式；registration 需要的 6 個函式，其中 2 個新增；6 個待確認事項）；`contracts/README.md` 加一列
- 人做了什麼：同意開 docs PR，待確認事項請 C、D、A 在 PR 回覆
- 驗證：未記錄（約定文件，待 C、D 審查）
- 問題與修正：AI 起初在約定裡寫「請 D 在 `MatchRead` 補上 `outcome`」，查 competition models 後發現欄位已存在，刪掉這一列；也查證 registration 的轉換表已允許四種報名狀態轉為 `disqualified`、competition 已允許申訴相關的場次轉換，把原本寫成「請確認」的兩項改為已確認
- 成熟度：L3（AI 依既有規格與程式產出介面，人與組員決定）
- 證據：`contracts/disputes.md`
### 2026-11-05｜需求／設計｜Story 2.7 第二階段 spec：S31 裁判管理與 S23 接受邀請

- Story／範圍：2.7 第二階段（分支 `story/2-7-ui`）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（Explore 子代理調查前端）
- 怎麼用：AI 依 epic-2-context、第一階段 spec 與延後項目寫 spec，列出 3 個開放問題（各附建議）
- AI 產出：`spec-2-7-s31-s23-referee-ui.md`（I/O 矩陣 16 列、Decisions 3 條）
- 人做了什麼：三題都選建議：接受後留在原頁並連到 S13、後端加 `accepting` 欄位（順便清掉第一階段延後項目）、產生新連結前先確認
- 驗證：spec 經人核准後鎖定
- 問題與修正：epic-2 context 之後有 C 的 commit 動到 planning 文件卻沒標 `Epic-Context: unaffected`；AI 查到它改的是候補遞補規則，epic-2 context 完全沒有這些內容，沿用現有 context 並寫進 Implementation Notes，沒有重新產生（避免與其他人的版本衝突）。調查時發現接受與預覽的回應都沒有 tournament_id，連不到 S2，交給人決定接受後的去處
- 成熟度：L3（AI 依既有規格產出 spec，人做決定）
- 證據：spec 的 Decisions、Implementation Notes

### 2026-11-05｜程式／程式審查｜Story 2.7 第二階段：S31、S23 畫面與 `accepting` 欄位

- Story／範圍：2.7 第二階段（分支 `story/2-7-ui`）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（實作子代理、Blind Hunter、Edge Case Hunter、Verification Gap）
- 怎麼用：子代理只依 spec 實作並在瀏覽器實測；三個審查者審 diff；主代理逐筆查證、交回子代理修正，最後自己跑完整驗證
- AI 產出：後端兩個 schema 新增 `accepting`＋4 種賽事狀態的測試；前端 S31、S23 兩頁、兩支路由、側欄「裁判」、`referee-queries.ts`；單元測試 1 個檔案（26 個測試）；重新產生 client
- 人做了什麼：核准 spec
- 驗證：前端 build、typecheck、Biome 通過，單元測試 62 個檔案、824 個全過；後端 1923 個全過、覆蓋率 97%，lint 通過，單一 head；重新產生的 client 與提交版本相同
- 問題與修正：子代理在瀏覽器實測時抓到單元測試漏掉的 bug：產生的 client 把 `null` 回應換成 `{}`，從未產生過邀請時 S31 顯示空白連結與「賽事已結束」，單元測試因 mock 成 `null` 而沒發現；改為有 `token` 才算有邀請，mock 也改成 `{}`。審查 19 筆：11 筆修正（公開頁連帶載入主辦方頁的程式、接受失敗後卡片沒更新、背景重抓失敗蓋掉成功畫面、賽事未載入前按鈕可按等），1 筆延後（S31 與 D 的 S30 各定義一次同一個裁判名單查詢 key），5 筆不處理，2 筆誤報。主代理驗證時第一次跑 `generate-client.sh` 因工作區沒有 `.env` 而沒有執行，輸出卻顯示「client unchanged」，AI 看到錯誤訊息後判定那次比對無效，改用 `COMPOSE_ENV_FILES` 指向主資料夾的 `.env` 重跑
- 成熟度：L4（spec → 子代理實作與實測 → 多個審查者 → 主代理驗證）
- 證據：spec 的 Review Triage Log、Implementation Notes；commit 未記錄

### 2026-11-07｜程式／程式審查｜審查 D 的 #56：Story 4.1 S27 抽籤按鈕與抽籤狀態

- Story／範圍：4.1 S27（D 的 PR #56，18 個檔案、+1459／-22 行；B 因 CODEOWNERS 的 `features/tournaments/` 被指定審查）
- 工具：Claude Code（Opus 5.5）＋ bmad-code-review（Blind Hunter、Edge Case Hunter、Verification Gap、Acceptance Auditor）
- 怎麼用：以 PR 的 spec（`spec-4-1-s27-draw-button.md`）與 `contracts/competition.md`、`epic-4-context.md` 為依據跑四個審查者；主代理逐筆對照程式核對、篩選，擬好審查意見，人確認後送出 approve
- AI 產出：四個審查者共 26 點（Blind Hunter 13、Acceptance Auditor 6、Edge Case Hunter 7、Verification Gap 0）；核對後留 3 點（中 1：停留在 S27 時抽籤狀態不會自動更新；低 2：合約的鎖順序與程式不一致、draw-status 那列少寫 503），排除 23 點；一份審查意見
- 人做了什麼：決定審查整份 diff（不只 tournaments 部分）；確認審查意見後送出 approve
- 驗證：每個留下的發現都回到程式與合約核對；Verification Gap 確認 diff 的每個改動都有會失敗的測試
- 問題與修正：審查者有數點誤判，主代理核對後排除：Blind Hunter 說抽籤後公開頁面快取會停在「尚未抽籤」，但專案的 QueryClient 預設 staleTime 為 0，換頁就重抓；Blind Hunter 也說合約沒寫這個 GET 會鎖賽事，實際合約有寫「先 `lock_tournament`」；Edge Case Hunter 說 `can_draw=false`、`reason=null` 會讓按鈕無說明地停用，以及主辦方在兩次讀取間被換人，後端都不會產生這種情況。工作階段中途中斷，Edge Case Hunter 沒跑完，重建 diff 確認程式沒變後重跑。bmad-code-review 的步驟要把發現寫進 spec 並改 sprint-status，但 PR 是 D 的，主代理改為只擬審查意見，不動別人的分支
- 成熟度：L4（多個審查者並行，主代理逐筆核對，人在送出前確認）
- 證據：PR #56 的審查意見（B，APPROVED，2026-11-07）

### 2026-11-07｜程式／程式審查｜審查 D 的 #57：6.2／6.5 前置的 competition 公開函式

- Story／範圍：6.2、6.5 前置（D 的 PR #57，5 個檔案、+802／-8 行；B 是這三個函式的呼叫端、disputes 約定 #55 的作者）
- 工具：Claude Code（Opus 5.5）＋ bmad-code-review（Blind Hunter、Edge Case Hunter、Verification Gap、Acceptance Auditor）
- 怎麼用：以 `spec-6-x-competition-hooks.md`、`contracts/disputes.md`、`contracts/competition.md` 為依據跑四個審查者；主代理對照 B 自己的 disputes 約定與程式逐筆核對，擬審查意見，人確認後送出 approve
- AI 產出：四個審查者共 16 點（Blind Hunter 12、Edge Case Hunter 4、Verification Gap 0、Acceptance Auditor 0 點違反、4 點備註）；核對後留 2 點低度約定文字建議（`get_replay_window` 的場次歸屬與主辦方由呼叫端檢查、`unassign_referee_if_member` 的狀態前提沒有在程式裡擋），另整理出 B 做 6.2 時要注意的呼叫順序（`check_replay_time` 要在 `clear_for_replay` 之前）
- 人做了什麼：確認審查意見後送出 approve
- 驗證：每個留下的發現都回到程式與約定核對；Verification Gap 確認改動都有會失敗的測試
- 問題與修正：Blind Hunter 說 `list_matches(fresh=True)` 會用資料庫的值蓋掉呼叫端還沒 flush 的修改，主代理查 `repository.list_matches` 與 Session 設定後判定為誤判：查詢前 autoflush 會先寫入；Edge Case Hunter 提的「季軍賽作廢時仍限制準決賽重賽時間」是 4.3 `_reschedule_window` 既有的行為，不是這個 PR 造成的
- 成熟度：L4（多個審查者並行，主代理逐筆核對，人在送出前確認）
- 證據：PR #57 的審查意見（B，APPROVED，2026-11-07）

### 2026-11-07｜需求／一致性檢查｜比對已實作的功能與原始規劃文件

- Story／範圍：Epic 1～5、7 已完成或進行中的 Story（1.1～1.5、1.7、1.8、2.1、2.2、2.4、2.7、3.1～3.4、3.6、4.1、4.3、4.4、4.6、5.1～5.6、5.8、7.1、7.2）與 Epic 6 現況
- 工具：Claude Code（Opus 5.5）＋三個唯讀子代理（依 Epic 分工）
- 怎麼用：子代理以 `epics.md`（套用期中版調整）、PRD、`EXPERIENCE.md`、架構文件為準，逐條對照 main 的程式與測試，區分「符合／部分符合／不符／未實作／有意偏離（已記錄）」；主代理抽查關鍵發現
- AI 產出：每個 Story 的 AC 對照表；7 個沒有追蹤的落差（S27 缺報名截止與優先期結束倒數、S12 缺下一場與優先期倒數、抽籤順延沒有提示主辦方、頒獎台與名次標記未做、比分登錄沒有併發測試、7.2 沒有操作紀錄斷言）、1 個過時的延後項目（5.2 第二階段）
- 人做了什麼：提出要檢查「做的東西跟原本文件是否相符」
- 驗證：主代理抽查 4 項：前端沒有 `podium` 元件、S12 沒有下一場資料、前端沒用到 `delayed_rounds`、S27 沒有 `Countdown`，都屬實；7 個落差尚未寫入 deferred-work
- 問題與修正：找到 B 自己負責的 2.4 有一條 AC（S27 倒數）在 2.2 第二階段 spec 寫「不做」、2.4 spec 只做 S2，兩邊都沒接到，Story 卻已標 done；這是流程上的缺口，不是 AI 這次的錯誤
- 成熟度：L3（AI 依既有規格逐條比對，人決定後續處理）
- 證據：未記錄（結果只在對話中，尚未寫入 deferred-work）

### 2026-11-07｜程式／程式生成｜Story 2.4 補遺：S27 報名開始、優先期結束、報名截止倒數

- Story／範圍：2.4 補遺（分支 `story/2-4-s27-countdown`，spec `_bmad-output/implementation-artifacts/spec-2-4-s27-countdowns.md`）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（epic context 重新產生子代理、實作子代理、Blind Hunter、Edge Case Hunter、Verification Gap）
- 怎麼用：由文件比對找到的落差開 spec；主代理調查後寫 spec 並列出 2 個需要人決定的問題；子代理依 spec 實作；三個審查者審 diff；主代理逐筆核對、交回子代理補測試，最後自己在容器跑完整驗證
- AI 產出：`OrganizerTournamentOverview.tsx` 新增私有元件 `OrganizerStatusCountdowns`（沿用 2.4 的 `Countdown`、`registrationEndVariant`、`REGISTRATION_OPENING_TEXT`，不改 S2）；`organizer-tournaments.test.tsx` 新增〈S27 狀態倒數〉14 個測試，涵蓋 I/O 矩陣 7 個情境；sprint-status 註解；重新產生 `epic-2-context.md`（只多一行時間格式）
- 人做了什麼：決定尚未開放時 S27 也顯示「報名開始」倒數（照 EXPERIENCE.md）、優先期倒數歸零後直接隱藏（避免 2 分鐘後誤報逾時）；核准 spec
- 驗證：容器內 Biome 檢查 244 個檔案通過、型別檢查 0 錯誤、單元測試 63 個檔案 845 個全過；三個審查者共 15 點，3 點補測試（重抓失敗不重試也不換錯誤頁、尚未開放不顯示優先期倒數、徽章斷言檢查實際色調），12 點不處理（4 點誤判，8 點低度），0 點延後；375px 手動檢查未做
- 問題與修正：審查找出測試「看起來有驗、其實不會紅」的地方：倒數歸零後重抓的錯誤處理（`retry: false`、`.catch`）沒有任何失敗的測試，子代理補測試後以暫存副本拿掉 `retry: false` 確認新測試會失敗；徽章斷言只檢查屬性存在、不檢查值。Blind Hunter 建議把倒數規則搬到 `status.ts`，主代理判定會改到 S2，違反 spec 的 Never 而不採用。子代理第一次跑完整單元測試時有 1 個與本次無關的測試逾時，單獨重跑與全套重跑都通過；主代理最後重跑全套也通過。bmad-build 最後一步要 commit，依 CLAUDE.md「除非使用者要求，不要 commit」沒有執行
- 成熟度：L4（spec → 子代理實作 → 多個審查者 → 主代理核對與完整驗證，人在 spec 決策點介入）
- 證據：spec 的 Decisions、Implementation Notes、Review Triage Log；commit 未建立

### 2026-11-08｜程式／程式審查｜審查 D 的 #60：S27 抽籤狀態與 6.x 前置函式的審查後續

- Story／範圍：4.1 S27、6.2／6.5 前置（D 的 PR #60，9 個檔案、+394／-22 行；處理 B 與 A 在 #56、#57 的建議）
- 工具：Claude Code（Opus 5.5）＋ bmad-code-review（Blind Hunter、Edge Case Hunter、Verification Gap、Acceptance Auditor）
- 怎麼用：以 `spec-4-1-followup-review.md`、前兩支 spec 與 competition、disputes 約定為依據跑四個審查者；主代理對照 B 先前的建議與自己的 #62、disputes 約定核對，擬審查意見，人確認後送出 approve
- AI 產出：四個審查者共 17 點（Blind Hunter 11、Edge Case Hunter 1、Verification Gap 0、Acceptance Auditor 5）；核對後留 1 點低度建議（抽籤狀態的 queryKey 只有賽事 id，狀態變成報名截止後最多沿用 30 秒前的預估）與 1 點給 B 自己的提醒（`disputes.md` 第 124 行沒寫 `unassign_referee_if_member` 新的 `ValueError` 前提，6.5 要在 `confirm_walkover`／`confirm_match` 之前呼叫）
- 人做了什麼：確認審查意見後送出 approve
- 驗證：Verification Gap 確認每個改動拿掉後都有測試會失敗；留下的發現都回到程式與約定核對
- 問題與修正：Edge Case Hunter 的 queryKey 發現是單看 #60 看不出的跨 PR 互動，主代理對照 B 自己的 #62（報名截止歸零後重抓賽事）確認會發生；Acceptance Auditor 指出 competition 約定改了前提、但呼叫端的 disputes 約定沒同步，主代理判斷這是 B 自己的檔案，記為 6.5 的待辦而不要求 D 修改（Never 條款不允許 D 改 disputes）
- 成熟度：L4（多個審查者並行，主代理逐筆核對，人在送出前確認）
- 證據：PR #60 的審查意見（B，APPROVED，2026-11-08）

### 2026-11-08｜程式／debug｜PR #62 審查後續：狀態改變後重抓 S27 抽籤狀態

- Story／範圍：2.4 補遺（PR #62，D 審查「合併前請先修 1」）
- 工具：Claude Code（Opus 5.5）
- 怎麼用：AI 讀 D 的審查意見，對照剛合併的 #60 判斷兩種情況哪一種還會發生，再依 D 建議的做法修正並補測試
- AI 產出：`refetchAfterCountdown` 在重抓到的狀態與原本不同時 invalidate 抽籤狀態；2 個新測試（開放報名 → 報名截止、尚未開放 → 開放報名）
- 人做了什麼：決定照 D 的第 1 點修正，其他建議先不做
- 驗證：容器內 Biome 247 個檔案、型別檢查 0 錯誤、單元測試 64 個檔案 868 個全過；變異檢查（拿掉 invalidate）讓「開放報名 → 報名截止」的新測試失敗
- 問題與修正：D 列的兩種情況裡，「尚未開放 → 開放報名」在 #60 合併後已不會發生（尚未開放時不送出抽籤狀態查詢），變異檢查也證實這個測試不靠修正就會過，所以 PR 說明據實寫明只有後一種是這次修正擋下的。全套測試第一次有 1 個 S30 測試逾時，AI 查出是本機容器映像裡的 `vitest.config.ts` 是舊版（預設 5 秒、沒有 15 秒設定），掛上目前的設定檔後全過，不是程式錯誤
- 成熟度：L3（AI 依審查意見與既有規格修正，人決定範圍）
- 證據：spec-2-4-s27-countdowns.md 的 Implementation Notes；PR #62

### 2026-11-09｜程式／程式生成｜Story 6.1 提出申訴

- Story／範圍：6.1（分支 `story/6-1`，Draft PR #63，spec `_bmad-output/implementation-artifacts/spec-6-1-file-appeal.md`）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（調查子代理、實作子代理、Blind Hunter、Edge Case Hunter、Verification Gap）
- 怎麼用：以 B 自己的 disputes 約定（#55）與 epic-6 context 寫 spec，列出 1 個需要人決定的問題；子代理依 spec 實作前後端；三個審查者審 diff；主代理逐筆核對、交回子代理修正，最後自己在容器跑後端與前端全套
- AI 產出：`appeal` 資料表與遷移；`file_appeal`、`get_appeal_state`、`open_appeal_attachment` 與三支 API；competition 新增 `mark_appealed`（新檔 `appeals.py`，`service.py` 只新增公開函式）；前端 `features/disputes/` 的 `AppealPanel`、`AppealDialog`、queries，S4 只加掛載點；約定 `disputes.md`、`competition.md` 依分工更新；後端測試 3 個新檔（含兩條真實連線的併發測試），前端 1 個新檔並在 `match-route.test.tsx` 補路由層測試
- 人做了什麼：與 D 協議 Epic 6 分工（competition 端的 4 個函式交給 D）；決定 S4 由 B 在 6.1 一併掛；核准 spec
- 驗證：後端 lint（mypy 70 個檔案無問題、ruff 通過）、全套 2161 passed、覆蓋率 97%；前端 Biome 251 個檔案、型別檢查 0 錯誤、單元測試 65 個檔案 868 個全過；三個審查者共 26 點，8 點修正、1 點延後（取消賽事後仍可申訴，期中 2.6 擱置走不到）、17 點不處理（含 6 點誤判）；375px 手動檢查未做
- 問題與修正：審查找出「看起來有驗、其實不會紅」的地方：router 在 commit 失敗時刪附件、S4 路由是否真的掛上申訴入口，都沒有任何測試，補上後拿掉對應程式會失敗。AI 實作的說明清理去掉所有控制與格式字元，會丟掉 tab、拆散 ZWJ 表情（申訴是證據，存下的文字會和隊長輸入不同），改成只去控制字元與雙向控制字元。第一隊送出後佔位資料讓舊的可按按鈕閃回，改成佔位期間停用，子代理拿掉修正確認新測試會失敗。審查員有誤判被主代理排除，例如「第二隊送出後不會重抓」（S4 的 refresh 會 invalidate 整場的查詢前綴）、「期限到了按鈕仍可按」（倒數歸零會觸發 refresh）。子代理第一次跑後端全套時，併發測試提交的操作紀錄（只增不改、刪不掉）讓別的測試計數多 1，改為只計該場次後通過。另外 frozen 區塊寫隊長判斷「經 `registration_port.is_captain`」，但那是 competition 內部檔案、架構測試不允許 disputes 匯入，實作改呼叫 `registration.service.is_captain`，已記在 Implementation Notes 待使用者確認
- 成熟度：L4（spec → 子代理實作 → 多個審查者 → 主代理核對與完整驗證，人在分工與 spec 決策點介入）
- 證據：spec 的 Decisions、Implementation Notes、Review Triage Log；Draft PR #63；commit 未建立

### 2026-11-09｜程式／程式審查｜審查 C 的 #64：Story 6.4 提出檢舉

- Story／範圍：6.4（C 的 PR #64，28 個檔案、+3683／-80 行；B 是 tournaments 負責人，也是 6.5 `resolve_report` 的實作者）
- 工具：Claude Code（Opus 5.5）＋ bmad-code-review（Blind Hunter、Edge Case Hunter、Verification Gap、Acceptance Auditor）
- 怎麼用：以 `spec-6-4-file-report.md`、epic-6 context 與 disputes 約定跑四個審查者，另請 Acceptance Auditor 從 6.5 的角度看 `Report`、`ReportRead`；主代理核對後擬審查意見，並用 `git merge-tree` 實際試合 #63 與 #64 列出衝突檔案，人確認後送出 approve
- AI 產出：四個審查者共約 23 點（Blind Hunter 13、Edge Case Hunter 2、Verification Gap 1、Acceptance Auditor 4 點加 6 點 6.5 備註）；核對後留 4 點低度建議（遷移進 main 前加 `reported_team_id` 索引、S2 掛載點的路由層測試、約定兩處仍寫 `ensure_captain`、存檔不見的 404 沒有測試）；6.5 的設計備註（多筆檢舉對同一隊、`ReportRead` 缺報名狀態、`resolve_report` 要先鎖賽事）留給 B 自己
- 人做了什麼：確認審查意見後送出 approve
- 驗證：Acceptance Auditor 逐條核對 spec 的 AC、Boundaries 與 I/O 矩陣；`git merge-tree` 確認 10 個衝突檔案與兩支遷移接在同一個 head
- 問題與修正：Edge Case Hunter 提的「隊長中途換人後一直 403」，主代理判斷要等期中擱置的 3.11（隊員異動）才會發生而排除；Blind Hunter 對 C 的 spec 與 AI 紀錄寫法的意見（任務勾選、計數）屬 C 自己的文件，不列入審查意見
- 成熟度：L4（多個審查者並行，主代理逐筆核對並實際試合，人在送出前確認）
- 證據：PR #64 的審查意見（B，APPROVED，2026-11-09）

### 2026-11-09｜專案管理與流程／進度盤點與合併衝突處理｜Story 6.5 分支合併 main

- Story／範圍：6.5（PR #65 草稿，分支 `story/6-5`，工作樹 `espory-6-5`）
- 工具：Claude Code（Opus 5.5）
- 怎麼用：先請 AI 依 sprint-status、CONTRIBUTING 分工表、`gh pr list`、各工作樹的 git 狀態整理 Epic 6 各 Story 的負責人與進度。之後請它把 main 合併進 6.5：解衝突、跑測試，經人同意後 commit 並推上去
- AI 產出：
  - 盤點：整理出 6.1、6.2、6.4、6.5 的負責人與狀態，並指出 sprint-status 與實際情況不一致，以及 6.2 有約 780 行還沒 commit
  - 第一次合併（#61、#64、#66、#67）：解 2 個衝突（`sprint-status.yaml`、`registration/service.py`，兩邊都保留），在 `traceability.yaml` 補上 6.5 的 2 個測試檔
  - 第二次合併（含 6.1 的 #63）：解 `sprint-status.yaml` 衝突，順手把 6-1 改成 `done`
- 人做了什麼：決定先處理 6.5（6.1 收尾另外處理），同意兩次合併的 commit 與推送
- 驗證：
  - 第一次合併後，全部後端測試 1 failed／2218 passed。失敗的是 #61 新增的 `test_every_test_file_is_listed`，補上 2 列後 2219 passed
  - 第二次合併後 2276 passed
  - 推上去後，`gh pr view 65` 顯示 `MERGEABLE`
- 問題與修正：
  - AI 第一次用 Python heredoc 解衝突時，腳本其實沒有執行，檔案沒變，也沒有報錯。AI 回頭讀檔才發現衝突標記還在，改用 Edit 工具。
  - 合併 main 前不知道 #61 規定每個測試檔都要寫進 `traceability.yaml`，跑完全部測試才發現。
  - 另一個工作階段傳來的交接訊息說 6-5 「合併到一半、有衝突」，AI 用 `git status` 與 `MERGE_HEAD` 核對後，確認那只是自己解好但還沒 `git add` 的狀態。
- 成熟度：L3（AI 依專案規則合併並跑全部測試，commit 與推送都由人決定）
- 證據：commit f96d871、ee0222e，PR #65

### 2026-11-09｜程式／程式生成｜Story 6.5 第一階段：對手未定時拒絕取消資格

- Story／範圍：6.5 第一階段（PR #65 草稿）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（Blind Hunter、Edge Case Hunter、Verification Gap）
- 怎麼用：依 D 在 #65 的決定實作「對手尚未確定時回 409 `DISQUALIFY_OPPONENT_PENDING`、不改任何資料」，並以 `origin/main..` 的完整 6.5 差異跑三個審查者
- AI 產出：
  - 原本拋 `NotImplementedError` 的地方改成 409，2 個測試改為也斷言操作紀錄與 outbox 事件都不變
  - spec 情況表與 Decisions、contract、deferred-work 隨之更新
  - 審查共 13 點，核對後修正 4 點：
    - （高）被取消資格的隊伍已報到時，報到紀錄會殘留，棄權 worker 會一直卡在該場。新增 `repository.delete_check_in`
    - （中）頂替後沒有發 `MatchOpponentsDecided`，兩隊收不到新對手的通知
    - （中）沒有兩場以上勝場的頂替測試，補 16 隊的 2 個測試
    - （低）contract 缺 `REGISTRATION_INVALID_TRANSITION`
  - 另外延後 1 點（未驗證），排除 8 點
- 人做了什麼：spec 的情況表在凍結區塊內，人同意依 D 的決定修改，其餘由 AI 完成
- 驗證：
  - lint（ty、ruff）通過
  - 全部後端測試 2279 passed（新增 3 個），覆蓋率 97%，覆蓋率門檻通過
- 問題與修正：
  - 第一階段原本的實作漏了兩件事：頂替時清除報到紀錄、發對手確定的事件。這次的審查者找出來；Edge Case Hunter 和 Blind Hunter 都提到，AI 對照 `forfeit.judge_forfeit` 確認報到殘留會讓棄權 worker 拋 `ValueError`。
  - AI 跑 `scripts/test.sh` 時帶了 `-q` 等參數，結果覆蓋率門檻被設成 0，前兩次全部測試其實沒檢查到門檻。AI 從輸出的 `--fail-under=0` 發現後，改成不帶參數重跑。
  - 審查者另有 8 點是誤判，例如「已退賽的敗隊會被放回對戰表」：目前沒有程式會把報名改為退賽。這些都在 spec 的 Review Triage Log 記下排除理由。
- 成熟度：L4（固定流程實作，三個審查者並行，主代理逐筆核對並修正，全部測試與覆蓋率門檻驗證，人只在凍結區塊的修改做決定）
- 證據：commit 7cd8eb2，PR #65，`_bmad-output/implementation-artifacts/spec-6-5-disqualify.md`
