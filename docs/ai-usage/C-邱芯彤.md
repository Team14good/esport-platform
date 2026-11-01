# 邱芯彤 的 AI 使用紀錄

格式與等級定義見 [README](README.md)。只在檔尾新增，最新的在最下面。

### 2026-11-01｜需求與設計／spec｜Story 3.4 名額分配規則（第一階段 spec）

- Story／範圍：3.4 第一階段（分支 story/3-4，尚未開 PR）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（規劃步驟）
- 怎麼用：開工前先用 gh 查 PR 狀況，確認 3.1、2.2 未合併、沒有人在做分配規則；AI 比照 D 的 4.1、5.x 第一階段，提議先寫不碰資料庫的純函式，依 FR-14～17 與 EXPERIENCE.md 的固定字串寫 spec
- AI 產出：spec 一份（I/O 與邊界情況表 10 列、驗收條件 2 條、任務 3 項），並提出範圍問題（只做 3.4，或一次做完 3.4～3.6 的校園賽規則）
- 人做了什麼：決定一次做完校園賽規則、保留約 2,700 tokens 的完整 spec，核准 spec
- 驗證：spec 經人審核後核准
- 問題與修正：AI 第一版 spec 的範圍選項 A 已把 `decide_first_come` 列為任務，但 I/O 表沒有先搶期送出的情境，人決定範圍後由 AI 補上兩列；Never 一節原寫「只用標準函式庫」，與 Code Map 要 import `registration.models` 矛盾，AI 自我檢查時修正
- 成熟度：L4（固定流程產出 spec，人在 checkpoint 決定範圍與核准）
- 證據：_bmad-output/implementation-artifacts/spec-3-4-allocation-policy.md；commit 未記錄（尚未 commit）

### 2026-11-01｜程式／程式生成｜Story 3.4 名額分配規則（第一階段實作）

- Story／範圍：3.4 第一階段（分支 story/3-4，尚未開 PR）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（實作子代理）
- 怎麼用：由不帶對話脈絡的子代理只依 spec 實作，主流程對照 diff 驗收任務與 I/O 表，並自己重跑全部測試與分支覆蓋率
- AI 產出：registration/allocation.py（排序鍵、優先期結算、先搶期送出判定、兩階段候補順位與原因代碼、截止補位）；測試 29 個
- 人做了什麼：未記錄（待使用者確認子代理對 spec 未寫明處的 4 項解讀，見 spec 的 Implementation Notes）
- 驗證：後端 761 個測試通過；allocation.py 分支覆蓋率 100%（22 個分支）；mypy、ty、ruff 通過
- 問題與修正：無（子代理把 spec 未寫明的 4 項解讀列出交給人確認，沒有自行寫進 spec）
- 成熟度：L4（依 spec 由子代理實作，主流程對照 diff 驗收並自動測試）
- 證據：spec 同上；commit 未記錄（尚未 commit）

### 2026-11-01｜測試／程式審查｜Story 3.4 名額分配規則（第一階段審查與測試）

- Story／範圍：3.4 第一階段（分支 story/3-4，尚未開 PR）
- 工具：Claude Code（Opus 5.5）＋ bmad-build 審查步驟（Blind Hunter、Edge Case Hunter、Verification Gap 三個審查子代理）
- 怎麼用：三個審查者平行審 diff，主流程逐項查證後分類，記在 spec 的 Review Triage Log，修正交回原實作子代理
- AI 產出：審查發現共 20 項；修正 6 組（補「略過候選者本身」的測試、介面字串改為全文比對、兩段 docstring 寫明呼叫端責任、deferred 寫明 `fill_at_deadline` 與 11/12 交接、sprint-status 註解），延後 2 項（代表隊退出的同校遞補對象、分支覆蓋率自動檢查），其餘查證後駁回
- 人做了什麼：未記錄（審查分類由 AI 完成，待使用者確認）
- 驗證：修正後後端 762 個測試通過，allocation.py 分支覆蓋率 100%，lint 通過；主流程在一次性容器中刪掉 `decide_first_come` 的自我排除條件，確認新測試會失敗
- 問題與修正：Verification Gap 審查者指出原本的測試用 `pending` 狀態的候選者，本來就不計入正取，刪掉或反轉過濾條件測試照樣通過，屬於「測試存在但驗證不到」；實作子代理推算新測試能抓到後，主流程實際做一次變異測試確認
- 成熟度：L4（多個獨立審查者加自動測試與變異檢查，主流程查證每項發現）
- 證據：spec 的 Review Triage Log；_bmad-output/implementation-artifacts/deferred-work.md；commit 未記錄（尚未 commit）