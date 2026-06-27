---
name: hermes-session-analysis
description: Analyze Hermes Agent session persistence, database structure, and Web UI display mechanisms
category: devops
---

# Hermes Agent Session Analysis

Skill for analyzing Hermes Agent's session persistence mechanism, database structure, and Web UI display behavior. Use when investigating why sessions appear/disappear, verifying data integrity, or understanding the session lifecycle.

## When to Load

Load this skill when:
- User asks why some conversation history disappears after restart
- Need to verify session persistence is working correctly
- Investigating discrepancies between database records and Web UI display
- Analyzing session data integrity or backup mechanisms
- User wants to understand where conversations are stored

## Key Architecture Facts

### Triple Storage Mechanism (CRITICAL)

Hermes Agent has **three separate data stores**, and they are NOT automatically kept in sync:

| Storage Type | Location | Format | Purpose | Session Count (2026-05-28) |
|-------------|----------|--------|---------|---------------------------|
| **Hermes CLI DB** | `~/.hermes/state.db` | SQLite | CLI queries, backup scripts, `hermes sessions` | 321 |
| **Web UI DB** | `~/.hermes-web-ui/hermes-web-ui.db` | SQLite | Web UI display, local session store | 124 (only api_server source) |
| **JSON Backup** | `~/.hermes/sessions/*.json` | JSON files | Persistence across restarts, recovery | ~497 |

**⚠️ PITFALL: The two SQLite databases are completely separate files.** The Web UI does NOT read `~/.hermes/state.db` directly. It has its own DB at `~/.hermes-web-ui/hermes-web-ui.db` with a **different schema** (includes `profile`, `preview`, `last_active`, `workspace` columns). The `syncAllHermesSessionsOnStartup` function copies sessions from Hermes CLI DB to Web UI DB, but **only once** — it skips if the Web UI DB already has records (`if(G&&G.count>0) { p.info("skipping"); return }`).

**This is the #1 cause of "Web UI shows fewer sessions than CLI":** After the initial sync, any new sessions created in the CLI side are never propagated to the Web UI DB until the Web UI is restarted with an empty DB.

**Also important:** These counts can diverge across all three stores. Orphan JSON files accumulate from crashes/restarts. The `backup_sessions` script (see `robust-db-persistence`) reconciles JSON↔CLI-DB but does NOT touch the Web UI DB.

### Profile vs User ID (Critical Distinction)

The Web UI's "使用者" dropdown is a **Profile selector**, not a user identity system:

| Concept | Where Stored | Values | Purpose |
|---------|-------------|--------|---------|
| **Profile** | BFF `sessions.profile` (Web UI DB) | "default", custom names | Configuration isolation (model, gateway) |
| **user_id** | BFF `sessions.user_id` (Hermes CLI DB) | ALL NULL | User identity (never populated) |

The BFF's `createSession` INSERT omits `user_id` entirely. The BFF proxy does NOT forward any user identity header to the API Server. The API Server does NOT parse the OpenAI `user` body field. All sessions have `user_id = NULL`.

See `user-id-system` skill for implementation plan to add real user identity.

### Web UI Database Schema (separate from Hermes CLI DB)

The Web UI DB (`~/.hermes-web-ui/hermes-web-ui.db`) has a **different schema** from the Hermes CLI DB:

**Web UI sessions table** (24 columns, differs from CLI's 29):
```sql
-- Columns present in Web UI but NOT in CLI DB:
profile (TEXT)        -- Profile name (e.g., "default")
preview (TEXT)        -- First user message preview (63 chars)
last_active (REAL)    -- MAX(message.timestamp) or started_at
workspace (TEXT)      -- User-assigned workspace tag

-- Columns in CLI DB but NOT in Web UI DB:
model_config          -- Model configuration JSON
system_prompt         -- System prompt text
parent_session_id     -- For child sessions
billing_provider, billing_base_url, billing_mode  -- Billing fields
cache_read_tokens, cache_write_tokens, reasoning_tokens  -- Extended token counts
api_call_count        -- API call counter
handoff_state, handoff_platform, handoff_error     -- Device handoff fields
```

### Database Schema (Hermes CLI DB)

**sessions table** (29 columns):
```sql
-- Core identity
id (TEXT)              -- Session UUID or timestamp format
source (TEXT)          -- Platform: api_server, telegram, etc.
user_id (TEXT)         -- User identifier
model (TEXT)           -- Model used (e.g., qwen/qwen3.5-397b-a17b)
started_at (REAL)      -- Unix timestamp when session started
ended_at (REAL)        -- NULL = still active
end_reason (TEXT)      -- Why session ended
message_count (INT)    -- Number of messages

-- Extended fields
title (TEXT)           -- Session title (often NULL, auto-generated)
parent_session_id (TEXT) -- For child sessions (compression, subagents)
-- ... billing, token counts, handoff metadata
```

**messages table** (14 columns):
```sql
id (INTEGER)           -- Message ID
session_id (TEXT)      -- Foreign key to sessions.id
role (TEXT)            -- 'user', 'assistant', 'tool'
content (TEXT)         -- Message content
timestamp (REAL)       -- Unix timestamp
tool_calls (TEXT)      -- JSON array of tool calls
finish_reason (TEXT)   -- 'stop', 'tool_calls', etc.
```

### Web UI Display Flow

```
User opens Web UI
 ↓
GET /api/sessions?limit=20&offset=0
 ↓
Web UI Server (Koa, /opt/hermes-web-ui/dist/server/index.js)
 ↓
Checks sessionStore mode (ZG() function):
 ├─ "local" mode → queries Web UI's own hermes-web-ui.db
 │    └─ listSessionSummaries() / mZ() function
 └─ "hermes" mode → queries Hermes CLI's state.db
      └─ Falls back to CLI query (zs()) if Web UI DB query fails
 ↓
Returns JSON response
 ↓
Web UI renders session list
```

**⚠️ Key Insight: The Web UI has TWO session query paths:**

1. **Primary path (local store)**: Reads from `~/.hermes-web-ui/hermes-web-ui.db` — the Web UI's own SQLite DB. This is used by default when `sessionStore === "local"` (which is the default, set by `SESSION_STORE` env var).

2. **Fallback path**: If the primary DB query fails, it falls back to calling Hermes CLI's session listing function (`zs()`), which reads from `~/.hermes/state.db`. But this fallback only triggers on **errors**, not on data divergence.

3. **Startup sync**: `syncAllHermesSessionsOnStartup()` copies sessions from `state.db` to `hermes-web-ui.db`, but **only when the Web UI DB is empty**. Once it has records, new CLI-side sessions are invisible to the Web UI.

**The `_C`/`qC` API handlers** also filter by source — the "Recent Sessions" endpoint (`_C`) shows all sources, while the sidebar endpoint (`qC`) **excludes `api_server` source sessions** (`b.filter(Z=>Z.source!=="api_server")`).

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
        session_id = f[8:-5]  # Remove 'session_' and '.json'
        json_ids.add(session_id)

print(f'DB sessions: {len(db_ids)}')
print(f'JSON sessions: {len(json_ids)}')
print(f'Only in DB: {len(db_ids - json_ids)}')
print(f'Only in JSON: {len(json_ids - db_ids)}')

if json_ids - db_ids:
    print('\\nSessions only in JSON (need recovery):')
    for sid in list(json_ids - db_ids)[:5]:
        print(f'  {sid}')
"
```

## Common Issues and Solutions

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

### Issue: Empty or partial session list in Web UI

**Symptoms:**
- Web UI shows far fewer sessions than `hermes sessions` CLI
- Web UI shows 1 session, CLI shows 300+

**Root Cause (Most Common):**
The Web UI DB (`~/.hermes-web-ui/hermes-web-ui.db`) is a **separate database** from the Hermes CLI DB (`~/.hermes/state.db`). The `syncAllHermesSessionsOnStartup` function only runs when the Web UI DB is empty. Once populated, new CLI-side sessions never appear in the Web UI.

**Diagnosis:**
```bash
# Compare session counts across both DBs
python3 /tmp/check_dbs.py
```

```python
# /tmp/check_dbs.py
import sqlite3

# Web UI DB
try:
    conn = sqlite3.connect(os.path.expanduser('~/.hermes-web-ui/hermes-web-ui.db'))
    c = conn.execute('SELECT COUNT(*) FROM sessions')
    webui_count = c.fetchone()[0]
    c = conn.execute("SELECT COUNT(*) FROM sessions WHERE source != 'api_server'")
    non_api = c.fetchone()[0]
    conn.close()
except Exception as e:
    webui_count = f"error: {e}"

# Hermes CLI DB
try:
    conn = sqlite3.connect(os.path.expanduser('~/.hermes/state.db'))
    c = conn.execute('SELECT COUNT(*) FROM sessions')
    cli_count = c.fetchone()[0]
    conn.close()
except Exception as e:
    cli_count = f"error: {e}"

print(f"Web UI DB: {webui_count} sessions")
print(f"Hermes CLI DB: {cli_count} sessions")
if isinstance(webui_count, int) and isinstance(cli_count, int):
    print(f"Gap: {cli_count - webui_count} sessions missing from Web UI")
```

**Solutions:**
1. **Incremental sync script** (recommended): Add a Phase in `backup_sessions` cron to sync new sessions from `state.db` → `hermes-web-ui.db`. Requires schema column mapping (Web UI DB has `profile`, `preview`, `last_active`, `workspace`; CLI DB has `model_config`, `system_prompt`, `parent_session_id`, etc.)
2. **Restart Web UI with empty DB**: `rm ~/.hermes-web-ui/hermes-web-ui.db && restart web-ui` — triggers full re-sync but loses Web UI-specific data (workspace assignments)
3. **Change sessionStore to "hermes"**: Set `SESSION_STORE=hermes` env var for Web UI — makes it query `state.db` directly instead of its own DB

**Other checks:**
1. API endpoint responding: `curl http://localhost:8648/api/sessions`
2. Gateway status: `cat /data/.hermes/gateway_state.json`
3. Source filter in UI (sidebar endpoint excludes `api_server` source)

### Issue: Session shows wrong message count

**Symptoms:**
- `message_count` in sessions table doesn't match actual messages

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

If database is lost but JSON files exist:

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

## Best Practices

### Preventing Session Loss

1. **Graceful shutdown** - Always close Hermes Agent properly
2. **Regular backups** - Set up cron to backup `/data/.hermes/`
3. **Monitor disk space** - Ensure JSON files can be written
4. **Check gateway health** - `cat /data/.hermes/gateway_state.json`

### Performance Optimization

1. **Index maintenance** - Ensure indexes on `session_id` and `timestamp`
2. **Periodic cleanup** - Remove very old sessions if needed
3. **Pagination** - Web UI uses limit/offset, don't load all sessions

## References

- `references/session-persistence-analysis.md` — Original session persistence investigation (2026-05-11)
- `references/webui-dual-db-architecture.md` — Web UI dual-DB architecture, sync mechanism, schema mapping, deobfuscated function names

- Hermes CLI DB: `~/.hermes/state.db` (primary session store, used by `hermes sessions`)
- Web UI DB: `~/.hermes-web-ui/hermes-web-ui.db` (Web UI's own DB, different schema)
- Web UI server bundle: `/opt/hermes-web-ui/dist/server/index.js` (compiled, key logic in minified JS)
- Session backups: `~/.hermes/sessions/`
- Gateway state: `~/.hermes/gateway_state.json`
- Web server code: `/usr/local/lib/python3.11/site-packages/hermes_cli/web_server.py`
- State module: `/usr/local/lib/python3.11/site-packages/hermes_state.py`
- Data sync module: `/app/src/data_sync.py`

## Related Skills

- `hermes-agent` - General Hermes Agent configuration and management
- `robust-db-persistence` - Session backup pipeline (JSON↔DB sync, HF upload) — does NOT sync Web UI DB
- `debugging` - General debugging methodologies
