# 組員協作說明

> **草案，協作流程待組內討論。** 第 3 節的認領、分支、PR 與合併流程是提議，還沒有定案；待決定的項目列在〈0. 待組內決定〉。第 1、2、4 節是專案現況與已知的坑，可以直接照做。第 6 節的期中分工與範圍已於 2026-10-28 定案。

這份文件說明組員怎麼接手一個 Story，從開分支、用 BMAD 產生 spec 並實作，到發 PR 合併。專案的啟動與測試指令見 [README.md](README.md)。

## 0. 待組內決定

討論出結論後，更新第 3、5 節，並刪除這一節與開頭的草案標示。

1. **認領 Story 的方式**：在群組說、用 GitHub Issue 指派，還是直接修改 `sprint-status.yaml`？
2. **分支與合併**：一個 Story 一個分支、發 PR 合併，還是直接推 `main`？`main` 要不要設成受保護分支？
3. **PR 審查**：要不要規定至少一位組員看過？審查時要不要跑 `/bmad-walkthrough` 或 `/bmad-code-review`？
4. **誰把 Story 改成 `done`**：作者、審查者，還是組長？
5. **commit 粒度**：一個 Story 一個 commit，還是允許多個？
6. **是否一律用 BMAD 與 Claude Code 做 Story**：還是可以手寫程式？這會決定 Claude Code 和 uv 是不是必裝。
7. ~~**分工方式**：按 Epic 分，還是按 Story 分？~~ **已定案（2026-10-28）**：依模組分工，期中前只做主線，見〈6. 期中分工與範圍〉。
8. **`docs/` 期中交付文件由誰維護**？

## 1. 第一次準備

需要的工具：

| 工具 | 用途 |
| --- | --- |
| Docker（含 Docker Compose v2.23 以上） | 啟動與測試整套服務（後端、前端、資料庫、寄信） |
| Git（Windows 請用 Git Bash 執行 `.sh` 腳本） | 版本控制 |
| [Claude Code](https://claude.com/claude-code) | 執行 BMAD 工作流程（`.claude/skills/` 裡的 bmad skill） |
| [uv](https://docs.astral.sh/uv/) | BMAD 的腳本用 `uv run` 執行（Python 3.11 以上，uv 會自動處理） |

```bash
git clone https://github.com/max930000/espory-platform.git
cd espory-platform
cp .env.example .env                  # 本機設定，不會進版控
docker compose up -d --build --wait   # 五個服務都 healthy 才算成功
```

接著設定你在 BMAD 裡的名字。建立 `_bmad/custom/config.user.toml`，這個檔案不進版控：

```toml
[core]
user_name = "你的名字"
```

團隊共用的設定放在 `_bmad/custom/config.toml`，例如「一律用繁體中文溝通」。不要把個人設定寫進那個檔案。

## 2. 先讀哪些文件

| 文件 | 內容 |
| --- | --- |
| `_bmad-output/implementation-artifacts/sprint-status.yaml` | 每個 Story 的狀態：`backlog` → `in-progress` → `review` → `done` |
| `_bmad-output/planning-artifacts/epics.md` | 所有 Epic 與 Story 的驗收條件、〈待決事項〉 |
| `_bmad-output/implementation-artifacts/epic-<N>-context.md` | 某個 Epic 濃縮後的需求、技術決策與 UX 規則；bmad-build 會優先讀它 |
| `_bmad-output/implementation-artifacts/spec-*.md` | 已完成 Story 的 spec：Code Map、Design Notes、審查紀錄，是下一個 Story 的參考 |
| `_bmad-output/implementation-artifacts/deferred-work.md` | 審查時延後處理的問題；做到相關 Story 時要看 |
| `_bmad-output/planning-artifacts/architecture/` | 架構骨幹（AD-1～AD-21） |
| `_bmad-output/planning-artifacts/ux-designs/` | `DESIGN.md`（外觀）與 `EXPERIENCE.md`（畫面與行為，S1～S38） |
| `CLAUDE.md` | 給 Claude 的專案規則，人也值得讀一遍 |

## 3. 做一個 Story 的流程

### 3.1 認領

1. 在群組或 GitHub Issue 說你要做哪個 Story，避免兩人做同一個。
2. 先確認前置 Story 已經 `done`：
   - `epics.md` 的 Story 是照順序設計的，每個 Story 都假設前面的 Story 已經完成。
   - 具體依賴寫在 `epic-<N>-context.md` 的〈Cross-Story Dependencies〉。例如 1.7、1.8 的通知需要 1.6 的通知中心，1.8 審核的是 1.7 建立的申請。
   - 期中前有 15 個 Story 擱置，依賴它們的地方改用〈6.3 期中版規則〉的做法，不必等。
   - 前置 Story 還沒合併就開工，之後很難合併。
   - 一個 Epic 還沒有 `epic-<N>-context.md` 時，第一個做該 Epic 的人跑 bmad-build 會自動產生它，記得一起提交。

### 3.2 開分支

```bash
git switch main
git pull
git switch -c story/1-6-notification-center   # 一個 Story 一個分支
```

### 3.3 用 BMAD 產生 spec 並實作

在專案根目錄開啟 Claude Code，輸入：

```text
/bmad-build Story 1.6：通知中心（sprint key 1-6-通知中心）
```

bmad-build 的流程：

1. **讀資料**：讀 epic context 與前一個 Story 的 spec，調查程式碼。
2. **寫 spec**：寫出 `spec-<story>.md`。需求沒講清楚、只有人能決定的事，會列成「Open Questions」問你。
3. **Checkpoint**：你核准 spec 後，`<frozen-after-approval>` 區塊就鎖定，只有人能改。
4. **實作**：實作子代理依 spec 寫程式與測試，並把 `sprint-status.yaml` 改成 `in-progress`。
5. **審查**：三個審查者（Blind Hunter、Edge Case Hunter、Verification Gap）審 diff。小問題自動修正，大問題延後並記進 `deferred-work.md`。
6. **完成**：spec 標為 `done`，sprint 狀態改成 `review`。

如果要你決定的事超出 Story 範圍，例如 PRD 沒寫、會影響其他 Story 的規則，先在群組討論，再把結論寫回 spec 的 Decisions。

### 3.4 自己檢查

- `/bmad-walkthrough`：帶你看這次的變更，指出風險最高的地方與測試方法。
- `/bmad-code-review`：再跑一次獨立的審查。這是可選的，改動很大時建議跑。
- 跑 README〈測試與檢查〉的全部指令，五項都要通過：
  - 後端測試
  - 後端 lint
  - 前端 build、typecheck、biome
  - 前端單元測試
- 在瀏覽器實際走一遍，包括 375 px 寬的手機畫面。

### 3.5 Commit、PR、合併

1. 一個 Story 原則上一個 commit，spec、`sprint-status.yaml` 與程式碼一起提交。
   - 訊息格式：`feat: Story 1.6 通知中心`。
   - 審查後另外修正時，用 `fix: Story 1.6 Code Review 修正`。
2. `git push -u origin story/1-6-notification-center`，在 GitHub 開 PR 到 `main`。
3. 至少一位組員看過 PR，可以搭配 `/bmad-walkthrough` 或 `/bmad-code-review` 一起看。
4. 合併後，把 `sprint-status.yaml` 裡這個 Story 改成 `done`，提交到 `main`。

## 4. 容易出問題的地方

| 情況 | 怎麼做 |
| --- | --- |
| 改了程式，測試卻還是舊的結果 | backend、frontend 容器是 build 時複製原始碼，沒有掛載。改完要 `docker compose up -d --build --wait` 再跑測試；開發時可改用 `docker compose up --build --watch` 自動同步 |
| 後端 API 有變動 | 執行 `bash scripts/generate-client.sh` 重新產生 `frontend/src/client`，不要手改 |
| 新增前端頁面 | `frontend/src/routeTree.gen.ts` 由 vite build 產生，不要手改。要在本機更新它，把整個 `frontend/` 掛進容器跑 `bunx vite build`；只掛 `src/` 會出現 `EXDEV` 錯誤 |
| 兩個分支都新增了 Alembic 遷移 | 合併後會有兩個 head。後合併的那支要把 `down_revision` 改成先合併那支的 revision，再跑 `alembic heads`，確認只剩一個 head |
| `sprint-status.yaml`、`deferred-work.md` 衝突 | 兩邊的修改都保留。`deferred-work.md` 只能新增項目，不修改別人的項目；項目已經處理完時才刪除 |
| 產生的檔案衝突（`frontend/src/client/`、`routeTree.gen.ts`） | 不要手動合併，合併其他檔案後重新產生 |
| 換行字元 | 一律 LF（`.gitattributes` 已設定）。Windows 上用 Python 改檔要用二進位模式，否則會寫成 CRLF，`.sh` 腳本會壞掉 |
| 時間 | 後端一律 `app.core.clock.now()`；跟期限有關的測試用 `frozen_clock` 推進時間，不要等真實時間 |

## 5. 不要做的事

- 不要提交 `.env` 或任何真實密碼、金鑰。
- 不要直接推 `main`，一律走 PR。
- 不要修改別人 spec 的 `<frozen-after-approval>` 區塊；需求要改時先討論。
- 不要用 npm 安裝前端套件，一律用 Bun。也不要產生 `package-lock.json`。
- 沒有共識前不要修改 `docs/` 的期中交付文件。

## 6. 期中分工與範圍（2026-10-28 定案）

目標：**11/18 期中前完成全部 30 個主線 Story**，Demo 一場從主辦方申請、建立賽事、報名分配、抽籤、場次到申訴的完整賽事。其餘 15 個 Story 擱置到期中之後。

### 6.1 分工（依模組）

同一個模組裡前後相依的 Story 交給同一個人。組員名字開會後填入。

| 組員 | 負責模組 | 主線 Story | 數量 |
| --- | --- | --- | --- |
| A：【待填】 | identity、worker 排程、對戰樹畫面、整體驗收 | 1.7、1.8、4.6、5.2、5.8、7.1、7.2、7.3 | 8 |
| B：【待填】 | tournaments、disputes（申訴） | 2.1、2.2、2.4、2.7、6.1、6.2、6.5 | 7 |
| C：【待填】 | registration、disputes（檢舉） | 3.1、3.2、3.3、3.4、3.5、3.6、6.4 | 7 |
| D：【待填】 | competition | 4.1、4.3、4.4、5.1、5.3、5.4、5.5、5.6 | 8 |

已完成：1.1～1.4；1.5 已實作、待審查。

### 6.2 擱置的 Story（期中前不做）

1.6、2.3、2.5、2.6、2.8、3.7、3.8、3.9、3.10、3.11、4.2、4.5、4.7、5.7、6.3

在 `sprint-status.yaml` 的行尾以「擱置」註解標示，狀態維持 `backlog`。若工具改寫檔案、註解消失，以本節為準。

### 6.3 期中版規則

完整規則與每個 Story 的調整寫在 `_bmad-output/planning-artifacts/epics.md` 的〈期中範圍〉一節與各 Story 末尾的「期中版調整」，`bmad-build` 會一起讀到；兩邊不一致時以 `epics.md` 為準。做 Story 時，用到的規則寫進該 Story spec 的 Decisions（CLAUDE.md 規定使用者的決定要記在 spec）。重點：

- **只做主線需要的部分**：被擱置 Story 負責的流程（撤回、退回、退賽遞補、修改與取消賽事等）不做。
- **通知**：1.6 通知中心擱置。需要通知的地方只用 `core.events.publish` 發出事件，不登錄通知規則；期中後補 1.6 時再接上。
- **BO 數**：2.3 擱置，每一輪都用建立賽事時設定的 BO（預設帶入遊戲的 BO）。
- **賽事模式**：3.10 擱置，期中只開放校園賽；2.2 不顯示模式選項，自訂模式相關的部分都到期末。
- **抽籤**：4.2 擱置，只做主辦方手動抽籤（4.1）；報名截止後的賽事也能按「抽籤」。
- **6.5 取消資格**：4.5 擱置，不做候補遞補。該隊還沒比賽 → 對手輪空晉級；已贏過 → 由最近一場輸給它的隊伍頂替；抽籤前取消 → 不立即遞補，名額留給之後的分配。
- **6.3 擱置**：只少了申訴逾期提醒與「棄權計時暫停」的提示。申訴還沒處理時下一場本來就不起算棄權（兩隊未確定），5.1、5.2 照原規則做。
- **6.4 檢舉入口**：3.9 擱置，只在 S2 總覽放「檢舉隊伍」。
- **1.8 核准後**：沒有通知輪詢，申請人重新整理頁面後才出現主辦方身分。
- **7.1 示範資料**：只放校園賽，不放自訂模式的賽事。

Epic 1～7 的 context（`_bmad-output/implementation-artifacts/epic-*-context.md`）已預先產生，含期中規則與交接期限。`_bmad/custom/bmad-build.toml` 讓 `bmad-build` 依 git commit 判斷 context 是否過期，clone 或 pull 後不會重新產生，不必再 `touch`。修改 `planning-artifacts/` 但不影響需求內容時（改 metadata、刪備份），在 commit 訊息 body 加一行 `Epic-Context: unaffected`，避免全組的 context 被判定過期。

### 6.4 時程與交接期限

| 期間 | A | B | C | D |
| --- | --- | --- | --- | --- |
| 10/29～10/30 | 約定介面、建立種子腳本 | 約定介面 | 約定介面 | 約定介面 |
| 第 1 週（～11/3） | 1.7、1.8 | 2.1 → 2.2 → 2.4 | 3.1、3.2 | 4.1、4.3 |
| 第 2 週（11/4～11/10） | 4.6、7.1 | 2.7，依約定介面準備 6.x | 3.3、3.4、3.5 | 4.4、5.1、5.3 |
| 第 3 週（11/11～11/15） | 5.2、5.8 | 6.1、6.2、6.5 | 3.6、6.4 | 5.4、5.5、5.6 |
| 11/16～11/17 | 7.2、7.3 | 全組整合與演練 | | |

跨人交接的期限，晚了下游就會卡住：

| 期限 | 要完成 | 等待的人 |
| --- | --- | --- |
| 10/31 | B 的 2.2（賽事資料表） | C、D |
| 11/1 | A 的 1.8（後台版面與元件） | B（2.1、2.2 的畫面） |
| 11/3 | D 的 4.1（對戰表） | A（4.6） |
| 11/3 | C 的 3.1（Invite link field 元件） | B（2.7） |
| 11/6 | B 的 2.7（裁判） | D（4.4） |
| 11/7 | D 的 5.1（報到） | A（5.2） |
| 11/11 | D 的 5.4、A 的 5.2 | B（6.1）、D（5.6） |
| 11/12 | D 的 5.5、C 的 3.6 | A（5.8）、B（6.2、6.5）、D（4.1 接上真資料） |
| 11/13 | C 的 6.4（檢舉） | B（6.5） |

### 6.5 不要互相等的做法

- **先約定介面（10/29～10/30）**：每個模組負責人寫下別人會呼叫的 `service.py` 公開函式（名稱、參數、回傳的 schema）與別人需要的資料表欄位。下游照約定先寫，不等上游合併。
- **共用的開發種子資料**：A 建立種子腳本，每個人把自己模組的資料加進去（主辦方帳號、兩款遊戲與段位表、裁判、32 隊正取、已抽籤的賽事）。這份腳本之後長成 Story 7.1。
- **純邏輯先寫**：例如 4.1 的對戰表計算先寫成函式與單元測試；4.6 的對戰樹畫面先用假資料。
- **每天至少把 `main` 合併進自己的分支一次**，並在合併後重新 `docker compose up -d --build --wait`。

### 6.6 動到別人模組時的範圍

- **5.2（A）在 competition 模組**：只新增棄權判定的檔案與 worker 工作，不修改 D 的 `service.py` 既有函式；需要的查詢請 D 在 `service.py` 提供公開函式。
- **6.4（C）在 disputes 模組**：只新增檢舉相關的檔案；6.5 由 B 接續。
- **6.5（B）在 competition 模組**：取消資格的對戰表頂替（`BracketService.disqualify()`）由 B 實作。頂替邏輯寫在 competition 新增的檔案，`service.py` 只新增 `disqualify` 這個公開函式給 disputes 呼叫，不修改 D 的既有函式；輪空確認與晉級沿用 D 在 5.5 提供的函式，缺少的查詢請 D 在 `service.py` 提供公開函式。D 審查這部分的 PR。
- **4.6、5.8（A）在前端 `features/competition`**：與 D 的頁面用不同檔案。

### 6.7 11/11 進度檢查

進度落後時，依序把下列 Story 延到期末：6.5 → 6.4 → 5.6 → 5.8 → 7.3。

無論如何要保住期中 Demo 的 13 個主幹：1.7、1.8、2.1、2.2、2.4、3.1～3.6、4.1、4.6（主辦方申請到抽籤、對戰樹）。
