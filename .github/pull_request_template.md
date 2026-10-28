<!-- 標題格式：feat: Story 4.1 主辦方提前抽籤並產生對戰表（修正用 fix:，文件用 docs:，雜項用 chore:） -->

## Story

- Story：<!-- 例如 4.1 -->
- Spec：<!-- _bmad-output/implementation-artifacts/spec-*.md 的連結 -->
- 用到的期中版規則：<!-- epics.md〈期中範圍〉第幾項；沒有就寫「無」 -->

## 變更摘要

<!-- 3～5 行：做了什麼、刻意沒做什麼。可以貼 /bmad-walkthrough 的摘要 -->

## 給審查者

<!-- 風險最高的地方、建議怎麼測。動到別人模組時說明範圍（CONTRIBUTING 6.6） -->

## 檢查清單

- [ ] CI 全綠（後端測試與 lint、前端 build／typecheck／biome／單元測試、Alembic 單一 head、API client 一致）
- [ ] 已在瀏覽器實際走過，含 375 px 寬的手機畫面（有畫面變動時附截圖）
- [ ] 跨模組呼叫只用對方 `service.py` 的公開函式；新增的公開函式已寫在 PR 說明
- [ ] 新的延後項目已寫進 `deferred-work.md`
- [ ] 合併前：`sprint-status.yaml` 這個 Story 已改成 `done`
