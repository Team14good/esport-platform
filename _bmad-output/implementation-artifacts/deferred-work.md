# Deferred Work

- source_spec: `_bmad-output/implementation-artifacts/spec-1-2-flow-frontend-shell-and-theme.md`
  summary: DESIGN.md 的部分色票對比不足：淺色 primary #0891B2 搭配白字約 3.7:1，未達 WCAG AA 一般文字 4.5:1；深色 `status-eliminated` #4B5370 在背景 #070A14 上約 2.6:1，連非文字元素的 3:1 都不到。
  evidence: Story 1.2 照 DESIGN.md frontmatter 原樣寫入 `frontend/src/index.css`，數值與設計稿一致，所以問題出在設計稿本身。需要由 UX（bmad-ux）調整色票，例如加深淺色 primary，或讓 primary 按鈕在淺色時改用深色字，再同步更新 `index.css`。
- source_spec: `_bmad-output/implementation-artifacts/spec-1-3-email-signup-and-verification.md`
  summary: worker 的事件分派與寄信遇到「每次都失敗」的項目時（不是 payload 格式錯誤，而是持續性的資料庫錯誤或外鍵錯誤），同一筆會一直排在最前面，擋住後面所有事件或信件（未證實；若成立為 medium）。
  evidence: `dispatch_outbox` 與 `send_next_email` 每次都取最舊的一筆，失敗時交易回滾、項目不變；`outbox_event` 沒有 attempts 或 dead-letter 欄位，`_compose` 的資料庫錯誤也可能讓 `attempts` 無法寫入。Story 1.3 的事件只有 `VerificationEmailRequested`，payload 一定合法、帳號不可刪除，所以沒能證明實際會發生。要確認是否成立：用 Story 1.6 的新事件類型，或刻意製造持續性的資料庫錯誤來觀察。若成立，在 1.6 建立事件類型登錄機制時，加上分派次數上限與 dead-letter 標記。
- source_spec: `_bmad-output/implementation-artifacts/spec-1-1-official-template-project-skeleton.md`
  summary: `audit_log` 的「只增不改」只靠資料庫 trigger；應用程式、worker、alembic 都以資料表擁有者（預設 postgres 超級使用者）連線，可以停用或刪除 trigger，AD-9 沒有真正的強制力。
  evidence: 2026-10-24 Story 1.1 Code Review（Blind Hunter）。要強制，需另建非擁有者的應用程式角色，對 `audit_log` 只給 INSERT／SELECT，並撤銷 UPDATE／DELETE／TRUNCATE；遷移仍以擁有者身分執行。牽涉 compose、`.env` 與連線設定，適合在部署或安全強化時一併處理。
- source_spec: `_bmad-output/implementation-artifacts/spec-1-4-login-logout-account-identity-switcher.md`
  summary: `POST /api/v1/access-tokens` 沒有頻率限制或連續失敗鎖定；每次請求都會跑一次 argon2，可被用來暴力猜密碼或耗用 CPU（規劃文件沒有相關規則，嚴重度未證實；若部署到公開網路，為 medium）。
  evidence: 2026-10-27 Story 1.4 Code Review（Blind Hunter）。Story 1.4 調查時確認 PRD、架構、epics 都沒有鎖定或頻率限制的規則。要處理時，先由 PM／架構決定規則（例如同一 Email 或 IP 每分鐘上限），再在登入端點實作，並決定是否要以 429 回應。
- source_spec: `_bmad-output/implementation-artifacts/spec-1-7-apply-to-be-organizer.md`
  summary: S1 的 Page banner「想辦賽事？申請成為主辦方」（→ S15）延後；目前進入 S15 只有身分切換器的「申請成為主辦方」。
  evidence: Story 1.7 Decisions：S1 目前仍是佔位頁（賽事列表在 Epic 2），banner 沒有地方放。做 S1 賽事列表時（Epic 2）在頂欄下方、內容區最上方加上 Page banner，對已登入的非主辦方帳號顯示，連到 `/organizer/apply`；樣式見 DESIGN.md〈頁頂橫幅〉。

## Deferred from: code review of spec-1-5-forgot-reset-password.md (2026-10-28)

- source_spec: `_bmad-output/implementation-artifacts/spec-1-5-forgot-reset-password.md`
  summary: `POST /api/v1/password-reset-emails` 沒有頻率限制：可以對同一個 Email 大量寄信灌爆收件匣，而且每次申請都會作廢對方手上的重設連結，讓本人無法完成重設。
  evidence: 2026-10-28 Story 1.5 Code Review（Edge Case Hunter）。Story 1.5 的 Never 明定不做頻率限制（與登入相同）。處理時與登入的頻率限制一起由 PM／架構決定規則（例如同一 Email 每小時上限、同一 IP 上限），並決定超過時是否仍回相同的 202 以免透露帳號是否存在。
- source_spec: `_bmad-output/implementation-artifacts/spec-1-5-forgot-reset-password.md`
  summary: `tests/test_migrations.py` 的測試資料庫每次從空表升級，測不到「既有帳號升級後拿到 0」（低；若遷移檔被改錯，為 medium：有資料的資料庫升級失敗，或舊登入全部失效）。`compare_server_default` 已在 PR #94 開啟，這筆只剩資料升級的部分。
  evidence: 2026-10-28 Story 1.5 第二輪 Code Review（Verification Gap）；PR #94 審查要求保留本半句。處理時另寫一支「升到上一版、插入帳號、再升到 head」的測試。
- source_spec: `_bmad-output/implementation-artifacts/spec-1-5-forgot-reset-password.md`
  summary: 「重設信只寄 Email、不建立站內通知」目前沒有任何斷言（1.5 第一輪審查移除了 `"notification" not in metadata.tables`）；Story 1.6 加入站內通知後，若 `dispatch_event` 誤替 `PasswordResetRequested`（或 `VerificationEmailRequested`）建立站內通知，現有測試照樣通過。
  evidence: 2026-10-28 Story 1.5 第二輪 Code Review（Blind Hunter、Acceptance Auditor）。目前還沒有 notification 表，無從斷言。Story 1.6 建立站內通知時，在 `tests/notifications/test_email_delivery.py` 的重設信與驗證信測試補上「站內通知筆數不變」的斷言。
## Deferred from: spec-3-2-player-registration-info.md 第一段 (2026-10-30)

- source_spec: `_bmad-output/implementation-artifacts/spec-3-2-player-registration-info.md`
  summary: 上傳 API 沒有請求大小上限，5 MB 在 multipart 整個收完後才由 `core.storage` 檢查。
  evidence: 2026-10-30 Story 3.2 第一段 Code Review（Blind Hunter）。Starlette 會先把整個 body spool 到暫存檔，超大請求仍會被完整接收；第二段建 multipart API 時要決定請求大小上限（例如檢查 `Content-Length`）（medium）。

## Deferred from: Story 5.2（S4 申訴期區塊，2026-10-30）

- source_spec: `_bmad-output/implementation-artifacts/spec-5-5-confirm-advance.md`
  summary: `confirm_walkover` 不檢查空缺方是否真的確定不會有隊伍，6.5 呼叫前要自己確認（未驗證，若為真屬 medium）。
  evidence: Edge Case Hunter：空缺方的來源場次還沒定案時就以輪空確認，來源的勝隊之後會發現下一場已定案而被丟掉。要確認 6.5 的呼叫時機，或在 `confirm_walkover` 用 progression 的來源推導擋下。

- source_spec: `_bmad-output/implementation-artifacts/spec-5-5-confirm-advance.md`
  summary: 6.2 更正已結束賽事或季軍賽已開打後的準決賽時，`VoidMatch`、名次與賽事狀態怎麼處理還沒定（未驗證，若為真屬 medium）。
  evidence: `_void` 只能從待開打轉 voided；`_finish` 對已結束的賽事不再動作，但名次從場次重算，會和 `tournament.podium` 操作紀錄不一致。6.2 實作時要決定規則並補測試。

- source_spec: `_bmad-output/implementation-artifacts/spec-5-1-check-in-backend.md`
  summary: （低）兩隊同時報到只以先後兩次請求與唯一鍵測試，沒有在兩條真實資料庫連線上測併發。
  evidence: 測試環境所有 session 共用同一條連線與交易，無法製造真正的併發。若之後測試架構支援多連線，補一個兩隊同時 POST 的測試。
- source_spec: `_bmad-output/implementation-artifacts/spec-4-3-schedule-rules.md`
  summary: 4.3 第二階段的改時間 service 呼叫 `reschedule_window`／`check_reschedule` 時，準決賽的 `next_match_at` 要傳決賽與季軍賽中較早的那一場。
  evidence: A 在 #5 的審查：8 強 10:00、準決賽 12:00、決賽 16:00、最小間隔 85 分，先把季軍賽改到 14:00、再把準決賽改到 13:00 都會被允許，但準決賽最早 14:25 才結束。`schedule.py` 只收一個 `next_match_at`，規則（不晚於兩隊要去的下一場）要由呼叫端選對場次；docstring 已註明。

- source_spec: `_bmad-output/implementation-artifacts/spec-2-4-public-tournament-pages.md`
  summary: （低）公開賽事列表 `GET /tournaments` 沒有分頁或上限，未登入的請求一次取回所有賽事（含已結束、已取消）。
  evidence: 2026-11-02 Story 2.4 第一輪審查（Blind Hunter、Edge Case Hunter）。期中賽事數量少；賽事累積後在 S1 改為分頁（沿用 1.8 的分頁格式）或只回最近的已結束賽事。
- source_spec: `_bmad-output/implementation-artifacts/spec-2-4-public-tournament-pages.md`
  summary: S2 總覽「開放報名」時要顯示「已正取隊數／名額」（EXPERIENCE.md 狀態表），2.4 只顯示名額；需要 registration 提供正取隊數的公開函式。
  evidence: 2026-11-02 Story 2.4 第二輪審查（Blind Hunter）。spec 的 Never 明定不做；由 C 的 3.x 提供計數後，在 S2 總覽補上。

## Deferred from: spec-2-4-status-badge-and-organizer-banner.md (2026-11-03)

- source_spec: `_bmad-output/implementation-artifacts/spec-2-4-status-badge-and-organizer-banner.md`
  summary: Story 2.4 第二階段第 3 項：S1 空狀態「目前沒有公開的賽事。」對主辦方另顯示「建立賽事」，連到 2.2 第二階段的 S26（`/organizer/tournaments/new`）（low）。等 PR #31 合併後再做。
  evidence: 2026-11-03 使用者決定 2.4 第二階段先只做狀態徽章與申請主辦方 banner；S26 在 PR #31，尚未合併。上方 source_spec 為 `spec-2-4-public-tournament-pages.md` 的「Story 2.4 第二階段」那筆列了三項，其中狀態徽章、申請主辦方 banner 兩項已由 `spec-2-4-status-badge-and-organizer-banner.md` 完成，只剩本項；那筆依使用者指示保留不刪。
  summary: （低）`PageBanner` 的 `action` 只支援 `onClick`，S1「申請成為主辦方」按鈕以程式導向，不能中鍵開新分頁或複製連結；需要 A 為 `PageBanner` 新增連結型的 action。
  evidence: 2026-11-03 Story 2.4 第二階段審查（Blind Hunter）。`PageBanner.tsx` 是 A 的元件，本 Story 只 import 不修改。
## Deferred from: spec-3-2-player-registration-info-2.md (2026-11-03)

- source_spec: `_bmad-output/implementation-artifacts/spec-3-2-player-registration-info-2.md`
  summary: 上傳 API（`PUT /teams/{team_id}/members/me/profile`）仍沒有請求大小上限；上面第一段留下的同一項再次延後（medium）。
  evidence: 第二段 spec 的 Never 明定「不做請求大小上限」：`save_image` 邊讀邊擋 5 MB，超過的檔案不會存下，但 Starlette 仍會先把整個 multipart body spool 到暫存檔。只靠 `Content-Length` 擋不住 chunked 傳輸，要在 ASGI middleware 或反向代理（例如 `client_max_body_size`）處理，屬部署層的決定，不在本 Story 範圍。
- source_spec: `_bmad-output/implementation-artifacts/spec-4-6-bracket-page.md`
  summary: S2 在「賽程已公布」「進行中」時應以「對戰表」為預設分頁（epics 4.6 AC、EXPERIENCE.md 狀態表），4.6 第二階段沒有做；目前 `/tournaments/$tournamentId` 固定顯示總覽，觀眾要自己點「對戰表」。
  evidence: 2026-11-03 使用者決定（spec Decisions 1A）交給 B 決定做法。「總覽」分頁本身連到 `/tournaments/$tournamentId`，直接導向會讓總覽點不回去。可行做法：總覽改用新網址（例如 `/overview`），`/tournaments/$tournamentId` 依狀態導向 `/bracket` 或總覽；或 S1 列表在這兩個狀態直接連到 `/bracket`（外部分享連結仍落在總覽）。兩者都要改 B 的 `TournamentPage`／`TournamentTabs`／`TournamentList`。

## Deferred from: Story 7.1 第二階段 competition 步驟（2026-11-03）

- source_spec: `_bmad-output/implementation-artifacts/spec-2-2-organizer-tournament-ui.md`
  summary: （低）主辦方賽事清單的查詢在兩處各定義一次：`features/tournaments/organizer-queries.ts` 的 `myTournamentsQueryOptions` 與 C 的 `features/registration/CreateTeamEntry.tsx` 的 `organizerTournamentsQueryOptions`，都用查詢鍵 `["tournaments","organizer","list"]`；之後只改其中一邊（例如 `queryFn` 或回傳型別），兩邊的快取會互相污染。
  evidence: 2026-11-03 A（@max930000）在 PR #31 的審查。處理時請 C 把 `CreateTeamEntry.tsx` 改成 import `myTournamentsQueryOptions`，刪掉自己的定義（registration 模組只新增 import，不改 tournaments 的檔案）。

## Deferred from: spec-5-2-appeal-countdown-and-banner-link.md (2026-11-04)

- source_spec: `_bmad-output/implementation-artifacts/spec-5-2-appeal-countdown-and-banner-link.md`
  summary: B 的 `OrganizerApplyBanner.tsx`：S1「申請成為主辦方」改用 `PageBanner` 新增的連結型 action（`action: { label, to: "/organizer/apply" }`），就能中鍵開新分頁、複製連結（low）。
  evidence: 2026-11-04 A 已為 `PageBanner` 新增 `to`；使用者決定不改 B 的既有函式，交給 B。改完後 S1 的測試要從按鈕改成連結。

## Deferred from: spec-7-2-e2e-tournament-drill-2.md (2026-11-04)

- source_spec: `_bmad-output/implementation-artifacts/spec-7-2-e2e-tournament-drill-2.md`
  summary: e2e 一次只跑 1 個測試（`playwright.config.ts` 的 `workers: 1`，`tournament.spec.ts` 另有 `describe.configure({ mode: "default" })`），完整跑一次約 22 分鐘；演練同時跑會互相拖慢，一般 API 超過 1 秒（NFR-2），甚至整個卡住。
  evidence: 2026-11-04 實測：本機沒設 worker 上限時，16 核預設開 8 個 worker，6 個演練同時開瀏覽器、註冊帳號，`POST /accounts` 6～7 秒、`GET /accounts/me` 約 2.4 秒，之後停住超過 20 分鐘；2 個 worker 時 e2e 容器約吃 5 核；1 個 worker 時 10 passed、62 skipped（22.4 分鐘）。7.3 彙整回應時間時要知道這些數字是在什麼並行度下量的；之後要縮短時間，`WORKER_POLL_SECONDS` 最小只能設 15 秒（`core/config.py`），省不多，要另找方法（例如共用已驗證的選手帳號）。
## Deferred from: spec-2-7-referee-invitation.md (2026-11-04)

- source_spec: `_bmad-output/implementation-artifacts/spec-2-7-referee-invitation.md`
  summary: （低）裁判邀請的 token 放在網址路徑（`GET /referee-invites/{token}`、`POST /referee-invites/{token}/accept`），uvicorn 與反向代理的 access log 會記下完整路徑，token 會留在 log 裡；與 3.1 的隊伍邀請連結做法相同。
  evidence: 2026-11-04 D（@OG-Matcha）在 PR #40 的審查，期中可以接受。之後要收緊時，accept 改用 body 帶 token，或在 log 遮蔽這段路徑；隊伍邀請一併處理。
## Deferred from: spec-7-1-tournaments-demo-step.md (2026-11-04)

- source_spec: `_bmad-output/implementation-artifacts/spec-7-1-tournaments-demo-step.md`
  summary: （低）示範賽事的時間在第一次建立時固定（開賽＝當時＋7 天）；保留資料庫、超過 7 天後再次啟動時，tournaments 步驟依「主辦方＋名稱」沿用這場已過開賽時間的賽事，competition 步驟的抽籤會因 `TOURNAMENT_START_PASSED` 一直略過。
  evidence: 2026-11-04 Story 7.1 tournaments 步驟第一輪審查（Blind Hunter、Edge Case Hunter）。凍結區塊規定已存在就沿用、不覆寫；Demo 前用 `docker compose down -v` 清掉資料庫即可。要自動處理時，需由人決定：過期就另建一場（會有兩場同名賽事）或改寫既有賽事的時間（違反「不覆寫」）。
- source_spec: `_bmad-output/implementation-artifacts/spec-4-3-s30-matches-page.md`
  summary: 主辦方賽事後台側欄在子頁（例如 S30 `/organizer/tournaments/{id}/matches`）時，「總覽」（`/organizer/tournaments/{id}`）也顯示為目前位置：`BackofficeLayout` 的 `Link` 沒設 `activeOptions`，以前綴比對；「我的賽事」（`/organizer`）在所有賽事頁也同樣亮起。
  evidence: 2026-11-04 S30 實作時發現；B 的 S31 裁判頁也會遇到。修法需要改 B 的 `components/layout/BackofficeLayout.tsx`（例如 `BackofficeNavItem` 加選填的 `exact`，傳給 `activeOptions`），S30 spec 禁止改 B 的元件，交給 B 決定。
- source_spec: `_bmad-output/implementation-artifacts/spec-4-3-s30-matches-page.md`
  summary: S30 的 Manual checks 還沒做：在瀏覽器（含 375 px）走一次列表、修改時間、指派、收回。
  evidence: 2026-11-04 A 在 #48 審查提醒。本機沒有已抽籤的賽事（抽籤要等 C 的 registration 函式，或 7.1 示範資料有已抽籤的賽事），目前只有單元測試；任一條件完成後補做。

## Deferred from: spec-4-4-s13-referee-matches.md (2026-11-04)

- source_spec: `_bmad-output/implementation-artifacts/spec-4-4-s13-referee-matches.md`
  summary: `Match.referee_account_id` 沒有索引，`GET /me/referee/matches` 會掃整張場次表；資料變多時要加索引，並另開一支 Alembic 遷移。
  evidence: 2026-11-04 S13 實作與審查第 1 輪；期中規模可接受，且 `tests/test_migrations.py` 要求遷移與模型一致，所以這個 Story 沒動 schema。
- source_spec: `_bmad-output/implementation-artifacts/spec-2-7-s31-s23-referee-ui.md`
  summary: （中）裁判名單的查詢在兩處各定義一次：tournaments 的 `referee-queries.ts` `refereesQueryOptions`（S31）與 D 的 `features/competition/organizer-matches-queries.ts` `tournamentRefereesQueryOptions`（S30），都用 `["tournaments","organizer","referees",tournamentId]`；`queryFn`、`retry` 各寫一份，誰先掛載就用誰的設定，之後只改一邊會互相污染快取。
  evidence: 2026-11-05 Story 2.7 第二階段審查（Blind Hunter）。前端依賴方向是 competition → tournaments，不能反過來匯入 D 的定義；處理時請 D 把 `organizer-matches-queries.ts` 改成匯入 `refereesQueryOptions`，刪掉自己的定義（competition 只新增 import，不改 tournaments 的檔案）。
- source_spec: _bmad-output/implementation-artifacts/spec-4-1-s27-draw-button.md
  summary: S27 抽籤預估改成不寫入的純函式試算（目前在 savepoint 內真的分配再回滾，開放報名中每次預估都持有賽事列鎖）。
  evidence: 2026-11-05 S27 審查。`get_draw_status` 在開放報名中呼叫 `finalize_for_draw` 後以例外回滾，每次預覽都重做分配、消耗 `audit_log.seq` 序列值並持有賽事列鎖到交易結束；前端只能以 `staleTime` 與關閉聚焦重抓降低頻率。改成 registration 提供不寫入的試算函式後可移除 savepoint。
- source_spec: `_bmad-output/implementation-artifacts/spec-3-6-deadline-fill.md`
  summary: （中）報名截止工作 `close_registrations` 每輪只取最早到期的一場；那場在 `close_registration` 一直拋錯（例如缺快照的 `RuntimeError`）時，worker 每輪都卡在它，之後到期的賽事永遠不會轉為「報名截止」。
  evidence: 2026-11-05 Story 3.6 截止 worker 審查第 1 輪（Blind Hunter、Edge Case Hunter、Verification Gap 都提出）。`find_due_registration_end_id` 依 `registration_end`、id 取第一筆，`run_once` 遇錯 rollback 後結束本輪該工作；`open_due_registration`、`allocate_due_priority_window` 是相同模式。處理時讓 worker 跳過本輪失敗過的候選（或逐筆在 savepoint 內嘗試），並補「第一場拋錯時第二場仍會關閉」的測試。

## Deferred from: spec-6-5-disqualify.md（2026-11-08）

- source_spec: `_bmad-output/implementation-artifacts/spec-6-5-disqualify.md`
  summary: 6.5 第二階段：disputes `resolve_report`（屬實時呼叫 competition `disqualify`，申訴一併結案）、S33 檢舉處理頁、S27 待處理清單的檢舉、對戰樹的「取消資格」標記（`destructive`）。
  evidence: 2026-11-08 使用者決定 Story 6.5 拆兩階段；第一階段只做 competition `disqualify` 與 registration `disqualify_registration`。檢舉資料表由 C 的 6.4 建立，6.4 合併後接上；`DisqualifyResult.affected_match_ids` 給 disputes 結案該場未結案的申訴。
- source_spec: `_bmad-output/implementation-artifacts/spec-6-5-disqualify.md`
  summary: （期中後）progression 支援「這一方確定不會有隊伍」，讓對手未定時也能取消資格，對手確定後自動判不戰而勝。
  evidence: 2026-11-09 D 在 PR #65 決定期中版對手未定時拒絕（409 `DISQUALIFY_OPPONENT_PENDING`，涵蓋輪空入座等另一場勝隊的一方、決賽要由準決賽敗隊頂替而季軍賽另一方未定）。`progression.advance` 的 `side_team` 只依 plan 的來源推導一方是否定案：輪空直接入座的一方沒有來源、永遠不會定案；由勝場進來的一方被清空後會被重新填回原隊伍。要支援需在 progression 新增這種表示（例如 `MatchState` 加欄位、資料表加旗標並遷移），屬於修改 D 的既有函式。
- source_spec: `_bmad-output/implementation-artifacts/spec-6-5-disqualify.md`
  summary: （未驗證，若成立為中）competition `get_registration_state` 若讀到鎖賽事前已載入 session 的報名，`disqualified` 可能是過時值，導致已取消資格的敗隊被選為頂替隊伍。
  evidence: 2026-11-09 6.5 第一階段審查（Edge Case Hunter）。第一階段 `disqualify` 一開始就 `lock_tournament`，之前不讀報名，所以目前不會發生；第二階段 disputes `resolve_report` 若在呼叫 `disqualify` 前讀過同一隊的報名就可能成立。第二階段實作時確認呼叫順序，或在 registration 的 `get_registration` 讀取時 `populate_existing`。
## Deferred from: code review of spec-6-2-review-fixes.md (2026-11-09)

- source_spec: `_bmad-output/implementation-artifacts/spec-6-2-review-fixes.md`
  summary: （低）申訴說明與處理理由的 1000 字上限，前端以 UTF-16 單位計算、後端以 code point 計算；含大量 emoji 的文字可能前端顯示未超過、送出後回 422（或反過來）。
  evidence: 2026-11-09 審查（Blind Hunter）。`disputes/models.py` 的註解已寫明差異；修法是前端改用 `[...text].length` 計數並補測試，6.1、6.2、6.4 的表單一併處理。
## Deferred from: unified code review of 5.6／5.8／7.1／7.3 (2026-11-09)

- source_spec: `_bmad-output/implementation-artifacts/spec-7-1-registration-demo-step.md`
  summary: （低）示範資料的段位截圖在資料庫寫入前就存到磁碟；單隊的 savepoint 或整個示範交易回滾時，已存的截圖留在磁碟（#67 審查提過）。
  evidence: 2026-11-09 統一 code review。`registration.py` 的 `update_player_profile` 先 `storage.save_image` 再寫資料庫，`initial_data.py` 失敗時整批回滾；每次失敗的啟動最多留下 160 個 1×1 PNG。修法：回滾時刪掉本次存的檔案，或先寫資料庫、提交後再存檔。
- source_spec: `_bmad-output/implementation-artifacts/spec-7-1-tournaments-demo-step.md`
  summary: 示範賽事沒有直播連結，與 epics.md 的 7.1 AC 不同。
  evidence: 2026-11-04 使用者決定不做（spec 第 19、46 行），spec 要求在 PR 記錄差異；統一 code review 補登於此，期中後若 S2 要展示直播連結再補。
- source_spec: `_bmad-output/implementation-artifacts/spec-7-1-tournaments-demo-step.md`
  summary: （低）同名遊戲已存在但段位名稱不同時，示範資料沿用舊遊戲，32 隊的 `update_player_profile` 全部失敗、只記警告，接著對 0 隊抽籤，啟動不會報錯。
  evidence: 2026-11-09 統一 code review。`tournaments.py` 依名稱沿用遊戲；只有手動改過遊戲設定的保留資料庫會遇到。
- source_spec: `_bmad-output/implementation-artifacts/spec-7-3-test-coverage-report.md`
  summary: （低）純函式 90% 分支覆蓋率是單元＋整合合併計算（`coverage run --append`），AC 寫的是單元測試；`test-all.sh` 複製前端 JUnit 與 Playwright JSON 時丟掉錯誤，檔案不存在時報告不會明確失敗。
  evidence: 2026-11-09 統一 code review。`scripts/test.sh`、`scripts/test-all.sh`。修法：README 註明計算方式（或只用單元測試算），`cp` 失敗時在報告標出缺漏。
- source_spec: `_bmad-output/implementation-artifacts/spec-6-4-followup-review.md`
  summary: （低）6.1 申訴的刪檔測試（`test_file_appeal.py`，例如 `test_commit_failure_deletes_the_attachment`）只斷言上傳目錄是空的，實作沒存檔也會通過；可比照 6.4 用 spy `storage.save_image` 斷言存過且該鍵值已被刪。
  evidence: 2026-11-09 6.4 合併後審查後續的 Blind Hunter 指出；與 D 在 #64 指出的 6.4 刪檔測試是同一類漏洞，6.4 這邊已補，申訴是 B 的測試，不在本次範圍。

## Deferred from: spec-7-2-e2e-tournament-drill-3.md (2026-11-10)

- source_spec: `_bmad-output/implementation-artifacts/spec-7-2-e2e-tournament-drill-3.md`
  summary: 3.9「公開正取名單」做完後，完整賽事演練要補「觀眾未登入在賽事頁看到分配後的正取隊伍」；目前改為抽籤後在公開對戰表看到隊伍。
  evidence: 3.9 期中擱置，S2 沒有正取名單分頁（`TournamentTabs.tsx` 的註解）。

## Deferred from: spec-5-7-settlement-screenshot.md (2026-11-20)

- source_spec: `_bmad-output/implementation-artifacts/spec-5-7-settlement-screenshot.md`
  summary: （低）S32 申訴處理頁沒有通往 S4 場次頁的連結，主辦方處理申訴時要自己從對戰樹點進場次頁才看得到結算截圖；可在 S32 每個場次加「查看場次頁」連結（B 的 `AppealsPage.tsx`）。
  evidence: 2026-11-20 Story 5.7 核准時使用者決定這次不動 S32，留給 B；期中 B 文件的申訴使用案例寫主辦方處理時「檢視說明、各局比分與結算截圖」。
- source_spec: `_bmad-output/implementation-artifacts/spec-4-2-auto-draw.md`
  summary: （低）自動抽籤某場每輪都拋錯時（例如資料不一致讓 `mark_drawn` 拒絕），`auto_draw_due` 只寫 exception log、每輪重試，主辦方看不到；開賽時間過後就不再嘗試，也沒有通知。
  evidence: 2026-11-19 Story 4.2 審查第 2 點；與 `start_due_tournament` 相同模式。可考慮連續失敗後寫略過紀錄並發事件。

## Deferred from: spec-1-6-notification-center.md (2026-11-21)

- source_spec: `_bmad-output/implementation-artifacts/spec-1-6-notification-center.md`
  summary: （低）FR-37「裁判指派因晉級衝突被取消時另通知主辦方」沒有做：`RefereeUnassigned` 沒有區分「晉級衝突自動收回」與「主辦方收回、改派」，notifications 無從判斷，目前只通知被取消的裁判。
  evidence: Story 1.6 Decisions。修法：competition 在 `RefereeUnassigned` 加一個原因欄位（例如 `reason: "conflict" | "organizer"`，5.5 `unassign_referee_if_member` 發 `conflict`），notifications 的 `_referee_unassigned` 在 `conflict` 時另加主辦方一份草稿（link `/organizer/tournaments/{tid}/matches`）。

- source_spec: `_bmad-output/implementation-artifacts/spec-2-6-cancel-tournament.md`
  summary: （未驗證，若為真屬 medium）賽事取消後，側欄的場次管理（S30）、裁判（S31）、申訴（S32）、檢舉（S33）頁可能仍顯示可操作的按鈕；確認對話框寫「賽事資訊改為唯讀」，2.6 的驗收條件只要求 S27 唯讀。
  evidence: 2026-11-22 Story 2.6 審查（Blind Hunter）。後端已確認裁判邀請（`ensure_accepting_referees`）與申訴處理（`disputes/service.py` 拒絕已取消）會擋下；改場次時間是否擋下未確認。要確認 competition 的改時間 API 對已取消賽事的處理，並決定各頁是否隱藏動作。
## Deferred from: spec-3-8-review-and-reject-registration.md (2026-11-22)

- source_spec: `_bmad-output/implementation-artifacts/spec-3-8-review-and-reject-registration.md`
  summary: （低）3.7 撤回在「優先期已過、worker 還沒結算」時沒有先結算：`withdraw_registration` 直接撤回再 `_backfill_released_locked`，沒有結算紀錄就不遞補；撤回的若是優先期內送出的 `pending`，之後 worker 結算時該校會被當成優先期沒有報名（`priority_school_ids` 不含該校）。3.8 的退回已比照 `submit_registration` 先結算。
  evidence: Story 3.8 spec 審查第 8 點。修法：`withdraw_registration` 在鎖內、撤回前比照 `reject_registration`，校園賽且 `now > priority_end` 時先呼叫 `settle_priority_window`（已結算時不做任何事），並補「優先期已過、尚未結算時撤回」的測試。
## Deferred from: spec-2-8-organizer-audit-log.md (2026-11-21)

- source_spec: `_bmad-output/implementation-artifacts/spec-2-8-organizer-audit-log.md`
  summary: （低）S34 操作紀錄的分頁在 service 切片：`list_audit_log` 每次都經 `core.audit.list_for_tournament()` 讀出該賽事的全部紀錄，再反轉、取一頁；一場 64 隊賽事可達上千筆，每換一頁都要讀全部。
  evidence: Story 2.8 Decisions（AC 指定用 `list_for_tournament()`，不改 `core/audit.py` 既有函式）。修法：在 `core/audit.py` 新增一個資料庫層分頁的函式（例如 `page_for_tournament(session, tournament_id, *, offset, limit)` 回傳該頁與總數，`ORDER BY at DESC, seq DESC`，可用既有索引 `ix_audit_log_tournament_id_at_seq`），`list_audit_log` 改呼叫它。
- source_spec: `_bmad-output/implementation-artifacts/spec-2-8-organizer-audit-log.md`
  summary: （低）S34 的變更內容照原始資料顯示：欄位名稱是英文代碼（如 `registration_end`、`rank_tiers`），id 是 UUID（如 `game_id`、`organizer_id`），時間是 UTC ISO 字串；主辦方不一定看得懂。
  evidence: Story 2.8 Decisions。翻譯欄位名稱、把 id 換成名稱需要各模組提供對照（各模組寫紀錄的欄位不同），可在前端 `features/tournaments/audit-log.ts` 依 `entity_type` 加欄位名稱對照表，id 換名稱則需後端各模組提供批次查名稱的公開函式。
- source_spec: `_bmad-output/implementation-artifacts/spec-1-6-notification-center.md`
  summary: （中）一般通知事件之間仍沒有重試上限：某則事件的 resolver 每次都拋非預期例外（程式錯誤、DataError）時，`dispatch_outbox` 每輪回滾、停在這則，之後的一般通知全部延後；驗證信與重設信已改為優先處理，不受影響。
  evidence: 2026-11-21 OG-Matcha 在 #100 的審查第 1 點；followup 只做了 token 事件優先。修法：`outbox_event` 加 `attempts`／`last_error`（需遷移，`core/events.py`），失敗時在獨立交易裡累加，超過上限標為 dead-letter 並寫 log；或改成略過時記錄到操作紀錄。
## Deferred from: spec-3-11-roster-changes-and-disband-team.md (2026-11-23)

- source_spec: `_bmad-output/implementation-artifacts/spec-3-11-roster-changes-and-disband-team.md`
  summary: （低）3.7 撤回的隊伍隊員仍佔同賽事一隊：撤回後 `TeamMember` 列保留，`ALREADY_IN_TOURNAMENT` 與唯一鍵 (tournament_id, account_id) 讓隊員無法加入同賽事的其他隊伍；3.11 只處理名單鎖定前的異動（FR-41），撤回後的報名名單已鎖定，移除、退出、解散都回 409 `ROSTER_LOCKED`。
  evidence: Story 3.11 Decisions。修法候選：撤回時比照解散把原隊員搬到 `disbanded_team_member`（或另一張保存表）並刪除隊員列；或 `_ensure_can_join` 與唯一鍵改為排除報名已撤回的隊伍（要改唯一鍵與遷移）。
- source_spec: `_bmad-output/implementation-artifacts/spec-3-11-roster-changes-and-disband-team.md`
  summary: （中）既有通知規則在 worker 處理時才以 `_member_ids` 查隊員（`notifications/rules.py`）：主辦方退回後、worker 處理前隊長就移除隊員或解散，`RegistrationRejected`、`RegistrationAllocated`、`RegistrationBackfilled` 只寄給處理當下仍在隊上的人（解散則沒有人收到）。
  evidence: Story 3.11 spec 審查第 3 點、Design Notes。修法候選：這些事件改帶發生當下的收件人帳號（違反 AD-8「事件只帶 id」，需要人決定），或規則在隊伍已解散時改查 `registration.service.list_disbanded_member_ids`（只補解散的情況，移除仍會少人）。

## Deferred from: spec-2-5-edit-tournament.md (2026-11-23)

- source_spec: `_bmad-output/implementation-artifacts/spec-2-5-edit-tournament.md`
  summary: （未驗證，若為真屬 medium）報名截止的賽事延長報名、轉回開放報名時，沒有處理截止時已發出的事件或已改變的狀態，也沒有通知已報名隊伍報名重新開放。
  evidence: 2026-11-23 Story 2.5 審查（Blind Hunter）。2.5 的 AC 沒有要求通知；優先期結算（`priority_window_settlement`）已完成不重跑是預期行為。要確認 registration `close_registration` 有沒有發出在重新開放後會變成錯誤的事件，並決定是否通知隊伍。

## Deferred from: spec-3-11-roster-changes-and-disband-team.md（#110 組員審查，2026-11-23）

- source_spec: `_bmad-output/implementation-artifacts/spec-3-11-roster-changes-and-disband-team.md`
  summary: （低）S19 先顯示「可加入」、隊長在這之後解散隊伍，按加入時 `join_team` 回 409 `ROSTER_LOCKED`，畫面顯示「名單已鎖定」，重新整理後才變成「隊伍已解散」；行為正確，只是文字不一致。
  evidence: 2026-11-23 OG-Matcha 在 #110 的審查第 2 點；Story 3.11 程式審查 R7（凍結矩陣「解散與加入同時」規定回 `ROSTER_LOCKED`）。修法候選：解散的隊伍加入時回專屬錯誤碼（例如 `TEAM_DISBANDED`，需改 spec 矩陣），或前端在加入得到 409 時重新取得邀請預覽。

## Deferred from: spec-6-3-appeal-overdue.md (2026-11-24)

- source_spec: `_bmad-output/implementation-artifacts/spec-6-3-appeal-overdue.md`
  summary: （低）`AppealReminded` 派送時沒有再確認申訴仍未結案、賽事不是已結束或已取消；outbox 前面卡住導致延後派送時，主辦方可能在處理完後才收到「申訴待處理」。
  evidence: Story 6.3 審查（Blind Hunter 第 6 點、Edge Case Hunter 第 7 點）。修法：notifications `rules.py` 的 `_appeal_reminded` 經 disputes 公開函式查申訴狀態，已結案或賽事已結束／已取消時回傳空清單（A 的模組，需 A 同意）。
- source_spec: `_bmad-output/implementation-artifacts/spec-6-3-appeal-overdue.md`
  summary: （低，效能）`remind_due_appeal` 每次都掃過所有未結案、未提醒的申訴，已取消或已結束賽事裡沒結案的申訴永遠留在候選中；任一候選讀取失敗會讓整個工作回滾。
  evidence: Story 6.3 審查（Blind Hunter 第 4 點、Edge Case Hunter 第 14 點）。修法候選：候選查詢 join 賽事排除已結束／已取消，或對單一候選的例外記 log 後略過。
- source_spec: `_bmad-output/implementation-artifacts/spec-6-3-appeal-overdue.md`
  summary: （低）決賽、季軍賽兩隊在不同時間申訴時，S32 以最早一筆未結案申訴計算處理期限，S27 每筆各自計算，兩頁顯示的期限不同。
  evidence: Story 6.3 審查（Edge Case Hunter 第 6 點）。修法候選：S32 改為逐筆顯示期限，或 S27 同場合併成一個期限。
## Deferred from: spec-3-9-public-accepted-teams.md（#106 組員審查，2026-11-23）

- source_spec: `_bmad-output/implementation-artifacts/spec-3-9-public-accepted-teams.md`
  summary: （低）前端「能不能檢舉」的前置判斷（已登入、此賽事有四種狀態隊伍、是隊長、賽事未結束或取消）在 6.4 `ReportTeamEntry` 與 3.9 `AcceptedTeamReportAction` 的 `useReportableTeamsById` 各寫一份；之後改其中一邊的條件，另一邊要記得一起改。哪些隊伍可檢舉、是否已有處理中的檢舉由後端 `reportable-teams` 決定，兩邊共用，不受影響。
  evidence: 2026-11-23 OG-Matcha 在 #106 的審查建議。抽成共用 hook 要改 C 的 `ReportTeamEntry.tsx`（CLAUDE.md：動到別人的模組只新增），所以 3.9 不動。修法：把 `useReportableTeamsById` 移到 `features/disputes/useReportableTeams.ts` 匯出，`ReportTeamEntry` 改用它（`eligible` 改成 Map 不為空），兩邊的 `REPORTER_STATUSES`、`ENDED_STATUSES` 只留一份；`report-team.test.tsx`、`accepted-teams.test.tsx` 應不需修改。

## Deferred from: spec-3-10-custom-mode-first-come.md（#118 組員審查，2026-11-24）

- source_spec: `_bmad-output/implementation-artifacts/spec-3-10-custom-mode-first-come.md`
  summary: （低）registration `_candidate` 為了讓自訂賽事的學校快照可為 null，拿掉了「缺學校快照拋 RuntimeError」的檢查，校園賽也一併放行；校園賽若有 `school_id` 為 null 的報名，會被當成同一所學校套用每校上限與順位，不會報錯。
  evidence: 2026-11-24 OG-Matcha 在 #118 的審查建議（第 2 點）；本 Story 實作審查 R9 同一件事。目前沒有路徑會產生這種資料（校園賽送出時 `submit_registration` 已保證有學校），屬防禦性退步。修法：校園賽的呼叫端（或 `_candidate` 加模式參數，經 `allocation.checks_school` 判斷）在學校快照為 null 時拋 RuntimeError，自訂賽事照常放行。

## Deferred from: spec-3-10-custom-mode-invite-link.md（程式碼審查，2026-11-25）

- source_spec: `_bmad-output/implementation-artifacts/spec-3-10-custom-mode-invite-link.md`
  summary: （中，未驗證）遷移 `b2f6c8d4e1a9` 在加 CHECK 約束前替既有自訂賽事補 token 的迴圈，沒有對實際資料執行的測試。
  evidence: `tests/test_migrations.py` 只比對模型與遷移的 schema，不在有資料的資料庫上跑 `upgrade()`。要驗證：在 `a7d3e9b2c6f4` 建一筆 `mode='custom'`、無 token 的賽事，升級後確認有 token 且約束存在。目前只有本機以 SQL 改成自訂的賽事會遇到，已手動驗證過一次（7 場）。
