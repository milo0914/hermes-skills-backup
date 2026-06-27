---
name: data-persistence
description: Data persistence, session management, sync, and identity for Hermes Agent - backup, recovery, DB persistence, CLI↔WebUI sync, session ID unification, user ID, session merge, HuggingFace sync, and system health checks
category: devops
---

# Data Persistence & Backup

Skill for implementing robust data persistence strategies in Hermes Agent, including session backup/recovery, SQLite-to-JSON export, incremental synchronization, and frequency-limited remote pushes (HuggingFace, Google Drive, etc.).

## When to Load

Load this skill when:
- User asks about session persistence or backup strategies
- Need to implement automatic backup mechanisms for Hermes Agent data
- User wants to prevent data loss on system restart or conversation window close
- Need to sync SQLite database to JSON files with incremental updates
- User mentions HuggingFace commit limits or frequency restrictions
- Implementing cron-based scheduled tasks for data maintenance
- User asks "why did my conversation disappear?" or "how do I backup sessions?"

## Core Concepts

### 1. Dual Storage Architecture

Hermes Agent uses a dual storage approach:
- **Primary**: SQLite database (`/data/.hermes/state.db`) - sessions, messages, FTS indexes
- **Backup**: JSON files (`/data/.hermes/sessions/session_*.json`) - portable, human-readable

**Why both?**
- SQLite: Fast queries, full-text search, relational integrity
- JSON: Portability, version control friendly, easy to sync to remote

### 2. Incremental Backup Strategy

Never backup everything every time. Use hash-based change detection:

```python
import hashlib
import json

def calculate_session_hash(session_data):
    """Calculate MD5 hash of session data for change detection"""
    return hashlib.md5(json.dumps(session_data, sort_keys=True).encode()).hexdigest()

# Compare with previous hash
if current_hash != old_hash:
    # Only backup changed sessions
    write_json(session_data)
```

**Benefits:**
- Reduces backup time by 90%+ (only changed sessions)
- Minimizes disk I/O
- Respects remote API rate limits
- Faster execution = more frequent backups possible

### 3. Locking Mechanism

Prevent concurrent backup execution:

```python
import fcntl
import sys

lock_file = open('/data/.hermes/bin/.backup.lock', 'w')
try:
    fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
except IOError:
    print("Backup already running, exiting")
    sys.exit(0)

try:
    # Perform backup
    pass
finally:
    fcntl.flock(lock_file, fcntl.LOCK_UN)
    lock_file.close()
```

**Why locking matters:**
- Cron jobs may overlap if previous run is slow
- Manual backup while cron is running
- Multiple users on shared systems
- Prevents database corruption from concurrent writes

### 4. Frequency-Limited Remote Pushes

When syncing to remote (HuggingFace, Google Drive, etc.), respect API limits:

**HuggingFace Limits (discovered empirically):**
- Max 5 commits per hour
- Minimum 10 minutes (600s) between commits
- Recommended: Max 20 commits per day

**Implementation pattern:**

```python
import time
from datetime import datetime

def should_push_to_remote(backup_state):
    """Check if we should push to remote based on rate limits"""
    now = time.time()
    
    # Reset daily counter if needed
    if backup_state.get('last_commit_time'):
        last_commit = datetime.fromisoformat(backup_state['last_commit_time'])
        if (datetime.now() - last_commit).days > 0:
            backup_state['commits_today'] = 0
    
    # Check hourly limit
    if backup_state.get('commits_today', 0) >= HF_MAX_COMMITS_PER_HOUR:
        return False, "Hourly limit reached"
    
    # Check interval since last commit
    if backup_state.get('last_commit_time'):
        last_commit = datetime.fromisoformat(backup_state['last_commit_time'])
        elapsed = now - last_commit.timestamp()
        if elapsed < HF_MIN_INTERVAL_SECONDS:
            return False, f"Only {elapsed:.0f}s since last commit, need {HF_MIN_INTERVAL_SECONDS}s"
    
    return True, "OK"
```

## Implementation Steps

### Overview: Complete Installation Workflow

The complete backup system installation involves these components:
1. **Core backup script** (`backup_sessions.py`) - Main backup logic with incremental sync
2. **Startup script** (`startup_backup.sh`) - Runs backup on system startup
3. **Installation script** (`install_backup_system.sh`) - One-click installer
4. **Cron setup** (`setup_backup_cron.py`) - Schedules automatic backups
5. **GitHub push script** (`push_to_github_final.sh`) - Version control integration

**Reference:** See `references/complete-backup-installation.md` for the complete installation guide with all scripts.

### Step 1: Extract Session Data from SQLite

```python
import sqlite3
from pathlib import Path

STATE_DB = Path('/data/.hermes/state.db')
SESSIONS_DIR = Path('/data/.hermes/sessions')

def extract_sessions_to_json():
    """Extract all sessions from SQLite to JSON files"""
    if not STATE_DB.exists():
        raise FileNotFoundError(f"Database not found: {STATE_DB}")
    
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(str(STATE_DB))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get all sessions
    cursor.execute("""
        SELECT id, source, model, started_at, ended_at, message_count 
        FROM sessions 
        ORDER BY started_at DESC
    """)
    sessions = cursor.fetchall()
    
    for session in sessions:
        session_id = session['id']
        
        # Get all messages for this session
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
        
        # Build session data structure
        session_data = {
            'session_id': session_id,
            'source': session['source'],
            'model': session['model'],
            'session_start': datetime.fromtimestamp(session['started_at']).isoformat() if session['started_at'] else None,
            'last_updated': datetime.fromtimestamp(session['ended_at']).isoformat() if session['ended_at'] else datetime.now().isoformat(),
            'message_count': len(messages),
            'messages': messages
        }
        
        # Write to JSON
        json_file = SESSIONS_DIR / f'session_{session_id}.json'
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(session_data, f, ensure_ascii=False, indent=2)
    
    conn.close()
```

### Step 2: Implement Incremental Sync

```python
import json
import hashlib

BACKUP_STATE_FILE = Path('/data/.hermes/backup_state.json')

def get_backup_state():
    """Load previous backup state"""
    if not BACKUP_STATE_FILE.exists():
        return {'last_backup': None, 'commits_today': 0, 'last_commit_time': None, 'session_hashes': {}}
    
    try:
        with open(BACKUP_STATE_FILE, 'r') as f:
            return json.load(f)
    except:
        return {'last_backup': None, 'commits_today': 0, 'last_commit_time': None, 'session_hashes': {}}

def save_backup_state(state):
    """Save backup state"""
    with open(BACKUP_STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def sync_sessions_incremental():
    """Sync only changed sessions"""
    backup_state = get_backup_state()
    synced = 0
    updated = 0
    
    for session in sessions:  # From Step 1
        session_id = session['id']
        
        # Calculate current hash
        current_hash = calculate_session_hash(session_data)
        old_hash = backup_state['session_hashes'].get(session_id)
        
        json_file = SESSIONS_DIR / f'session_{session_id}.json'
        
        if current_hash != old_hash or not json_file.exists():
            # Write JSON (from Step 1)
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, ensure_ascii=False, indent=2)
            
            synced += 1
            if old_hash:
                updated += 1
                print(f"Updated: {session_id}")
            else:
                print(f"New: {session_id}")
            
            # Update hash
            backup_state['session_hashes'][session_id] = current_hash
    
    # Save state
    backup_state['last_backup'] = datetime.now().isoformat()
    save_backup_state(backup_state)
    
    return synced, updated
```

### Step 3: Push to Remote (Optional)

```python
def push_to_huggingface():
    """Push backup to HuggingFace with rate limiting"""
    hf_token = os.environ.get('HF_TOKEN')
    
    if not hf_token:
        print("HF_TOKEN not set, skipping remote push")
        return False
    
    backup_state = get_backup_state()
    
    # Check rate limits
    should_push, reason = should_push_to_remote(backup_state)
    if not should_push:
        print(f"Rate limit: {reason}")
        return False
    
    try:
        from huggingface_hub import HfApi
        api = HfApi()
        
        session_files = list(SESSIONS_DIR.glob('session_*.json'))
        
        if not session_files:
            print("No session files to upload")
            return False
        
        print(f"Uploading {len(session_files)} session files to {HF_REPO}...")
        
        api.upload_folder(
            folder_path=str(SESSIONS_DIR),
            repo_id=HF_REPO,
            repo_type="dataset",
            branch=HF_BRANCH,
            commit_message=f"Auto-backup: {len(session_files)} sessions ({datetime.now().isoformat()})"
        )
        
        # Update state
        backup_state['commits_today'] += 1
        backup_state['last_commit_time'] = datetime.now().isoformat()
        save_backup_state(backup_state)
        
        print(f"Successfully pushed to HuggingFace: {HF_REPO}")
        return True
        
    except Exception as e:
        print(f"Failed to push to HuggingFace: {e}")
        return False
```

### Step 4: Schedule with Cron

Create a cron job for automatic execution:

```bash
# Every 6 hours (respects rate limits)
0 */6 * * * python3 /data/.hermes/bin/backup_sessions.py
```

**Hermes cron command:**
```bash
hermes cron create \
  --schedule "0 */6 * * *" \
  --name "session-backup" \
  --prompt "Backup Hermes Agent sessions to JSON" \
  --deliver local
```

## Environment Variables

Required for full functionality:

```bash
# HuggingFace (optional - for remote push)
HF_REPO=milo0914/hermes-sessions-backup
HF_BRANCH=main
HF_TOKEN=your_huggingface_token_here

# Rate limiting (recommended)
HF_MAX_COMMITS_PER_HOUR=5
HF_MIN_INTERVAL_SECONDS=600
HF_MAX_COMMITS_PER_DAY=20
```

## File Structure

```
/data/.hermes/
├── state.db                    # Primary SQLite database
├── backup_state.json           # Backup state tracking
├── sessions/                   # JSON backup directory
│   ├── session_abc123.json
│   ├── session_def456.json
│   └── ...
├── bin/
│   ├── backup_sessions.py      # Main backup script
│   ├── startup_backup.sh       # Startup backup wrapper
│   └── .backup.lock            # Lock file (auto-created)
└── logs/
    └── backup.log              # Backup logs (if enabled)
```

## Common Pitfalls

### 0. GitHub Token Authentication Required for Remote Push

**Problem:** Cannot push to GitHub without Personal Access Token.

**Solution:**
1. Create token at: https://github.com/settings/tokens/new
2. Required scopes: `repo`, `workflow`
3. Set environment variable: `export GITHUB_TOKEN="ghp_xxxxxxxxxxxx"`
4. Use token in Git URL: `https://USERNAME:TOKEN@github.com/USER/REPO.git`

**One-line push command:**
```bash
export GITHUB_TOKEN="ghp_xxx" && \
cd /tmp/hermes-backup-github && \
git remote set-url origin "https://milo0914:${GITHUB_TOKEN}@github.com/milo0914/hermes-sessions-backup.git" && \
git branch -M main && \
git push -u origin main
```

**Security:** Never commit tokens to Git, always use `.gitignore`, rotate tokens periodically.

### 1. Missing Lock File Cleanup

**Problem:** Backup interrupted, lock file remains, future backups fail.

**Solution:**
```bash
# Manual cleanup if needed
rm /data/.hermes/bin/.backup.lock
```

**Prevention:** Always use try/finally blocks in scripts.

### 2. SQLite Database Locked

**Problem:** `sqlite3.OperationalError: database is locked`

**Cause:** Hermes Agent is writing to database while backup tries to read.

**Solution:**
- Use `timeout=30` in SQLite connection
- Schedule backups during low-activity periods
- Consider read-only connection: `sqlite3.connect(f'file:{db}?mode=ro', uri=True)`

### 3. HuggingFace Rate Limit Exceeded

**Symptoms:**
```
huggingface_hub.errors.HfHubHTTPError: 429 Too Many Requests
```

**Prevention:**
- Always implement rate limiting logic (see Step 4)
- Use incremental backups to reduce frequency needs
- Monitor `backup_state.json` for commit counts

### 6. Startup Backup Not Triggered

**Problem:** Backup doesn't run on system startup, missing sessions after restart.

**Solution A - Add to bashrc:**
```bash
# Add to ~/.bashrc or ~/.profile
echo "/data/.hermes/bin/startup_backup.sh" >> ~/.bashrc
```

**Solution B - Use systemd service (requires sudo):**
```bash
# Create service file
sudo systemctl daemon-reload
sudo systemctl enable hermes-backup.service
sudo systemctl start hermes-backup.service
```

**Solution C - Modify Hermes Gateway launch script:**
```bash
# In Hermes startup script, add before main process
/data/.hermes/bin/startup_backup.sh
```

**Prevention:** Always test startup script manually before adding to startup.

### 7. Large Session Files

**Problem:** Some sessions can be 400KB+ (78 messages), causing slow uploads.

**Solutions:**
- Compress old sessions: `gzip session_old.json`
- Implement retention policy: delete sessions > 30 days
- Split large sessions into chunks

### 8. Backup State vs Actual File Count Inconsistency

**Problem:** Three data stores diverge — JSON files, backup_state.json, and SQLite can have different counts.

**Observed (2026-05-28):** 497 JSON files, 198 tracked in backup_state.json, 206 in SQLite.

**Root causes:**
- Orphan JSON files from crashes/restarts that backup_state never tracked
- SQLite sessions that were never exported to JSON
- backup_state only tracks sessions it has successfully hashed
- No reconciliation mechanism between the three stores

**Diagnosis:**
```bash
# Compare counts across all three stores
echo "JSON files: $(ls /data/.hermes/sessions/*.json 2>/dev/null | wc -l)"
echo "SQLite sessions: $(python3 -c "import sqlite3; print(sqlite3.connect('/data/.hermes/state.db').execute('SELECT COUNT(*) FROM sessions').fetchone()[0])")"
python3 -c "import json; d=json.load(open('/data/.hermes/backup_state.json')); print(f'backup_state tracked: {len(d.get(\"session_hashes\",{}))}')"
```

**Prevention:** Periodically run `sync_json_to_db()` from `data_sync.py` to reconcile JSON→SQLite.

### 9. HF Space Restart Data Loss Window

**Problem:** On HF Spaces, container restarts wipe the SQLite DB. If the restart occurs between backup cron runs, all sessions created since the last backup are permanently lost.

**Observed (2026-06-06):** Sessions from 13:00-17:00 were lost because:
- Backup cron ran at 06:00 and 12:00 (captured morning sessions)
- Afternoon sessions were in SQLite only
- Space restarted before the 18:00 cron run
- Result: 4+ hours of sessions gone, including strategy review work

**Diagnosis:**
```bash
# Check if sessions are missing from a specific time range
python3 -c "
import sqlite3
conn = sqlite3.connect('/data/.hermes/state.db')
rows = conn.execute('SELECT date(started_at, \"unixepoch\") as d, COUNT(*) FROM sessions GROUP BY d ORDER BY d').fetchall()
for d, c in rows:
    print(f'{d}: {c} sessions')
"
```

**Mitigation strategies:**
1. Increase backup frequency to every 30 minutes (not 6 hours)
2. Add pre-shutdown hook: `trap '/data/.hermes/bin/backup_sessions.py' SIGTERM`
3. Use `sync_db_to_hf()` more frequently if HF_TOKEN is set
4. Key sessions (long tool-call chains, review work) should be explicitly exported mid-session

### 9. Session Cron is Local-Only (No Remote Push)

**Problem:** The `session_backup` cron job (`backup_sessions.py`) only exports SQLite→JSON locally. It does NOT push to HuggingFace or any remote.

**Actual architecture:**
- `cron/jobs.json`: single job `session_backup`, schedule `0 */6 * * *`
- `backup_sessions.py`: calls `data_sync.sync_json_to_db()` then `data_sync.sync_db_to_hf()`
- `sync_db_to_hf()` requires `HF_DATASET_REPO` and `HF_TOKEN` env vars — both NOT_SET in current environment
- When HF vars are not set, `sync_db_to_hf()` effectively no-ops (early return or error)
- `data_sync.py` syncs using **full-rewrite JSONL** (not incremental), which means if HF sync IS enabled, every run pushes the entire sessions table as one JSONL file

**Risk if HF sync is enabled without changes:** Every 6 hours, the entire sessions table is serialized to JSONL and committed to HF as a single file. With 200+ sessions, each commit replaces the entire file — no diff, no dedup. This is safe at 6hr intervals but would be problematic at higher frequency.

### 10. Shell Sessions After HF Space Restart (Confirmed Data Loss)

**Problem:** Session record exists in all three stores (CLI DB, JSON, Web UI DB) but messages are 0 everywhere. Content created during the session is permanently lost.

**Confirmed case:** 2026-06-06, session `63daf42f` had ~95 messages of strategy review + eng review work, but after HF Space restart all stores show 0 messages. JSON backup file exists but is only 1KB with empty messages array.

**Root cause:** Messages lived only in memory. HF Space restart destroyed the process before messages were flushed to SQLite. The cron backup job ran later and captured only the shell (session metadata without messages).

**Diagnosis:** Use `references/lost-session-forensics.md` methodology to trace across all three stores.

**Prevention:**
- Reduce cron backup interval for CLI→WebUI sync (currently 30min, sessions between runs are vulnerable)
- Write important work products to `/data/.hermes/skills/` (survives HF rebuild) immediately during the session, not just at the end
- No Hermes hook currently exists for "write messages to DB on creation"

### 5. Cold-Start Bootstrapping Gap (Full scripts/ Wipe)

**Problem:** After an HF Space rebuild, the ENTIRE `/data/.hermes/scripts/` directory is empty. The v5 self-heal logic lives inside the wrapper scripts themselves, so when all wrappers are missing, NO cron job can trigger and self-heal never executes — a bootstrapping deadlock.

**Observed:** This is the most common recurring cron failure. Occurred 2026-06-25, 2026-06-26, and likely after every HF Space rebuild. The self-heal code in each wrapper is designed to restore the OTHER wrappers when that ONE wrapper runs first, but the assumption is that at least one wrapper survives. A full wipe invalidates this assumption.

**Diagnosis:**
```bash
# Check if scripts/ is empty (indicates full wipe)
ls /data/.hermes/scripts/ | wc -l  # 0 = full wipe
# Check if skills/ still has the actual scripts (persistent)
ls /data/.hermes/skills/devops/*/scripts/  # should be non-empty
```

**Fix (one command):**
```bash
python3 /data/.hermes/skills/devops/data-persistence/scripts/heal-scripts-dir.py
```

**Verify without copying:**
```bash
python3 /data/.hermes/skills/devops/data-persistence/scripts/heal-scripts-dir.py --check
```

**Force overwrite all wrappers:**
```bash
python3 /data/.hermes/skills/devops/data-persistence/scripts/heal-scripts-dir.py --force
```

After repairing wrappers, re-trigger each failed cron: `cronjob(action='run', job_id='<id>')`

**Prevention:** After any HF Space rebuild or environment reset, the FIRST action before checking cron status is to verify scripts/ is populated. If empty, run `heal-scripts-dir.py` before relying on cron self-heal.

### 6. Encoding Issues with Special Characters

**Problem:** Chinese/Japanese characters in messages cause JSON encoding errors.

**Solution:**
```python
# Always use UTF-8 encoding
with open(json_file, 'w', encoding='utf-8') as f:
    json.dump(session_data, f, ensure_ascii=False, indent=2)
```

## Verification Steps

After implementing backup:

1. **Check JSON files exist:**
   ```bash
   ls -lh /data/.hermes/sessions/
   ```

2. **Verify backup state:**
   ```bash
   cat /data/.hermes/backup_state.json
   ```

3. **Test manual backup:**
   ```bash
   python3 /data/.hermes/bin/backup_sessions.py
   ```

4. **Check cron status:**
   ```bash
   hermes cron list
   ```

5. **Verify session count:**
   ```bash
   # Should match database
   ls /data/.hermes/sessions/*.json | wc -l
   ```

## Recovery Procedures

### From JSON to SQLite (Advanced)

If you need to restore from JSON backup:

```python
import json
import sqlite3

def restore_session_from_json(json_file, db_path):
    """Restore a single session from JSON to SQLite"""
    with open(json_file, 'r') as f:
        session_data = json.load(f)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Insert session (simplified - actual schema may vary)
    cursor.execute("""
        INSERT OR REPLACE INTO sessions (id, source, model, started_at, message_count)
        VALUES (?, ?, ?, ?, ?)
    """, (
        session_data['session_id'],
        session_data.get('source', 'restored'),
        session_data.get('model', 'unknown'),
        session_data.get('session_start'),
        len(session_data.get('messages', []))
    ))
    
    # Insert messages
    for msg in session_data.get('messages', []):
        cursor.execute("""
            INSERT OR REPLACE INTO messages 
            (session_id, role, content, timestamp)
            VALUES (?, ?, ?, ?)
        """, (
            session_data['session_id'],
            msg['role'],
            msg['content'],
            msg['timestamp']
        ))
    
    conn.commit()
    conn.close()
```

**Note:** This is complex and schema-dependent. Prefer preventing data loss over recovery.

## References

- `references/backup-scripts.md` - Complete backup script examples
- `references/rate-limit-strategies.md` - API rate limiting patterns
- `references/session-schema.md` - SQLite database schema details
- `references/github-push-guide.md` - Complete GitHub push guide with authentication and automation
- `references/complete-backup-installation.md` - Full installation guide with all scripts and cron setup (Chinese)
- `references/cron-self-heal-v5-fix.md` - Cron self-heal v5 fix: skill-level granularity + cold-start bootstrapping gap analysis
- `scripts/heal-scripts-dir.py` - One-command fix for cold-start: copy all cron wrappers from skills/ to scripts/

## Related Skills

- `hermes-agent` - Hermes Agent configuration and management
- `cron-management` - Scheduled task management

---

# Appendix: Absorbed Skills

This skill is the class-level umbrella for all Hermes Agent data persistence, session management, and synchronization concerns (as of 2026-06-03 consolidation).

## A. Session Diagnostics (from `hermes-session-analysis`)

**When to use:** Analyzing why sessions appear/disappear, verifying DB integrity, understanding Web UI display behavior.

**Key architecture:**
- Dual storage: SQLite (`state.db`) + JSON backups (`sessions/`)
- Web UI flow: `GET /api/sessions` → `SessionDB.list_sessions_rich()` → SQLite with JOIN
- Common issues: JSON not written, DB corruption, ID mismatch, source filtering

**Details:** `references/hermes-session-analysis.md`, `references/hermes-session-analysis_session-persistence-analysis.md`, `references/hermes-session-analysis_webui-dual-db-architecture.md`
**Lost session forensics:** `references/lost-session-forensics.md` — cross-store tracing methodology when messages never persisted (CLI DB + JSON + Web UI DB)

## B. System Health Checks (from `system-health-check`)

**When to use:** Verifying operational status, pre-troubleshooting checks, periodic maintenance.

**Core checks:** Configuration files, Database status, Session files, Gateway status, Memory system, Cron jobs.

**Details:** `references/system-health-check.md`

## C. Robust DB Persistence (from `robust-db-persistence`)

**When to use:** Ensuring sessions are written to DB immediately at creation time, eliminating JSON↔SQLite sync gaps.

**Key insight:** 3-phase pipeline operates on `state.db` only; Web UI DB (`hermes-web-ui.db`) has separate schema and does not auto-sync after initial population.

**Details:** `references/robust-db-persistence.md`, `references/robust-db-persistence_pipeline-architecture.md`
**Scripts:** `scripts/robust-db-persistence_backup_sessions.py`, `scripts/robust-db-persistence_sync_json_to_db.py`, `scripts/robust-db-persistence_sync_daemon.py`

## D. CLI → Web UI Sync (from `hermes-cli-to-webui-sync`)

**When to use:** CLI sessions not appearing in Web UI, or sessions visible but with empty message content.

**Key mechanism:** Incremental sync of both `sessions` and `messages` tables from `state.db` to `hermes-web-ui.db`.

**Critical pitfall — scripts/ directory persistence (HF Spaces):**
On HF Spaces, `/data/.hermes/scripts/` content is wiped on container rebuild while `skills/` persists.
All `no_agent=True` cron jobs break after rebuild because their script targets vanish.

**v4 雙層自癒架構（2026-06-07 修正，取代 v3）**：

v3 缺陷：獨立的 agent cron `restore-scripts-after-rebuild` 本身也需要 scripts/ 中的 wrapper 才能觸發 → 重建後 scripts/ 為空 → 死鎖無法自舉。

v4 設計：每個 no_agent cron wrapper 自含自癒邏輯：
- Layer 1: `scripts/` 中的 wrapper 副本（暫存層，HF 重建後丟失）
- Layer 2: `skills/` 中的實際腳本（持久層，GitHub 備份可還原）
- 自癒流程：wrapper 執行前檢查 skills/ → 不存在則 clone GitHub repo 還原 → 重建所有 scripts/ wrapper → 執行實際腳本
- 任一 cron 先觸發即連帶修復全部（ALL_CRON_SCRIPTS 列表）
- 消除 v3 的 0~10 分鐘空窗期

**Cron Scripts 對照表（v5）**：

| Cron Job | Job ID | scripts/ wrapper | skills/ 實際腳本 |
|----------|--------|-----------------|-----------------|
| Sync Sessions | 33001a64cdf4 | cron-sync-sessions.py | devops/hermes-cli-to-webui-sync/scripts/cron-sync-sessions.py |
| Skills Backup | ef7cc211bb56 | cron-skills-backup.sh | devops/github-skills-backup/scripts/cron-skills-backup.sh |
| Session Backup | 6527076f63be | backup-sessions.py | devops/robust-db-persistence/scripts/cron-backup-sessions.py |
| Restore from HF | 50a3a8b1dea5 | restore-from-hf.py | devops/robust-db-persistence/scripts/cron-restore-from-hf.py |
| Kaggle GPU Quota | b95c725a43ee | kaggle-gpu-quota-monitor.py | research/twstock-alpha-gpt/scripts/kaggle-gpu-quota-monitor.py |
| (shared dep) | — | github-skills-backup.sh | devops/github-skills-backup/scripts/github-skills-backup.sh |
| (shared dep) | — | sync-sessions-to-webui.py | devops/hermes-cli-to-webui-sync/scripts/sync-sessions-to-webui.py |

**新增 no_agent cron job 時必須**：更新所有 wrapper 的 ALL_CRON_SCRIPTS 列表 + 執行 GitHub backup 推送

**Details:** `references/hermes-cli-to-webui-sync.md`, `references/hermes-cli-to-webui-sync_schema-diff.md`
**Scripts:** `scripts/hermes-cli-to-webui-sync_sync-sessions-to-webui.py`, `scripts/hermes-cli-to-webui-sync_verify-sync.py`
**Self-healing detail:** See `hermes-cli-to-webui-sync` skill → `references/hf-spaces-scripts-persistence.md`
**Rebuild checklist:** See `hermes-cli-to-webui-sync` skill → "系統重建清單" section

## E. User ID System (from `user-id-system`)

**When to use:** Implementing multi-device user identification, solving session isolation across devices.

**Key gap:** Hermes Agent has no user identity mechanism — sessions from different devices are completely isolated.

**Details:** `references/user-id-system.md`, `references/user-id-system_web-ui-profile-vs-userid.md`

## F. Unified Session ID (from `unified-session-id`)

**When to use:** Eliminating inconsistent temporary session IDs (eph_* prefix) for stable cross-platform identification.

**Key problem:** Three different Session ID formats exist, causing session management chaos.

**Details:** `references/unified-session-id.md`
**Scripts:** `scripts/unified-session-id_migrate_legacy_sessions.py`

## G. Session Merge (from `session-merge`)

**When to use:** Consolidating scattered sessions from the same user across multiple devices.

**Key problem:** Same user's sessions on different devices are completely independent with no linking mechanism.

**Details:** `references/session-merge.md`
**Scripts:** `scripts/session-merge_session_merge.py`

## H. HuggingFace Sync (from `huggingface-sync`)

**When to use:** Syncing Hermes Agent data to HuggingFace Datasets for remote backup, incremental sync with verification.

**Details:** `references/huggingface-sync.md`, `references/huggingface-sync_hf-token-permissions.md`, `references/huggingface-sync_sync-troubleshooting.md`
**Scripts:** `scripts/huggingface-sync_verify-sync.sh`, `scripts/huggingface-sync_hf_search_sessions.py`

**HF session search:** When user needs to find sessions by keyword in the HF backup, use `scripts/huggingface-sync_hf_search_sessions.py`. Run: `python3 scripts/huggingface-sync_hf_search_sessions.py "keyword1,keyword2" [--limit N] [--include-cron]`. Requires AUTH_TOKEN and HF_DATASET_REPO env vars. Key pitfall: HF file names use `session_` prefix — always get exact names from `list_repo_files()` before downloading, bare IDs will 404.

## I. GitHub Skills Backup & Cron Self-Healing (from `github-skills-backup`)

**When to use:** Backing up all Hermes skills to GitHub, restoring skills after environment reset, managing cron self-healing after HF Space rebuilds.

**Key commands:**
```bash
# Backup all skills
bash /data/.hermes/skills/devops/github-skills-backup/scripts/github-skills-backup.sh

# List remote skills
bash /data/.hermes/skills/devops/github-skills-backup/scripts/github-skills-backup.sh --list

# Restore a single skill
bash /data/.hermes/skills/devops/github-skills-backup/scripts/github-skills-backup.sh --restore research/patent-research-workflow

# Bulk restore (public repo)
git clone https://github.com/milo0914/hermes-skills-backup.git /tmp/hermes-skills-backup
cp -r /tmp/hermes-skills-backup/* /data/.hermes/skills/
```

**Critical pitfall — GITHUB_TOKEN in HF Spaces:**
GITHUB_TOKEN is a Space Secret variable, NOT in shell env. `echo $GITHUB_TOKEN` returns empty but the token exists in `/proc/1/environ`. Scripts auto-detect it. `cat /proc/1/environ 2>/dev/null | tr '\0' '\n' | grep '^GITHUB_TOKEN=' | cut -d= -f2-` retrieves it. Never say "GITHUB_TOKEN not set" in HF Spaces.

**Cron self-healing (v5):**
- Dual-layer: `scripts/` = wrapper copies (ephemeral on HF rebuild), `skills/` = actual scripts (persistent, GitHub-backed)
- Each wrapper checks if target exists in `skills/` → if not, clones GitHub repo to restore → rebuilds all wrappers → runs actual script
- First cron to trigger after rebuild heals ALL other crons (ALL_CRON_SCRIPTS list)
- v5 fix: skill-level granularity (check each sub-skill, not just category dir)
- Symlinks forbidden (cron system rejects path traversal)
- Script location: `/data/.hermes/skills/devops/github-skills-backup/scripts/github-skills-backup.sh`

**Details:** `references/github-skills-backup.md`
**Scripts:** `scripts/github-skills-backup_cron-skills-backup.sh`, `scripts/github-skills-backup_github-skills-backup.sh`

---

## Verification Steps (Consolidated)

After implementing backup or troubleshooting:

1. **Check JSON files exist:**
   ```bash
   ls -lh /data/.hermes/sessions/
   ```

2. **Verify backup state:**
   ```bash
   cat /data/.hermes/backup_state.json
   ```

3. **Test manual backup:**
   ```bash
   python3 /data/.hermes/bin/backup_sessions.py
   ```

4. **Check cron status:**
   ```bash
   hermes cron list
   ```

5. **Verify session count:**
   ```bash
   ls /data/.hermes/sessions/*.json | wc -l
   ```

6. **System health quick-check:**
   ```bash
   # Config exists
   test -f /data/.hermes/config.yaml && echo "✓ config.yaml"
   
   # DB queryable
   python3 -c "import sqlite3; conn = sqlite3.connect('/data/.hermes/state.db'); print('✓ state.db:', conn.execute('SELECT COUNT(*) FROM sessions').fetchone()[0], 'sessions')"
   
   # Gateway running
   test -f /data/.hermes/gateway_state.json && echo "✓ gateway state"
   
   # Memory exists
   test -f /data/.hermes/memories/MEMORY.md && echo "✓ MEMORY.md"
   ```
