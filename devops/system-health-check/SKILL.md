---
name: system-health-check
description: Check Hermes Agent system health, configuration, and data persistence status
category: devops
triggers:
  - "check system configuration"
  - "verify data persistence"
  - "is my data saved"
  - "system health"
  - "check if settings are persisted"
  - "conversation history missing"
  - "verify database status"
---

# System Health Check Skill

## Trigger Conditions
Use this skill when:
- User asks to check system configuration, status, or health
- User questions whether data/settings are persisted correctly
- User reports missing conversations, settings, or state after restart
- Need to verify Hermes Agent's operational status before troubleshooting other issues
- Periodic maintenance or audit of the agent's infrastructure

## Core Concepts

Hermes Agent persists data across multiple layers:
1. **SQLite Database** (`state.db`): Primary storage for sessions and messages
2. **Session JSON Files** (`sessions/`): Backup copies of each conversation
3. **Memory System** (`memories/MEMORY.md`): Cross-session user preferences and facts
4. **Configuration Files** (`config.yaml`, `.env`): Settings and API credentials
5. **Skills Directory** (`skills/`): Custom skills and workflows

## Steps

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

## Verification Steps

After running checks, confirm:
- [ ] `config.yaml` exists with correct model/provider settings
- [ ] `.env` contains required API keys (NVIDIA, Gemini, etc.)
- [ ] `state.db` is queryable and contains sessions/messages tables
- [ ] Session JSON files exist in `sessions/` directory
- [ ] `MEMORY.md` exists in `memories/` directory
- [ ] Gateway process is running (check `gateway_state.json`)
- [ ] Memory and compression features are enabled in config

## Pitfalls

- **Telegram connection timeouts**: Gateway may show "retrying" state for Telegram - this is normal if proxy or bot token has issues, but doesn't affect core functionality
- **Database locking**: If database queries fail, check for lock files (`.db-lock`) or running processes
- **Session file accumulation**: Over time, `sessions/` directory accumulates many files - this is expected behavior, not a bug
- **Memory vs Session data**: `MEMORY.md` contains cross-session facts; `sessions/` contains conversation history - they serve different purposes
- **Cron jobs may be empty**: Having no scheduled cron jobs is normal; cron service runs internal ticks every 60 seconds

## References

- Configuration location: `/data/.hermes/config.yaml`
- Database location: `/data/.hermes/state.db`
- Session files: `/data/.hermes/sessions/`
- Memory file: `/data/.hermes/memories/MEMORY.md`
- Gateway state: `/data/.hermes/gateway_state.json`

## Related Skills

- `hermes-agent`: For configuration changes and CLI commands
- `debugging`: For deeper troubleshooting of specific failures
