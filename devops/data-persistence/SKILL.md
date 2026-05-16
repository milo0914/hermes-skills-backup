---
name: data-persistence
description: Data persistence strategies for Hermes Agent - session backup, recovery, SQLite-to-JSON export, incremental sync, and frequency-limited remote pushes
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

### 5. Encoding Issues with Special Characters

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

## Related Skills

- `hermes-agent` - Hermes Agent configuration and management
- `cron-management` - Scheduled task management

---

# Appendix: Absorbed Skills

This skill now incorporates content from the following consolidated skills (as of 2026-05-16):

## A. Session Diagnostics (from `hermes-session-analysis`)

**When to use:** Analyzing why sessions appear/disappear, verifying DB integrity, understanding Web UI display flow.

**Key architecture:**
- Dual storage: SQLite (`state.db`) + JSON backups (`sessions/`)
- Web UI flow: `GET /api/sessions` → `SessionDB.list_sessions_rich()` → SQLite with JOIN
- Common issues: JSON not written, DB corruption, ID mismatch, source filtering

**Diagnostic commands:** See `references/session-diagnostics.md`

## B. System Health Checks (from `system-health-check`)

**When to use:** Verifying operational status, pre-troubleshooting checks, periodic maintenance.

**Core checks:**
1. Configuration files (`config.yaml`, `.env`)
2. Database status (tables, counts)
3. Session files (backup existence)
4. Gateway status (process, state file)
5. Memory system (`MEMORY.md`)
6. Cron jobs

**Verification checklist:** See "Verification Steps" section below.

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
