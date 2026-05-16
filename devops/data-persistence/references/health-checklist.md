# System Health Checklist

*Absorbed from `system-health-check` skill on 2026-05-16*

## When to Use

- User asks to check system configuration, status, or health
- User questions whether data/settings are persisted correctly
- User reports missing conversations, settings, or state after restart
- Need to verify Hermes Agent's operational status before troubleshooting
- Periodic maintenance or audit of the agent's infrastructure

## Core Concepts

Hermes Agent persists data across multiple layers:

1. **SQLite Database** (`state.db`): Primary storage for sessions and messages
2. **Session JSON Files** (`sessions/`): Backup copies of each conversation
3. **Memory System** (`memories/MEMORY.md`): Cross-session user preferences and facts
4. **Configuration Files** (`config.yaml`, `.env`): Settings and API credentials
5. **Skills Directory** (`skills/`): Custom skills and workflows

## Health Check Steps

### 1. Check Configuration Files

```bash
# Verify config.yaml exists and is valid
cat /data/.hermes/config.yaml

# Check .env file for required API keys
cat /data/.hermes/.env

# Verify key settings are enabled
grep -E "memory_enabled|user_profile_enabled|compression" /data/.hermes/config.yaml
```

### 2. Check Database Status

```bash
# List database tables
python3 -c "import sqlite3; conn = sqlite3.connect('/data/.hermes/state.db'); print([row[0] for row in conn.cursor().execute(\"SELECT name FROM sqlite_master WHERE type='table'\")])"

# Count sessions and messages
python3 -c "import sqlite3; conn = sqlite3.connect('/data/.hermes/state.db'); print('Sessions:', conn.cursor().execute('SELECT COUNT(*) FROM sessions').fetchone()[0]); print('Messages:', conn.cursor().execute('SELECT COUNT(*) FROM messages').fetchone()[0])"
```

### 3. Check Session Files

```bash
# Count session backup files
ls -la /data/.hermes/sessions/ | wc -l

# Check most recent session files
ls -lt /data/.hermes/sessions/ | head -10
```

### 4. Check Gateway Status

```bash
# Read gateway state
cat /data/.hermes/gateway_state.json

# Check if gateway is running
ps aux | grep hermes-gateway
```

### 5. Check Memory System

```bash
# Verify MEMORY.md exists
cat /data/.hermes/memories/MEMORY.md

# Check memory configuration
grep -A2 "^memory:" /data/.hermes/config.yaml
```

### 6. Check Cron Jobs

```bash
# List scheduled cron jobs
hermes cron list

# Check cron service status
ls -la /data/.hermes/cron/
```

## Verification Checklist

After running checks, confirm:

- [ ] `config.yaml` exists with correct model/provider settings
- [ ] `.env` contains required API keys (NVIDIA, Gemini, etc.)
- [ ] `state.db` is queryable and contains sessions/messages tables
- [ ] Session JSON files exist in `sessions/` directory
- [ ] `MEMORY.md` exists in `memories/` directory
- [ ] Gateway process is running (check `gateway_state.json`)
- [ ] Memory and compression features are enabled in config

## Common Pitfalls

- **Telegram connection timeouts**: Gateway may show "retrying" state for Telegram - this is normal if proxy or bot token has issues, but doesn't affect core functionality
- **Database locking**: If database queries fail, check for lock files (`.db-lock`) or running processes
- **Session file accumulation**: Over time, `sessions/` directory accumulates many files - this is expected behavior, not a bug
- **Memory vs Session data**: `MEMORY.md` contains cross-session facts; `sessions/` contains conversation history - they serve different purposes
- **Cron jobs may be empty**: Having no scheduled cron jobs is normal; cron service runs internal ticks every 60 seconds

## Quick Health Check Script

```bash
#!/bin/bash
# Quick system health check

echo "=== Hermes Agent Health Check ==="

# Config exists
if [ -f /data/.hermes/config.yaml ]; then
 echo "✓ config.yaml exists"
else
 echo "✗ config.yaml MISSING"
fi

# Database queryable
session_count=$(python3 -c "import sqlite3; conn = sqlite3.connect('/data/.hermes/state.db'); print(conn.execute('SELECT COUNT(*) FROM sessions').fetchone()[0])" 2>/dev/null)
if [ -n "$session_count" ]; then
 echo "✓ state.db: $session_count sessions"
else
 echo "✗ state.db NOT ACCESSIBLE"
fi

# Session files exist
session_files=$(ls -1 /data/.hermes/sessions/*.json 2>/dev/null | wc -l)
echo "✓ Session JSON files: $session_files"

# Gateway state
if [ -f /data/.hermes/gateway_state.json ]; then
 echo "✓ gateway_state.json exists"
else
 echo "✗ gateway_state.json MISSING"
fi

# Memory file
if [ -f /data/.hermes/memories/MEMORY.md ]; then
 echo "✓ MEMORY.md exists"
else
 echo "✗ MEMORY.md MISSING"
fi

echo "=== Health Check Complete ==="
```

## Reference Paths

- Configuration location: `/data/.hermes/config.yaml`
- Database location: `/data/.hermes/state.db`
- Session files: `/data/.hermes/sessions/`
- Memory file: `/data/.hermes/memories/MEMORY.md`
- Gateway state: `/data/.hermes/gateway_state.json`
