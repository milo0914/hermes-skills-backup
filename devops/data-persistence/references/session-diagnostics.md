# Session Diagnostics Reference

*Absorbed from `hermes-session-analysis` skill on 2026-05-16*

## Diagnostic Commands

### Check Database Status

```bash
# Count total sessions
python3 -c "import sqlite3; conn = sqlite3.connect('/data/.hermes/state.db'); print(conn.execute('SELECT COUNT(*) FROM sessions').fetchone()[0])"

# List recent sessions
python3 -c "
import sqlite3
conn = sqlite3.connect('/data/.hermes/state.db')
for row in conn.execute('SELECT id, source, started_at, message_count FROM sessions ORDER BY started_at DESC LIMIT 10'):
 print(row)
"

# Check for orphaned sessions (in DB but no messages)
python3 -c "
import sqlite3
conn = sqlite3.connect('/data/.hermes/state.db')
cursor = conn.execute('''
 SELECT s.id, s.message_count, 
 (SELECT COUNT(*) FROM messages m WHERE m.session_id = s.id) as actual
 FROM sessions s
 WHERE s.message_count != (SELECT COUNT(*) FROM messages m WHERE m.session_id = s.id)
''')
for row in cursor:
 print(row)
"
```

### Check JSON Backup Files

```bash
# Count JSON files
ls -1 /data/.hermes/sessions/*.json | wc -l

# List recent JSON files by modification time
ls -lt /data/.hermes/sessions/*.json | head -20

# Check if specific session has JSON backup
SESSION_ID="46c8d9d9-cbdf-4be5-b2eb-5723f0a8d289"
ls -la /data/.hermes/sessions/session_${SESSION_ID}.json

# Verify JSON structure
python3 -c "
import json
with open('/data/.hermes/sessions/session_46c8d9d9-cbdf-4be5-b2eb-5723f0a8d289.json') as f:
 data = json.load(f)
 print(f\"Session ID: {data.get('session_id')}\")
 print(f\"Messages: {len(data.get('messages', []))}\")
 print(f\"Last updated: {data.get('last_updated')}\")
"
```

### Compare DB vs JSON

```bash
python3 -c "
import sqlite3
import json
import os

db_path = '/data/.hermes/state.db'
json_dir = '/data/.hermes/sessions'

# Get DB session IDs
conn = sqlite3.connect(db_path)
db_ids = set(row[0] for row in conn.execute('SELECT id FROM sessions'))

# Get JSON session IDs
json_ids = set()
for f in os.listdir(json_dir):
 if f.startswith('session_') and f.endswith('.json'):
  # Extract ID from filename
  session_id = f[8:-5] # Remove 'session_' and '.json'
  json_ids.add(session_id)

print(f'DB sessions: {len(db_ids)}')
print(f'JSON sessions: {len(json_ids)}')
print(f'Only in DB: {len(db_ids - json_ids)}')
print(f'Only in JSON: {len(json_ids - db_ids)}')

if json_ids - db_ids:
 print('\\nSessions only in JSON (need recovery):')
 for sid in list(json_ids - db_ids)[:5]:
  print(f' {sid}')
"
```

## Common Issues

### Issue: Session disappears after restart

**Symptoms:**
- Session visible in Web UI before restart
- Session missing after Hermes Agent restarts

**Root Causes:**
1. **JSON file not written** - Session created but crashed before JSON backup
2. **Database corruption** - `state.db` corrupted during shutdown
3. **ID mismatch** - JSON file exists but ID format doesn't match DB
4. **Source filtering** - Web UI filtering by source platform

**Solution:**
```bash
# 1. Check if JSON exists
ls -la /data/.hermes/sessions/session_<ID>.json

# 2. If JSON exists but not in DB, trigger recovery
# (Hermes should auto-recover on startup)

# 3. Manually verify JSON integrity
python3 -c "import json; json.load(open('/data/.hermes/sessions/session_<ID>.json'))"

# 4. If DB corrupted, restore from JSON
# (Requires stopping Hermes and manual intervention)
```

### Issue: Empty session list in Web UI

**Symptoms:**
- Web UI shows no sessions
- Database has records

**Check:**
1. API endpoint responding: `curl http://localhost:8642/api/sessions`
2. Gateway status: `cat /data/.hermes/gateway_state.json`
3. Source filter in UI (some platforms filter by default)

### Issue: Session shows wrong message count

**Diagnosis:**
```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('/data/.hermes/state.db')
cursor = conn.execute('''
 SELECT s.id, s.message_count, 
 (SELECT COUNT(*) FROM messages m WHERE m.session_id = s.id) as actual
 FROM sessions s
 WHERE s.message_count != (SELECT COUNT(*) FROM messages m WHERE m.session_id = s.id)
''')
for row in cursor:
 print(f\"Session {row[0]}: declared={row[1]}, actual={row[2]}\")
\")
```

## Recovery Procedures

### Recover Sessions from JSON to DB

```bash
python3 << 'EOF'
import sqlite3
import json
import os
from datetime import datetime

db_path = '/data/.hermes/state.db'
json_dir = '/data/.hermes/sessions'

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

recovered = 0
for fname in os.listdir(json_dir):
 if not fname.endswith('.json'):
  continue
 
 filepath = os.path.join(json_dir, fname)
 try:
  with open(filepath) as f:
   data = json.load(f)
  
  session_id = data.get('session_id')
  if not session_id:
   continue
  
  # Check if already in DB
  cursor.execute("SELECT 1 FROM sessions WHERE id = ?", (session_id,))
  if cursor.fetchone():
   continue
  
  # Insert session record
  cursor.execute("""
  INSERT INTO sessions (id, source, model, started_at, message_count)
  VALUES (?, ?, ?, ?, ?)
  """, (
   session_id,
   data.get('platform', 'unknown'),
   data.get('model', 'unknown'),
   datetime.fromisoformat(data.get('session_start')).timestamp(),
   len(data.get('messages', []))
  ))
  recovered += 1
  
 except Exception as e:
  print(f\"Error processing {fname}: {e}\")

conn.commit()
print(f\"Recovered {recovered} sessions\")
EOF
```

## Key Architecture Facts

### Dual Storage Mechanism

| Storage Type | Location | Format | Purpose |
|-------------|----------|--------|---------|
| **Primary DB** | `/data/.hermes/state.db` | SQLite | Real-time queries, Web UI source |
| **JSON Backup** | `/data/.hermes/sessions/*.json` | JSON files | Persistence across restarts, recovery |

### Database Schema

**sessions table** (29 columns):
```sql
-- Core identity
id (TEXT) -- Session UUID or timestamp format
source (TEXT) -- Platform: api_server, telegram, etc.
user_id (TEXT) -- User identifier
model (TEXT) -- Model used (e.g., qwen/qwen3.5-397b-a17b)
started_at (REAL) -- Unix timestamp when session started
ended_at (REAL) -- NULL = still active
end_reason (TEXT) -- Why session ended
message_count (INT) -- Number of messages

-- Extended fields
title (TEXT) -- Session title (often NULL, auto-generated)
parent_session_id (TEXT) -- For child sessions (compression, subagents)
-- ... billing, token counts, handoff metadata
```

**messages table** (14 columns):
```sql
id (INTEGER) -- Message ID
session_id (TEXT) -- Foreign key to sessions.id
role (TEXT) -- 'user', 'assistant', 'tool'
content (TEXT) -- Message content
timestamp (REAL) -- Unix timestamp
tool_calls (TEXT) -- JSON array of tool calls
finish_reason (TEXT) -- 'stop', 'tool_calls', etc.
```

### Web UI Display Flow

```
User opens Web UI
 ↓
GET /api/sessions?limit=20&offset=0
 ↓
hermes_cli/web_server.py::get_sessions()
 ↓
hermes_state::SessionDB.list_sessions_rich()
 ↓
SQLite query with JOIN to messages for preview
 ↓
Ordered by last_active DESC (most recent first)
 ↓
JSON response to Web UI
 ↓
Renders session list
```

**Key query logic:**
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
WHERE ...
ORDER BY last_active DESC
LIMIT 20 OFFSET 0
```
