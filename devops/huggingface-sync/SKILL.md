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
- `/data/.hermes/bin/sync_to_hf.py` - 上傳同步腳本
- `/data/.hermes/bin/sync_bidirectional.py` - 雙向同步腳本
- `/data/.hermes/bin/integrity_check.py` - 完整性檢查腳本
- `/data/.hermes/bin/cron_sync.sh` - Cron 包裝腳本
- `/data/.hermes/bin/cron_integrity.sh` - 完整性檢查 Cron 腳本

### Cron 任務配置
- **同步任務**：每 2 小時執行一次（`hermes cron job "d062ca0404fb"`）
- **完整性檢查**：每天 03:00 執行（`hermes cron job "d8742e599f66"`）

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
| API 調用 | 每小時約 100-200 次 | 每 2 小時同步 1 次，每次最多 50 文件 |
| Commit 頻率 | 建議間隔 >1 分鐘 | 增量同步，避免批量提交 |
| 文件大小 | 單文件 <10GB | 會話文件通常 <1MB |

### 合規性保證
✅ 每 2 小時同步一次（遠低於每小時限制）  
✅ 增量同步（只上傳變動文件）  
✅ 單次最多 50 文件（避免批量提交）  
✅ 錯誤重試機制（失敗後自動重試）  

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
