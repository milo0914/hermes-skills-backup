# Session Loss Investigation Pattern

## When to Use
When a user reports that specific session content (conversations, agent work, files created) that existed previously can no longer be found — either in the local DB or in HF backup.

## Investigation Steps

### 1. Check Local DB Coverage
```python
import sqlite3
from datetime import datetime, timezone

conn = sqlite3.connect('/data/.hermes/state.db')
cur = conn.cursor()
cur.execute("SELECT started_at FROM sessions ORDER BY started_at")
timestamps = [r[0] for r in cur.fetchall()]

# Check for gaps (entire days with 0 sessions)
dates_seen = set()
for ts in timestamps:
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    dates_seen.add(dt.strftime('%Y-%m-%d'))

# If a date is missing, sessions from that day were lost
```

### 2. Check HF Backup
- Use `hf_search_sessions.py` with `--date-range` to find sessions in the target date range
- Compare HF backup count vs local DB count for the same period
- If HF has sessions that local DB doesn't → DB was reset after HF Space restart
- If both are missing → session was never backed up (created between cron runs, lost before next backup)

### 3. Check Cron Backup Logs
```bash
# Look for cron execution around the suspected loss time
hermes cron list
hermes cron logs <job_id>
```
The cron schedule determines the maximum data-loss window. If cron runs every 6 hours, any session created and lost within 6 hours is permanently gone.

### 4. Cross-Reference with HF Session Filenames
- Date-format filenames (`session_20260606_134631_*.json`) are created by delegate_task sub-agents
- UUID-format filenames (`session_82f18f90-*.json`) are API server sessions
- Cron filenames (`session_cron_*.json` or `cron_*.json`) are automated tasks

### 5. Check for Session Continuation Chains
Sessions that were compacted or continued will have `parent_session_id` references. The session the user remembers might be a child session that references a parent:
```sql
SELECT id, parent_session_id, title FROM sessions WHERE parent_session_id IS NOT NULL
```

## Root Causes Observed

### HF Space Restart (Most Common)
- **Symptom**: Entire day missing from local DB; HF backup has sessions up to last cron run before restart
- **Cause**: Space restart clears the ephemeral filesystem including SQLite DB
- **Recovery**: Restore from HF backup (download sessions JSON, re-import to DB)

### Cron Backup Gap
- **Symptom**: Specific session missing from both local DB and HF backup; nearby sessions exist
- **Cause**: Session created after last cron run, lost before next cron run
- **Recovery**: Not recoverable — session content is permanently lost

### JSON→DB Sync Failure
- **Symptom**: Session exists in HF backup but not in local DB
- **Cause**: `sync_json_to_db()` may have skipped the file due to schema mismatch or encoding error
- **Recovery**: Manually re-import the JSON file

## Key Finding (2026-06-07)

Investigation of missing "strategy review" + "eng review" + kaggle notebook push session from 2026-06-06 afternoon (13:00-17:00 UTC+8):

- Local DB: **0 sessions** on 2026-06-06 UTC → confirms complete DB loss from Space restart
- HF backup: 5 sessions matching "台股" keyword, but all stop at "twstock-alpha-gpt skill creation" stage
- The session containing strategy review / eng review / phase 1-4 corrections / kaggle notebook push was **never backed up** — it was created between cron runs and lost in the restart
- **Lesson**: For important work, manually trigger backup immediately after completion
