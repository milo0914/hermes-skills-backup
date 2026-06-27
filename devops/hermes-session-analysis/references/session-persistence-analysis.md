# Hermes Agent 會話持久化機制 - 實作細節

本次分析（2026-05-11）中發現的技術細節和 SQL 查詢模式。

## 發現的問題

用戶提問：為什麼某些對話歷史在關閉視窗或系統重啟後會消失，但有些不會？

## 調查方法論

### 1. 數據庫結構分析

```python
import sqlite3

db_path = '/data/.hermes/state.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 檢查 sessions 表結構
cursor.execute("PRAGMA table_info(sessions)")
for col in cursor.fetchall():
    print(f"{col[0]}: {col[1]} ({col[2]})")

# 檢查 sessions 與 messages 的關聯
cursor.execute("""
    SELECT s.id, s.message_count, 
           (SELECT COUNT(*) FROM messages m WHERE m.session_id = s.id) as actual
    FROM sessions s
    LIMIT 10
""")
```

### 2. 關鍵 SQL 查詢模式

**列出最近的會話（含預覽）：**
```sql
SELECT s.*,
    COALESCE(
        (SELECT SUBSTR(m.content, 1, 63)
         FROM messages m
         WHERE m.session_id = s.id AND m.role = 'user'
         ORDER BY m.timestamp ASC
         LIMIT 1),
        NULL
    ) AS preview,
    COALESCE(
        (SELECT MAX(m2.timestamp)
         FROM messages m2
         WHERE m2.session_id = s.id),
        s.started_at
    ) AS last_active
FROM sessions s
ORDER BY last_active DESC
LIMIT 20
```

**檢查會話完整性：**
```sql
-- 找出只有 sessions 記錄但沒有 messages 的會話
SELECT s.id
FROM sessions s
LEFT JOIN messages m ON m.session_id = s.id
WHERE m.id IS NULL

-- 找出只有 messages 但沒有 sessions 記錄的（異常）
SELECT DISTINCT session_id
FROM messages
WHERE session_id NOT IN (SELECT id FROM sessions)
```

### 3. 雙重存儲機制驗證

```python
import os
import json

# 檢查 JSON 備份
sessions_dir = '/data/.hermes/sessions'
json_files = [f for f in os.listdir(sessions_dir) if f.endswith('.json')]

# 檢查數據庫記錄
cursor.execute("SELECT COUNT(*) FROM sessions")
db_count = cursor.fetchone()[0]

print(f"JSON 文件數：{len(json_files)}")
print(f"數據庫記錄：{db_count}")
print(f"差異：{abs(len(json_files) - db_count)}")
```

## 發現的關鍵事實

### 會話消失的原因

1. **JSON 文件未及時寫入**
   - 會話創建後立即崩潰/斷電
   - 異步備份來不及完成

2. **數據庫與 JSON 不一致**
   - 某些會話只在 JSON 中有記錄
   - 某些會話只在數據庫中有記錄

3. **Web UI 過濾條件**
   - `source` 參數過濾特定平台
   - `parent_session_id` 導致子會話被壓縮

4. **`ended_at` 為 NULL**
   - 所有會話都標記為「進行中」
   - 可能影響 UI 顯示邏輯

### 實際數據（2026-05-11 22:50）

```
數據庫會話總數：18
有消息的會話：17
空會話：1 (853505e5-64e8-40d8-adf9-42d1305acd75)
JSON 文件總數：64
```

### 會話 ID 格式

發現兩種格式並存：
1. **UUID 格式**: `46c8d9d9-cbdf-4be5-b2eb-5723f0a8d289`
2. **時間戳格式**: `20260502_152315_349039`

## 診斷腳本範本

### 快速健康檢查
```bash
python3 << 'EOF'
import sqlite3
import os

db_path = '/data/.hermes/state.db'
json_dir = '/data/.hermes/sessions'

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 基本統計
cursor.execute("SELECT COUNT(*) FROM sessions")
db_count = cursor.fetchone()[0]

json_count = len([f for f in os.listdir(json_dir) if f.endswith('.json')])

print(f"=== 會話健康檢查 ===")
print(f"數據庫記錄：{db_count}")
print(f"JSON 文件：{json_count}")
print(f"差異：{abs(db_count - json_count)}")

# 檢查空會話
cursor.execute("""
    SELECT id, started_at 
    FROM sessions 
    WHERE message_count = 0
""")
empty = cursor.fetchall()
if empty:
    print(f"\n空會話 ({len(empty)} 個):")
    for row in empty:
        print(f"  {row[0]} (開始於：{row[1]})")

conn.close()
EOF
```

## 修復建議

### 1. 定期備份
```bash
# 加入 cron，每小時備份
0 * * * * cp -r /data/.hermes/state.db /data/.hermes/backups/state.db.$(date +\%Y\%m\%d_\%H\%M)
```

### 2. 一致性檢查
```bash
# 每天檢查一次數據庫與 JSON 的一致性
python3 /path/to/consistency_check.py
```

### 3. 清理舊會話
```bash
# 清理 30 天前的會話（謹慎使用）
python3 << 'EOF'
import sqlite3
import time

conn = sqlite3.connect('/data/.hermes/state.db')
cursor = conn.cursor()

cutoff = time.time() - (30 * 24 * 3600)  # 30 days ago

cursor.execute("""
    DELETE FROM messages 
    WHERE session_id IN (
        SELECT id FROM sessions 
        WHERE started_at < ?
    )
""", (cutoff,))

cursor.execute("DELETE FROM sessions WHERE started_at < ?", (cutoff,))

conn.commit()
print(f"已清理 {cursor.rowcount} 條記錄")
conn.close()
EOF
```

## 相關文件路徑

| 文件 | 路徑 | 用途 |
|------|------|------|
| 主配置 | `/data/.hermes/config.yaml` | 系統配置 |
| 環境變量 | `/data/.hermes/.env` | API 密鑰等 |
| 狀態數據庫 | `/data/.hermes/state.db` | 會話和消息 |
| 會話備份 | `/data/.hermes/sessions/` | JSON 備份 |
| 網關狀態 | `/data/.hermes/gateway_state.json` | 運行時狀態 |
| Web 服務器 | `/usr/local/lib/python3.11/site-packages/hermes_cli/web_server.py` | API 端點 |
| 狀態模塊 | `/usr/local/lib/python3.11/site-packages/hermes_state.py` | 數據庫操作 |

## 參考文獻

- Hermes Agent 文檔：https://hermes-agent.nousresearch.com/docs
- Session persistence analysis session: 2026-05-11
- Related skill: `hermes-session-analysis`
