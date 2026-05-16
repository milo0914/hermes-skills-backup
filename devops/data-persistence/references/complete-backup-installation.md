# Hermes 備份系統完整安裝指南

## 概述

本指南說明如何建立完整的 Hermes Agent 會話備份系統，包含：
- 自動備份 SQLite 會話數據到 JSON 文件
- 增量備份（只備份變更的會話）
- 鎖定機制防止並發執行
- HuggingFace 遠端推送（可選）
- Cron 定時任務
- GitHub 版本控制

## 文件結構

完成後的文件結構：

```
/data/.hermes/
├── state.db                    # SQLite 數據庫
├── backup_state.json           # 備份狀態追蹤
├── sessions/                   # JSON 備份目錄
│   ├── session_abc123.json
│   └── ...
├── bin/
│   ├── backup_sessions.py      # 核心備份腳本（7.9KB）
│   ├── startup_backup.sh       # 啟動備份腳本（700B）
│   ├── install_backup_system.sh # 安裝腳本（3.0KB）
│   ├── setup_backup_cron.py    # Cron 設置腳本（1.5KB）
│   ├── push_to_github_final.sh # GitHub 推送腳本（2.1KB）
│   └── .backup.lock           # 鎖定文件（運行時創建）
└── logs/
    └── backup.log             # 備份日誌
```

## 安裝步驟

### 步驟 1：準備環境

確保以下 Python 庫已安裝：
```python
import sqlite3
import json
import hashlib
import fcntl
import os
from pathlib import Path
from datetime import datetime
```

### 步驟 2：創建核心備份腳本

位置：`/data/.hermes/bin/backup_sessions.py`

功能：
- 從 SQLite 提取會話數據
- 計算 MD5 哈希值進行增量檢測
- 只備份變更的會話
- 可選推送到 HuggingFace（帶頻率限制）

關鍵特性：
```python
# 增量備份邏輯
current_hash = calculate_session_hash(session_data)
old_hash = backup_state['session_hashes'].get(session_id)

if current_hash != old_hash or not json_file.exists():
    # 只備份變更的會話
    write_json(session_data)
```

### 步驟 3：創建啟動備份腳本

位置：`/data/.hermes/bin/startup_backup.sh`

功能：
- 系統啟動時執行備份
- 300 秒超時保護
- 靜默執行（不通知用戶）

內容：
```bash
#!/bin/bash
set -e
timeout 300 python3 /data/.hermes/bin/backup_sessions.py
```

### 步驟 4：創建安裝腳本

位置：`/data/.hermes/bin/install_backup_system.sh`

功能：
- 一鍵安裝所有組件
- 設置環境變量
- 測試備份功能
- 配置 Cron 任務

執行：
```bash
bash /data/.hermes/bin/install_backup_system.sh
```

### 步驟 5：設置 Cron 任務

使用 Hermes cron 命令：
```bash
hermes cron create \
  --schedule "0 */6 * * *" \
  --name "session-backup" \
  --prompt "Backup Hermes Agent sessions to JSON" \
  --deliver local
```

或使用 Python 腳本：
```bash
python3 /data/.hermes/bin/setup_backup_cron.py
```

### 步驟 6：配置環境變量（可選）

如需 HuggingFace 推送，設置：
```bash
export HF_REPO="milo0914/hermes-sessions-backup"
export HF_BRANCH="main"
export HF_TOKEN="your_token_here"
export HF_MAX_COMMITS_PER_HOUR=5
export HF_MIN_INTERVAL_SECONDS=600
```

### 步驟 7：推送至 GitHub（可選）

獲取 GitHub Personal Access Token：
1. 訪問：https://github.com/settings/tokens/new
2. 勾選權限：`repo`, `workflow`
3. 複製 Token

執行推送：
```bash
export GITHUB_TOKEN="ghp_xxx"
bash /data/.hermes/bin/push_to_github_final.sh
```

## 使用說明

### 手動執行備份
```bash
python3 /data/.hermes/bin/backup_sessions.py
```

### 查看備份狀態
```bash
cat /data/.hermes/backup_state.json
```

### 查看已備份的會話
```bash
ls -lh /data/.hermes/sessions/
```

### 查看 Cron 任務
```bash
hermes cron list
```

### 系統啟動時自動備份
```bash
# 添加到 ~/.bashrc
echo "/data/.hermes/bin/startup_backup.sh" >> ~/.bashrc
```

## 頻率限制說明

### HuggingFace 限制
- 每小時最多提交：5 次
- 提交間隔：至少 10 分鐘（600 秒）
- 每日最多提交：20 次

### 實現方式
```python
def should_push_to_remote(backup_state):
    now = time.time()
    
    # 檢查每日限制
    if backup_state.get('last_commit_time'):
        last_commit = datetime.fromisoformat(backup_state['last_commit_time'])
        if (datetime.now() - last_commit).days > 0:
            backup_state['commits_today'] = 0
    
    # 檢查每小時限制
    if backup_state.get('commits_today', 0) >= HF_MAX_COMMITS_PER_HOUR:
        return False, "Hourly limit reached"
    
    # 檢查間隔
    if backup_state.get('last_commit_time'):
        last_commit = datetime.fromisoformat(backup_state['last_commit_time'])
        elapsed = now - last_commit.timestamp()
        if elapsed < HF_MIN_INTERVAL_SECONDS:
            return False, f"Only {elapsed:.0f}s since last commit"
    
    return True, "OK"
```

## 常見問題

### 問題 1：鎖定文件未清理
**症狀：** `Backup already running`

**解決方法：**
```bash
rm /data/.hermes/bin/.backup.lock
```

### 問題 2：HuggingFace 推送失敗
**症狀：** `429 Too Many Requests`

**解決方法：**
- 檢查 `backup_state.json` 中的提交計數
- 等待 10 分鐘後重試
- 考慮減少推送頻率

### 問題 3：GitHub 認證失敗
**症狀：** `fatal: Authentication failed`

**解決方法：**
- 確認 Token 有效且未過期
- 確認 Token 有 `repo` 權限
- 重新生成 Token

### 問題 4：SQLite 數據庫鎖定
**症狀：** `sqlite3.OperationalError: database is locked`

**解決方法：**
- 使用 `timeout=30` 參數
- 在低峰期執行備份
- 使用只讀連接：`sqlite3.connect(f'file:{db}?mode=ro', uri=True)`

## 驗證步驟

1. **檢查 JSON 文件是否存在**
   ```bash
   ls -lh /data/.hermes/sessions/
   ```

2. **驗證備份狀態**
   ```bash
   cat /data/.hermes/backup_state.json
   ```

3. **測試手動備份**
   ```bash
   python3 /data/.hermes/bin/backup_sessions.py
   ```

4. **檢查 Cron 狀態**
   ```bash
   hermes cron list
   ```

5. **驗證會話數量**
   ```bash
   ls /data/.hermes/sessions/*.json | wc -l
   ```

## 安全提示

- ⚠️ 不要將 Token 提交到 Git
- ⚠️ 不要公開分享 Token
- ✅ Token 已包含在 `.gitignore` 中
- ✅ 定期更新 Token（建議 90 天）
- ✅ 使用最小權限原則

## 相關文件

- `/data/.hermes/bin/backup_sessions.py` - 核心備份腳本
- `/data/.hermes/bin/startup_backup.sh` - 啟動備份腳本
- `/data/.hermes/bin/install_backup_system.sh` - 安裝腳本
- `/data/.hermes/bin/push_to_github_final.sh` - GitHub 推送腳本
- `/data/.hermes/backup_state.json` - 備份狀態文件
- `/tmp/GITHUB_PUSH_GUIDE.md` - GitHub 推送指南

## 下一步

1. ✅ 完成首次備份
2. ⏳ 設置系統啟動時自動執行
3. ⏳ 配置 HuggingFace 推送（如需遠程備份）
4. ⏳ 定期檢查備份狀態
5. ⏳ 考慮實施清理策略（刪除 30 天前的備份）
