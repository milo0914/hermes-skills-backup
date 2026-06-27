---
name: huggingface-sync
description: Hugging Face Dataset 同步技能 - 提供 Hermes Agent 與 HF Dataset 之間的自動同步、增量備份、完整性驗證
version: 1.0.0
author: Hermes Agent
tags:
  - huggingface
  - sync
  - backup
  - dataset
  - persistence
  - cron
---

# Hugging Face Dataset 同步技能

## 概述
為 Hermes Agent 提供與 Hugging Face Dataset 之間的自動同步功能，確保對話歷史和配置數據的安全保存。支援增量同步、完整性驗證、頻率限制控制，避免超過 HF 免費層級限制。

## 觸發條件
- 用戶提到「同步到 Hugging Face」、「備份會話到 HF」、「HF Dataset 同步」
- 需要持久化保存對話歷史或配置
- 需要跨會話恢復對話狀態
- 用戶提到「備份」、「存檔」、「防止丟失」
- Cron 定時任務觸發（每 2 小時自動同步）

## 核心原則
1. **增量同步**：只上傳新增或修改的文件，節省帶寬和 API 調用
2. **頻率限制**：每 2 小時同步一次，避免超過 HF 免費層級限制
3. **完整性驗證**：自動檢測損壞或缺失的文件
4. **錯誤處理**：失敗重試和錯誤報告機制
5. **Token 安全**：使用 write 權限的 token，不提交到公共倉庫

## 步驟

### 1. 前置檢查
```bash
# 檢查 token 是否有效且具有 write 權限
python3 -c "from huggingface_hub import HfApi; api = HfApi(token='hf_...'); print(api.whoami())"

# 檢查必要文件
ls -la /data/.hermes/bin/sync_to_hf.py
ls -la /data/.hermes/.env  # 確認 AUTH_TOKEN 存在
```

### 2. 執行同步（上傳）
```bash
# 預覽模式（不實際上傳）
python3 /data/.hermes/bin/sync_to_hf.py --dry-run

# 實際執行同步（增量）
python3 /data/.hermes/bin/sync_to_hf.py

# 強制同步所有文件
python3 /data/.hermes/bin/sync_to_hf.py --force
```

### 3. 執行雙向同步
```bash
# 下載缺失文件
python3 /data/.hermes/bin/sync_bidirectional.py --download-only

# 上傳修改文件
python3 /data/.hermes/bin/sync_bidirectional.py --upload-only

# 完整雙向同步
python3 /data/.hermes/bin/sync_bidirectional.py
```

### 4. 完整性驗證
```bash
# 執行完整性檢查
python3 /data/.hermes/bin/integrity_check.py

# 輸出 JSON 格式報告
python3 /data/.hermes/bin/integrity_check.py --json

# 查看報告
cat /data/.hermes/logs/integrity_report.json | python3 -m json.tool
```

### 5. 監控與維護
```bash
# 查看同步日誌
tail -50 /data/.hermes/logs/sync_to_hf.log

# 查看同步狀態
cat /data/.hermes/sync_state.json | python3 -m json.tool

# 查看 Cron 任務
hermes cron list
```

## 配置文件

### 環境變量（/data/.hermes/.env）
```bash
AUTH_TOKEN=hf_你的 write 權限 token
```

### 同步腳本位置

**已安裝的腳本：**
- `/app/src/data_sync.py` — 核心同步模組（`sync_json_to_db()` + `sync_db_to_hf()`）
- `/data/.hermes/skills/devops/robust-db-persistence/scripts/backup_sessions.py` — cron 執行入口

**data_sync.py 實際行為（代碼確認 2026-05-28）：**
- `sync_json_to_db()`: 掃描 JSON 目錄，增量合併到 SQLite
- `DatasetManager.upload_to_dataset()`: 將整個 `/data/.hermes` 目錄樹透過 `upload_large_folder()` 上傳到 HF dataset（全量覆寫，非增量 diff）
- 若 `HF_DATASET_REPO` 或 `HF_TOKEN` 未設定，HF 上傳不會執行
- daemon 模式（`run_daemon()`）目前只做 watchdog 文件監聽，不再定時全量備份
- 詳見 `robust-db-persistence` 技能的 `references/pipeline-architecture.md`

**下方列出的腳本可能需要安裝或建立：**

### Cron 任務配置

**實際狀態（2026-05-28 更新）：**
- Hermes cron 中的 `session_backup` job（每 6 小時）已升級為**三階段統一同步**
- 三階段流程：
  1. **Phase 1 (JSON→DB)**：掃描 sessions/ 目錄中 DB 缺失的孤兒會話，匯入 SQLite
  2. **Phase 2 (DB→JSON)**：增量備份 SQLite 會話到 JSON 檔案（只更新有變更的）
  3. **Phase 3 (DB→HF)**：若 `HF_DATASET_REPO` 和 `HF_TOKEN` 已設定，上傳到 HF Dataset
- 腳本路徑：`/data/.hermes/skills/devops/robust-db-persistence/scripts/backup_sessions.py`
- 支援參數：`--skip-hf`（跳過 HF 上傳）、`--force-hf`（強制上傳）、`--dry-run`（預覽模式）
- 目前 HF 相關環境變數皆未設定，Phase 3 自動跳過
- 如需啟用 HF 同步，設定 `HF_DATASET_REPO` 和 `HF_TOKEN` 環境變數即可
- 舊的 `sync_daemon.py`（JSON→DB daemon）功能已合併進 Phase 1，不再需要獨立 daemon

## 常見問題與解決方案

### Token 權限不足
**問題**：`403 Forbidden: you must use a write token to upload`
**解決**：
1. 前往 https://huggingface.co/settings/tokens
2. 創建新 token，勾選 **write** 權限
3. 更新 `/data/.hermes/.env` 中的 `AUTH_TOKEN`

### 文件同步失敗
**問題**：單個文件上傳失敗
**解決**：
- 檢查網絡連通性：`curl -I https://huggingface.co`
- 檢查 token 是否過期
- 查看錯誤日誌：`tail -50 /data/.hermes/logs/sync_to_hf.log`
- 下次同步會自動重試失敗的文件

### 本地缺失文件
**問題**：本地會話文件丟失
**解決**：
```bash
# 從遠端下載缺失文件
python3 /data/.hermes/bin/sync_bidirectional.py --download-only
```

### 完整性檢查失敗
**問題**：發現損壞或不一致的文件
**解決**：
1. 查看詳細報告：`cat /data/.hermes/logs/integrity_report.json`
2. 執行雙向同步恢復：`python3 /data/.hermes/bin/sync_bidirectional.py`
3. 手動修復損壞的 JSON 文件

## 限制與合規性

### Hugging Face 免費層級限制
| 項目 | 限制 | 本系統策略 |
|------|------|-----------|
| 存儲空間 | ~10-20GB | 目前使用 <1%，完全安全 |
| API 調用 | 每小時約 100-200 次 | 每 6 小時同步 1 次（跟隨 session_backup cron） |
| Commit 頻率 | 建議間隔 >1 分鐘 | 每次全量覆寫 JSONL，一次 commit 搞定 |
| 文件大小 | 單文件 <10GB | 單個 JSONL 包含所有 sessions，通常 <10MB |

### 合規性保證
✅ 每 6 小時同步一次（跟隨 session_backup cron 排程）
✅ 全量 JSONL 覆寫（單文件 commit，非逐檔上傳）
⚠️ 無增量 diff 機制 — 每次 commit 包含所有 sessions，session 量大時文件會增長
✅ 錯誤重試機制（失敗後下次 cron 自動重試）

### ⚠️ 已知風險：全量覆寫模式
`data_sync.py` 的 `upload_large_folder()` 每次執行將整個 `/data/.hermes` 目錄樹上傳到 HF Dataset。這意味著：
- 每次 commit 包含所有 sessions 目錄的 JSON 文件
- 若 SYNC_INTERVAL 設得過短（如每分鐘），會產生大量 commit
- 建議保持 ≥6 小時間隔，或在改寫為增量模式前不要啟用

### ⚠️ sync_daemon.py 與 HF 同步的交互風險
`sync_daemon.py`（JSON→DB 同步）本身只寫本地 SQLite，不觸發 HF commit。但如果以高頻 daemon（每 5 分鐘）運行並在每次 sync 後觸發 HF 上傳，每天會產生約 288 次 commit，遠超 HF 限制。

**正確架構**：將 JSON→DB 同步合併進 session-backup cron（每 6hr），形成 3-phase pipeline：
1. Phase A: JSON→DB（補孤兒會話）
2. Phase B: DB→JSON（增量 hash 備份）
3. Phase C: DB→HF（單次 commit）

詳見 `robust-db-persistence` 技能的 Phase 2 說明。

## 參考文件
- `references/hf-token-permissions.md` - HF Token 權限說明（含創建 write token 步驟）
- `references/sync-troubleshooting.md` - 同步問題排查指南（完整診斷流程）
- `scripts/verify-sync.sh` - 同步驗證腳本（快速檢查工具）

## 支持文件說明

### 參考文檔
- **hf-token-permissions.md**：詳細說明 HF token 的權限類型、如何創建 write token、常見錯誤及解決方案
- **sync-troubleshooting.md**：完整的問題排查流程，包含錯誤代碼診斷、恢復流程、調試工具

### 腳本工具
- **verify-sync.sh**：一鍵驗證同步狀態，執行 `bash /data/.hermes/skills/devops/huggingface-sync/scripts/verify-sync.sh`

## 相關技能
- `hermes-agent` - Hermes Agent 配置與擴展
- `github-skills-backup` - GitHub 備份技能
- `cron-management` - Cron 任務管理
