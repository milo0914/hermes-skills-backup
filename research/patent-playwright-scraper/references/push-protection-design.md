# 推送防護設計 — 防止 Agent 一般 git 流程覆蓋舊報告

## 問題場景

Agent 執行專利調研時，若不知道 patent-playwright-scraper skill 已有內建推送腳本，
可能自行用一般 git 流程推送到 `milo0914/hermes-patent-research`：

```bash
# ❌ 危險的一般 git 流程
git clone https://github.com/milo0914/hermes-patent-research.git /tmp/work
cd /tmp/work
cp new_report.md ./
cp extracted_patents.json ./
git add -A && git push origin main
```

**覆蓋風險**：
1. 散檔同名覆蓋（`report.md` 蓋掉舊的 `report.md`）
2. `git add -A` 可能包含刪除操作（本地沒有舊壓縮檔 → 被視為「已刪除」）
3. Agent 在 /tmp 操作，推送完不保留副本

## 三層防禦設計

### 防禦 1：知識面 — SKILL.md 陷阱 19

Agent 載入 skill 時看到警告：
- 絕不可用一般 git 流程推送散檔
- 必須使用 `push_patent_report_github.sh` 或 E2E 腳本內建推送
- 手動推送時的 5 步安全流程（fetch → 時間戳壓縮檔 → 只 add 新檔 → 確認 diff → push）

### 防禦 2：repo 端 — PROTECTION_RULES.md

即使 Agent 沒載入 skill，clone 下 repo 後也會看到根目錄的 `PROTECTION_RULES.md`：
- 只推送 `.tar.gz` 壓縮檔
- 禁止 `git add -A` 不檢查
- 禁止 force push
- 手動推送的 5 步安全流程

### 防禦 3：自動注入 — 推送腳本 / E2E 腳本

`push_patent_report_github.sh` v5 和 `merck_lc_e2e_2024_2026.py` 的 `push_to_github()` 中：
- 推送前自動檢查 repo 是否已有 `PROTECTION_RULES.md`
- 若無，從 `templates/PROTECTION_RULES.md` 複製到推送工作目錄
- 確保 repo 始終包含此保護文件

## 安全推送 vs 危險推送對比

| | 推送腳本（安全） | Agent 自行推送（危險） |
|---|---|---|
| 檔案格式 | `.tar.gz` 壓縮檔 | 散檔直接放入 |
| 命名規則 | `patent-report-{timestamp}.tar.gz` | 可能跟舊檔同名 |
| 歷史保護 | 先 fetch + checkout 遠端 | 可能 clone 後直接覆蓋 |
| 工作目錄 | 技能目錄下（持久化） | /tmp（被清除） |
| 增量 vs 替換 | 增量添加 | 可能替換既有檔案 |
| PROTECTION_RULES | 自動注入 | 無 |

## 修改記錄

- 2026-05-23: 初始設計，v1.2.5 加入
