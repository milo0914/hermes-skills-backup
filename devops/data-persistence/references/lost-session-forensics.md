# Lost Session Forensics — 跨 DB 追蹤遺失對話的方法論

*源自 2026-06-06 13:00-17:00 UTC+8 的 session 遺失調查*

## 確認案例

Session `63daf42f-d870-4d5d-a404-7783d9a630dc`：
- 用戶記得進行了 strategy review + eng review + phase 1-4 修正 + kaggle notebook 推送
- CLI state.db：session 記錄存在，message_count 標示高值，但 actual messages = 0
- JSON 備份：檔案僅 1,034 bytes，messages = []
- Web UI DB：37 條 messages 但全為 hermes-cli-to-webui-sync 工具操作，非真實對話
- 結論：內容永久丟失，無法從任何備份還原

## 三層追蹤方法論

當用戶報告 session 內容遺失時，依序檢查以下三個資料儲存層：

### Layer 1: CLI state.db

```bash
# 1a. 找出指定時間段的 sessions
python3 -c "
import sqlite3
from datetime import datetime
conn = sqlite3.connect('/data/.hermes/state.db')
for row in conn.execute('SELECT id, started_at, message_count, title FROM sessions ORDER BY started_at DESC'):
    ts = datetime.fromtimestamp(row[1])
    if ts.strftime('%Y-%m-%d') == 'TARGET_DATE':
        print(f'{row[0]} | started={ts} | declared_msgs={row[2]} | title={row[3]}')
"

# 1b. 驗證實際 messages 數量 vs 宣告數量
python3 -c "
import sqlite3
conn = sqlite3.connect('/data/.hermes/state.db')
session_id = 'TARGET_SESSION_ID'
actual = conn.execute('SELECT COUNT(*) FROM messages WHERE session_id = ?', (session_id,)).fetchone()[0]
declared = conn.execute('SELECT message_count FROM sessions WHERE id = ?', (session_id,)).fetchone()[0]
print(f'Declared: {declared}, Actual: {actual}')
if actual == 0 and declared > 0:
    print('WARNING: Shell session — declared messages exist but actual=0')
"
```

### Layer 2: JSON 備份

```bash
# 2a. 檢查 JSON 檔案大小與結構
python3 -c "
import json, os
fpath = '/data/.hermes/sessions/session_TARGET_SESSION_ID.json'
if os.path.exists(fpath):
    with open(fpath) as f:
        data = json.load(f)
    inner = data.get('data', {})
    if isinstance(inner, dict):
        msgs = inner.get('messages', [])
    elif isinstance(inner, list):
        msgs = inner
    else:
        msgs = []
    print(f'File size: {os.path.getsize(fpath)} bytes')
    print(f'Messages: {len(msgs)}')
    if len(msgs) == 0:
        print('WARNING: JSON backup is a shell — no messages captured')
else:
    print('JSON file does not exist — never backed up')
"

# 2b. 檢查 JSON 修改時間（判斷是否在 HF 重啟前寫入）
ls -la /data/.hermes/sessions/session_TARGET_SESSION_ID.json
# mtime = cron 備份時間（如 16:28 或 22:08）→ 非即時寫入
```

### Layer 3: Web UI DB

```bash
# 3a. Web UI session ID 可能與 CLI 不同，用時間範圍交叉比對
python3 -c "
import sqlite3
from datetime import datetime
conn = sqlite3.connect('/data/.hermes-web-ui/hermes-web-ui.db')
for row in conn.execute('SELECT id, started_at, message_count, profile FROM sessions ORDER BY started_at DESC'):
    ts = datetime.fromtimestamp(row[1])
    if ts.strftime('%Y-%m-%d') == 'TARGET_DATE':
        actual = conn.execute('SELECT COUNT(*) FROM messages WHERE session_id = ?', (row[0],)).fetchone()[0]
        print(f'WebUI {row[0][:12]}... | started={ts} | declared={row[2]} | actual={actual} | profile={row[3]}')
"

# 3b. 檢查 Web UI messages 是否為 sync 工具操作（非真實對話）
python3 -c "
import sqlite3
conn = sqlite3.connect('/data/.hermes-web-ui/hermes-web-ui.db')
rows = conn.execute('SELECT role, SUBSTR(content, 1, 80) FROM messages WHERE session_id = ? LIMIT 5', ('WEBUI_SESSION_ID',)).fetchall()
for r in rows:
    print(f'{r[0]}: {r[1]}')
# 如果看到 'hermes-cli-to-webui-sync' 或 sync 工具名稱 → 不是真實對話
"
```

### Layer 4: 全域關鍵字搜尋（最後手段）

```bash
# 在所有 sessions 的 messages 中搜尋關鍵字
python3 -c "
import sqlite3
conn = sqlite3.connect('/data/.hermes/state.db')
keywords = ['strategy review', 'eng review', 'phase 1', 'kaggle']
for kw in keywords:
    results = conn.execute('SELECT session_id, COUNT(*) FROM messages WHERE content LIKE ? GROUP BY session_id', (f'%{kw}%',)).fetchall()
    for r in results:
        print(f'Keyword \"{kw}\" → session {r[0]}: {r[1]} messages')
    if not results:
        print(f'Keyword \"{kw}\" → not found in any session')
"
```

## 診斷判準

| CLI DB messages | JSON messages | Web UI messages | 診斷 |
|----------------|---------------|-----------------|------|
| > 0 | > 0 | > 0 | 正常 |
| > 0 | 0 | — | JSON 備份缺失，可從 DB 還原 |
| 0 | 0 | > 0 (sync ops) | **Shell session** — 內容從未持久化 |
| 0 | 0 | 0 | Session 完全不存在或已清除 |

**Shell session = 內容永久丟失。** 最可能原因：HF Space 重啟時 messages 只存在於記憶體，未 flush 到磁碟。

## 預防措施

1. 縮短 cron 備份間隔（目前 CLI→WebUI sync 每 30 分鐘）
2. 兩次 cron 之間建立的 session 有遺失風險
3. Hermes 無「session 建立時立即寫入 DB」的 hook
4. 重要工作成果應同時存入 skills/ 或其他持久化路徑（skills/ 在 HF Space 重建後仍存在）

## 教訓

**將重要產出寫入 skills/ 而非只存在 session 對話中。** Session messages 可能因重啟丟失，但 `/data/.hermes/skills/` 目錄在 HF Space 重建後通常能保留。策略決策、架構審查結果、修正計畫等應即時存入 skill references 或 scripts。
