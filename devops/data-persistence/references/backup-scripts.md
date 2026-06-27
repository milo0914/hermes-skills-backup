# Hermes Agent 備份腳本集合

## 核心備份腳本

### backup_sessions.py (完整版)

位置：`/data/.hermes/bin/backup_sessions.py`

```python
#!/usr/bin/env python3
"""
Hermes Agent 會話備份腳本
功能：
1. 將 SQLite 數據庫中的會話同步到 JSON 文件
2. 可選：將 JSON 備份推送到 HuggingFace（帶頻率限制）
3. 支持增量備份（只備份變更的會話）
4. 自帶鎖定機制，避免並發執行
"""

import os
import sys
import json
import sqlite3
import hashlib
import fcntl
import time
from datetime import datetime
from pathlib import Path

# 配置
HERMES_DATA_DIR = Path(os.environ.get('HERMES_DATA_DIR', '/data/.hermes'))
STATE_DB = HERMES_DATA_DIR / 'state.db'
SESSIONS_DIR = HERMES_DATA_DIR / 'sessions'
BACKUP_LOCK = HERMES_DATA_DIR / 'bin' / '.backup.lock'
BACKUP_STATE_FILE = HERMES_DATA_DIR / 'backup_state.json'

# HuggingFace 配置（從環境變量讀取）
HF_REPO = os.environ.get('HF_REPO', 'milo0914/hermes-sessions-backup')
HF_BRANCH = os.environ.get('HF_BRANCH', 'main')
HF_MAX_COMMITS_PER_HOUR = int(os.environ.get('HF_MAX_COMMITS_PER_HOUR', '5'))
HF_MIN_INTERVAL_SECONDS = int(os.environ.get('HF_MIN_INTERVAL_SECONDS', '600'))

def get_backup_state():
    """讀取上次的備份狀態"""
    if not BACKUP_STATE_FILE.exists():
        return {'last_backup': None, 'commits_today': 0, 'last_commit_time': None, 'session_hashes': {}}
    
    try:
        with open(BACKUP_STATE_FILE, 'r') as f:
            return json.load(f)
    except:
        return {'last_backup': None, 'commits_today': 0, 'last_commit_time': None, 'session_hashes': {}}

def save_backup_state(state):
    """保存備份狀態"""
    with open(BACKUP_STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def calculate_session_hash(session_data):
    """計算會話數據的哈希值"""
    return hashlib.md5(json.dumps(session_data, sort_keys=True).encode()).hexdigest()

def sync_sessions_to_json():
    """將 SQLite 中的會話同步到 JSON 文件"""
    if not STATE_DB.exists():
        print(f"錯誤：找不到數據庫 {STATE_DB}")
        return [], []
    
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(str(STATE_DB))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 獲取所有會話
    cursor.execute("SELECT id, source, model, started_at, ended_at, message_count FROM sessions ORDER BY started_at DESC")
    sessions = cursor.fetchall()
    
    synced = []
    updated = []
    
    backup_state = get_backup_state()
    
    for session in sessions:
        session_id = session['id']
        
        # 讀取該會話的所有消息
        cursor.execute("""
            SELECT id, role, content, tool_calls, timestamp, finish_reason 
            FROM messages 
            WHERE session_id = ? 
            ORDER BY timestamp ASC
        """, (session_id,))
        
        messages = []
        for msg in cursor.fetchall():
            messages.append({
                'id': msg['id'],
                'role': msg['role'],
                'content': msg['content'],
                'tool_calls': msg['tool_calls'],
                'timestamp': msg['timestamp'],
                'finish_reason': msg['finish_reason']
            })
        
        # 構建會話數據
        session_data = {
            'session_id': session_id,
            'source': session['source'],
            'model': session['model'],
            'session_start': datetime.fromtimestamp(session['started_at']).isoformat() if session['started_at'] else None,
            'last_updated': datetime.fromtimestamp(session['ended_at']).isoformat() if session['ended_at'] else datetime.now().isoformat(),
            'message_count': len(messages),
            'messages': messages
        }
        
        # 計算哈希值
        current_hash = calculate_session_hash(session_data)
        old_hash = backup_state['session_hashes'].get(session_id)
        
        # 檢查是否需要更新
        json_file = SESSIONS_DIR / f'session_{session_id}.json'
        
        if current_hash != old_hash or not json_file.exists():
            # 寫入 JSON 文件
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, ensure_ascii=False, indent=2)
            
            synced.append(session_id)
            if old_hash:
                updated.append(session_id)
            else:
                print(f"新建會話：{session_id}")
            
            # 更新哈希值
            backup_state['session_hashes'][session_id] = current_hash
    
    conn.close()
    
    # 保存狀態
    save_backup_state(backup_state)
    
    return synced, updated

def push_to_huggingface(force=False):
    """
    將備份推送到 HuggingFace
    注意：需要 HF_TOKEN 環境變量，且遵守頻率限制
    """
    hf_token = os.environ.get('HF_TOKEN')
    
    if not hf_token:
        print("警告：未設置 HF_TOKEN，跳過 HuggingFace 推送")
        return False
    
    # 檢查頻率限制
    backup_state = get_backup_state()
    now = time.time()
    
    # 重置今日計數（如果已過一天）
    if backup_state.get('last_commit_time'):
        last_commit = datetime.fromisoformat(backup_state['last_commit_time'])
        if (datetime.now() - last_commit).days > 0:
            backup_state['commits_today'] = 0
    
    if not force and backup_state.get('commits_today', 0) >= HF_MAX_COMMITS_PER_HOUR:
        print(f"已達今日提交上限 ({HF_MAX_COMMITS_PER_HOUR})，跳過推送")
        return False
    
    if backup_state.get('last_commit_time'):
        last_commit = datetime.fromisoformat(backup_state['last_commit_time'])
        elapsed = now - last_commit.timestamp()
        if elapsed < HF_MIN_INTERVAL_SECONDS:
            print(f"距離上次提交僅 {elapsed:.0f} 秒，小於間隔 {HF_MIN_INTERVAL_SECONDS} 秒，跳過推送")
            return False
    
    try:
        from huggingface_hub import HfApi
        api = HfApi()
        
        # 上傳所有會話文件
        session_files = list(SESSIONS_DIR.glob('session_*.json'))
        
        if not session_files:
            print("沒有會話文件可上傳")
            return False
        
        # 批量上傳
        print(f"準備上傳 {len(session_files)} 個會話文件到 {HF_REPO}...")
        
        # 使用 upload_folder 批量上傳
        api.upload_folder(
            folder_path=str(SESSIONS_DIR),
            repo_id=HF_REPO,
            repo_type="dataset",
            branch=HF_BRANCH,
            commit_message=f"Auto-backup: {len(session_files)} sessions ({datetime.now().isoformat()})"
        )
        
        # 更新狀態
        backup_state['commits_today'] += 1
        backup_state['last_commit_time'] = datetime.now().isoformat()
        save_backup_state(backup_state)
        
        print(f"成功推送到 HuggingFace: {HF_REPO}")
        return True
        
    except Exception as e:
        print(f"推送到 HuggingFace 失敗：{e}")
        return False

def main():
    """主函數"""
    # 獲取鎖
    lock_file = open(BACKUP_LOCK, 'w')
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except IOError:
        print("備份已在運行中，退出")
        sys.exit(0)
    
    try:
        print(f"=== Hermes 會話備份開始 ({datetime.now().isoformat()}) ===")
        
        # 第一步：同步到 JSON
        synced, updated = sync_sessions_to_json()
        print(f"同步完成：{len(synced)} 個會話，其中 {len(updated)} 個更新")
        
        if not synced:
            print("沒有變更，跳過推送")
            return
        
        # 第二步：推送到 HuggingFace（可選）
        if os.environ.get('HF_TOKEN'):
            push_to_huggingface()
        else:
            print("未設置 HF_TOKEN，僅本地備份")
        
        print("=== 備份完成 ===")
        
    finally:
        fcntl.flock(lock_file, fcntl.LOCK_UN)
        lock_file.close()

if __name__ == '__main__':
    main()
```

## 啟動時備份腳本

### startup_backup.sh

位置：`/data/.hermes/bin/startup_backup.sh`

```bash
#!/bin/bash
# Hermes Agent 啟動時自動備份腳本
# 在 hermes gateway 啟動前執行

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_SCRIPT="$SCRIPT_DIR/backup_sessions.py"

echo "=== 啟動前備份檢查 ==="

# 檢查 Python
if ! command -v python3 &> /dev/null; then
    echo "錯誤：找不到 python3"
    exit 1
fi

# 檢查備份腳本
if [ ! -f "$BACKUP_SCRIPT" ]; then
    echo "警告：備份腳本不存在，跳過備份"
    exit 0
fi

# 執行備份（帶超時）
echo "執行會話備份..."
timeout 300 python3 "$BACKUP_SCRIPT" || {
    echo "警告：備份執行失敗或超時"
    # 不中斷啟動流程
}

echo "=== 備份檢查完成 ==="
```

## 安裝腳本

### install_backup_system.sh

位置：`/data/.hermes/bin/install_backup_system.sh`

```bash
#!/bin/bash
# Hermes Agent 自動備份系統安裝腳本

set -e

echo "=== Hermes Agent 自動備份系統安裝 ==="
echo ""

SCRIPT_DIR="/data/.hermes/bin"
DATA_DIR="/data/.hermes"

# 1. 設置執行權限
echo "[1/5] 設置腳本執行權限..."
chmod +x "$SCRIPT_DIR/backup_sessions.py"
chmod +x "$SCRIPT_DIR/startup_backup.sh"
echo "✓ 完成"

# 2. 創建 .env 配置示例
echo ""
echo "[2/5] 創建環境變量配置示例..."
ENV_EXAMPLE="$DATA_DIR/.env.backup.example"
cat > "$ENV_EXAMPLE" << 'EOF'
# HuggingFace 推送配置（可選）
HF_TOKEN=your_huggingface_token_here
HF_REPO=milo0914/hermes-sessions-backup
HF_BRANCH=main
HF_MAX_COMMITS_PER_HOUR=5
HF_MIN_INTERVAL_SECONDS=600
HF_MAX_COMMITS_PER_DAY=20
EOF

echo "✓ 配置示例已創建：$ENV_EXAMPLE"

# 3. 測試備份腳本
echo ""
echo "[3/5] 測試備份腳本..."
python3 "$SCRIPT_DIR/backup_sessions.py" || {
    echo "⚠ 備份測試失敗，但已記錄錯誤"
}

# 4. 查看 Cron 任務
echo ""
echo "[4/5] 檢查 Cron 任務狀態..."
hermes cron list | grep -q "session-backup" && {
    echo "✓ Cron 任務已存在"
} || {
    echo "⚠ Cron 任務不存在，請手動創建"
}

echo ""
echo "=== 安裝完成 ==="
```

## 使用範例

### 手動執行備份

```bash
python3 /data/.hermes/bin/backup_sessions.py
```

### 設置環境變量後執行

```bash
export HF_TOKEN=your_token_here
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

## 故障排除

### 鎖定文件未釋放

```bash
rm /data/.hermes/bin/.backup.lock
```

### 數據庫被鎖定

```bash
# 等待 Hermes Agent 空閒
# 或重試備份
python3 /data/.hermes/bin/backup_sessions.py
```

### HuggingFace 推送失敗

```bash
# 檢查網絡
curl -I https://huggingface.co

# 檢查 Token
echo $HF_TOKEN

# 手動執行一次
python3 /data/.hermes/bin/backup_sessions.py
```
