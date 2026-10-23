---
input: prds/prd-se-final-project-2026-10-14/prd.md
spines: DESIGN.md, EXPERIENCE.md（2026-10-15 版）
checked: 2026-10-15
---

# 輸入對照：PRD

## (a) spine 已涵蓋的 UX 相關項目

| PRD 項目 | spine 位置 |
|---|---|
| §3 名詞表（賽事／場次／局；輪空；不用同義詞） | EXPERIENCE 開頭聲明、〈Voice and Tone〉 |
| UJ-1～UJ-4 | EXPERIENCE〈Key Flows〉逐步展開，高潮與例外皆保留 |
| FR-1～FR-38、NFR-3／6／7 對應 surface | EXPERIENCE〈需求覆蓋〉表 |
| §3 TournamentStatus 六態（含已取消） | EXPERIENCE〈State Patterns／賽事狀態〉 |
| §3 MatchStatus 待開打→進行中→申訴期→已確認／申訴中 | EXPERIENCE〈State Patterns／場次狀態〉（另加三個介面子狀態，已標明） |
| ApplicationStatus 待審核／核准／退回 | EXPERIENCE〈主辦方申請〉 |
| FR-4 一場一位裁判、未指派時主辦方代登（FR-26） | EXPERIENCE S24、Score entry panel |
| FR-9 只能延長、抽籤後只改場次時間 | EXPERIENCE〈Interaction Primitives〉、S28 |
| FR-11 滿員／鎖定後邀請連結失效、同賽事只能一隊 | EXPERIENCE Invite link field、〈通用狀態〉邀請連結失效 |
| FR-12 段位從對照表選、5 MB JPG／PNG | EXPERIENCE S18、Screenshot uploader |
| FR-13 不符條件時無法送出 | EXPERIENCE〈報名狀態〉組隊中「逐項列出缺什麼」 |
| FR-15 送出當下判定正取／候補 | EXPERIENCE〈Interaction Primitives〉送出 |
| FR-19 提前抽籤、只能一次、正取 < 2 不能抽 | EXPERIENCE UJ-1 步驟 6、〈賽事狀態〉報名截止列 |
| FR-24 開賽前 30 分起報到、雙方報到後「可開始」 | EXPERIENCE 場次子狀態、〈倒數與時間〉 |
| FR-25 棄權→進申訴期、申訴未處理時計時暫停 | EXPERIENCE 棄權計時暫停子狀態、〈倒數與時間〉暫停 |
| FR-26／27 平手不能送出、達門檻不能加局、確認後唯讀 | EXPERIENCE Score entry panel |
| FR-29／FR-36 申訴期／申訴中不顯示晉級 | EXPERIENCE〈對戰樹〉、Score display |
| FR-31 維持／更正＋理由、逾期前 1 小時提醒 | EXPERIENCE S32、〈倒數與時間〉申訴處理期限 |
| FR-32 已結束後不能檢舉 | EXPERIENCE〈賽事狀態〉已結束「檢舉入口消失」 |
| FR-35 10 秒內更新、375 px 左右捲動、輪空／棄權／取消資格不同標示、淘汰灰色 | EXPERIENCE〈對戰樹〉（5 秒輪詢）；DESIGN `status-eliminated`、Bracket mark tag |
| FR-36 結算截圖公開、段位截圖只給主辦方 | EXPERIENCE 需求覆蓋 NFR-6 列 |
| FR-37／38 站內＋Email、新通知在最上、點開導向 | EXPERIENCE〈通知〉 |
| NFR-1 不超收、SM-C1「寧可慢也不能分錯」 | EXPERIENCE Button (primary) 不做 optimistic update |
| NFR-4 到期 1 分鐘內執行 | EXPERIENCE〈倒數與時間〉到期行為 |
| NFR-5 權限在伺服器 | EXPERIENCE〈Foundation〉權限、〈身分切換器〉 |
| NFR-7 375 px、繁中 | EXPERIENCE〈Responsive & Platform〉 |
| §6 不做原生 App、直播只放連結 | EXPERIENCE〈Foundation〉、Open Questions #8 |
| §2.1 主辦方「出了爭議能拿出紀錄說明」 | DESIGN〈Brand & Style〉 |

## (b) 未反映／被捨棄的項目

1. **FR-25 雙方都未報到**：「兩隊皆淘汰、下一輪對手輪空」；準決賽發生時「另一場勝隊直接成冠軍、季軍賽取消」。spine 的場次卡、Bracket mark tag、〈賽事狀態〉已結束（冠亞季置頂）都沒有這個情境。
2. **FR-20「正取少於 4 隊時不產生季軍賽」**：〈對戰樹〉假設季軍賽固定在決賽下方，未處理沒有季軍賽的情況。
3. **FR-23「場次已開始（已有隊伍報到）後無法修改時間」**：S30「修改時間」未寫停用條件。
4. **FR-30「每支隊伍對同一場次只能申訴一次」**：S4／S21 未寫本隊已申訴後「提出申訴」的狀態。
5. **FR-32「不能檢舉自己的隊伍」**：S20 入口在「正取隊伍」每一列，未寫自己隊伍列不顯示「檢舉」。
6. **FR-13「隊員學校不一致時無法送出」**：〈報名狀態〉只寫「逐項列出缺什麼」，未列學校一致這一項（帳號學校在 S10）。
7. **UJ-2 步驟 3「上場時必須使用這個帳號（遊戲 ID）」**：S18 沒有提醒文案，質性約束被捨棄。
8. **FR-7 欄位「棄權時限（預設 15 分）、申訴期（預設 30 分）」**：EXPERIENCE UJ-1 步驟 4 列舉的欄位漏了這兩項（S26 以 FR-7 引用帶過）。
9. **§4.2 賽事進入「進行中」的觸發點**（第一個場次開放報到時）與「已結束」觸發點（決賽與季軍賽都確認）：〈賽事狀態〉未寫，觀眾看到的切換時機不明。
10. **§8 SM-C2「不要追求功能數量」**：spine 的附加功能（見 C3）未對照此反向指標說明取捨。

## (c) 衝突

| # | PRD | spine | 判斷 |
|---|---|---|---|
| C1 | **FR-22**：被取消資格的隊伍若已贏過至少一場 → 由「最近一場輸給它的隊伍」頂替；只有尚未比賽時才由候補遞補 | EXPERIENCE〈對戰樹〉「遞補隊伍直接出現在原位置（FR-17、FR-22）」；UJ-2 例外「S3 上該隊標『取消資格』，遞補隊伍出現在原位置」 | **實質衝突**：spine 只描述候補遞補，漏了「敗給它的隊伍頂替」，且 UJ-2 例外未區分兩種情況。對戰樹需能顯示「被淘汰的隊伍復活回到下一輪」。 |
| C2 | FR-13：名單人數「不足先發人數」才不能送出（替補非必要） | EXPERIENCE UJ-2 步驟 5「名單湊滿 5＋1、全員資料完成 →『送出報名』可用」 | 輕微：PRD UJ-2 敘事也寫 5＋1，但規則以 FR-13 為準。送出按鈕的啟用條件應為「≥ 先發人數」，替補可缺。 |
| C3 | §8 SM-C2 範圍以 §7 為準、不追求功能數量；PRD 無忘記／重設密碼、重寄驗證信、移除隊員、轉讓隊長、帳號資料頁、隊伍搜尋 | EXPERIENCE S8、S9、S10、S17（移除／轉讓）、〈對戰樹〉隊伍搜尋、主題切換 | 範圍擴張；spine 已標為「使用者決定」，但 PRD／Epic 需同步，否則 FR 覆蓋表無對應需求。 |
| C4 | FR-3「核准後，該帳號**立即**可以建立賽事」 | 〈身分切換器〉「新身分出現時，切換器在**下次載入**時出現新項目」[ASSUMPTION] | 輕微：權限立即生效，但入口延遲。S15「前往主辦方後台」可補足；建議核准狀態一被讀到就刷新切換器。 |
| C5 | §3 RegistrationStatus 未列「組隊中」「已送出・待分配」 | EXPERIENCE〈報名狀態〉新增兩個介面標籤 | 已標 [ASSUMPTION] 並列入 Open Questions #17；需 PRD 或架構確認。 |
| C6 | §3／FR-36 場次狀態只有四（五）態 | spine 新增「待開打・可報到」「待開打・可開始」「棄權計時暫停」三個介面子狀態 | 已標「介面子狀態」，非正式 `MatchStatus`；不衝突，但需確保程式不把它們寫成 enum 值（AD-11）。 |

## (d) 結論

PRD 覆蓋完整，旅程、狀態、時限、數字（30 分、15 分、5 MB、1 小時、10 秒）全部一致。**必須修正一項：C1（FR-22 取消資格頂替規則）**。建議補上：雙方棄權與無季軍賽的對戰樹呈現（b1、b2）、FR-23／FR-30／FR-32 的按鈕停用條件（b3～b5）、送出報名條件改為先發人數（C2）。範圍擴張（C3）需回寫 PRD 或在 Epic 註明為 UX 追加。

## EXPERIENCE.md Open Questions 回補明細

自 EXPERIENCE.md〈Open Questions〉移入（2026-10-15 編修）；編號與 EXPERIENCE.md 一致，EXPERIENCE.md 只留一行索引。

### OQ 8. 直播連結

使用者決定納入：S26 選填網址、S2 總覽「觀看直播」。回補：PRD FR-7（建立賽事欄位）；架構 D-2 `Tournament` 加欄位（`TournamentService.create_tournament`／`update_tournament` 帶入）。

**✅ 已回補（2026-10-15）**：PRD FR-7（選填 http／https 網址、賽事頁「觀看直播」另開分頁）、FR-9（賽事結束前都可修改，不受抽籤後鎖定）、§3 賽事定義；架構 D-2 `Tournament.livestream_url`，由 `create_tournament`／`update_tournament` 帶入。

### OQ 9. 忘記／重設密碼（S8、S9）

使用者決定。回補：PRD FR-1 增列可測結果（或新增 FR）；架構 D-1 `IdentityService`／`IdentityRouter` 沒有對應方法（需如 `request_password_reset(email)`、`reset_password(token, new_password)`），也沒有重設 token 與到期欄位；FR-37 通知對象表是否含重設信。

**✅ 已回補（2026-10-15）**：PRD 新增 FR-40（不洩漏 Email 是否存在、連結 1 小時有效 [ASSUMPTION]、一次性、重新申請作廢舊連結）；FR-37 註明重設信只寄 Email、不進站內通知。架構新增 AD-21 與 D-1 `AccountToken`、`IdentityService.request_password_reset(email)`、`reset_password(token, new_password)`。

### OQ 10. 重寄驗證信（S7）

使用者決定。回補：PRD FR-1；架構 D-1 只有 `register`、`verify_email(token)`，缺 `resend_verification(account)`，以及驗證 token 過期規則。

**✅ 已回補（2026-10-15）**：PRD FR-1 可測結果（驗證連結 24 小時有效 [ASSUMPTION]、重寄後舊連結失效）。架構 AD-21、D-1 `IdentityService.resend_verification(account)`，驗證 token 存於 `AccountToken`。

### OQ 11. 移除隊員（S17，名單鎖定前）

使用者決定。回補：PRD FR-11（或 FR-13 補「鎖定前可移除」）；架構 D-3 `RegistrationService` 沒有方法（需如 `remove_member(captain, team_id, account_id)`）；被移除者是否收到通知需列入 FR-37 對象表。

**✅ 已回補（2026-10-15）**：PRD 新增 FR-41（名單鎖定前、隊長不能移除自己、參賽資料一併刪除）；FR-37 加「被移除出隊伍 → 被移除的選手」。架構 D-3 `RegistrationService.remove_member(captain, team_id, account_id)`、事件 `TeamMemberRemoved`；AD-6 規定先鎖 Tournament。

### OQ 12. 轉讓隊長（S17，名單鎖定前）

使用者決定。回補：PRD FR-11；架構 D-3 `RegistrationService` 沒有方法（需如 `transfer_captain(captain, team_id, account_id)`），牽涉 `TeamMember.role`（`MemberRole`）與 AD-10 `ensure_captain`。

**✅ 已回補（2026-10-15）**：PRD FR-41（只能轉給同隊隊員、原隊長立即失去權限）、§3 隊長定義；FR-37 加「轉讓隊長 → 新隊長」。架構 D-3 `RegistrationService.transfer_captain(captain, team_id, account_id)`，隊長只看 `TeamMember.role`、每隊恰好一位，`ensure_captain` 不變；事件 `CaptainTransferred`。

### OQ 16. 裁判邀請有效期限

架構 D-2 `RefereeInvitation.expires_at` 存在，但 PRD FR-4 沒寫期限長度與能否重新產生。回補：PRD FR-4 可測結果；S31「產生新連結」是否作廢舊連結。

**✅ 已回補（2026-10-15）**：PRD FR-4（7 天有效 [ASSUMPTION]；重新產生後舊連結立即失效）。架構 D-2 `invite_referee` 作廢同賽事未到期的舊邀請、`accept_invitation` 檢查到期。S31「產生新連結」會作廢舊連結。

### OQ 26. 場次「待開打 → 進行中」的觸發事件

PRD §3 只列狀態順序；EXPERIENCE.md 假設「第一局登錄成功」時轉換（〈State Patterns〉）。回補：PRD §3 或 FR-26 補一句；架構 D-4 `MatchService.transition_match` 依此實作。

**✅ 已回補（2026-10-15）**：PRD §3 與 FR-26 已於 2026-10-15 前次更新寫明「裁判登錄第一局時」轉為進行中，與 EXPERIENCE.md 假設一致；架構 D-4 `MatchService.transition_match` 依此實作，無需修改。
