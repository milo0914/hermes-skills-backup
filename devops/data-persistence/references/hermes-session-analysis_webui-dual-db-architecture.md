# Web UI Dual-DB Architecture (2026-05-28)

## Discovery

The Web UI and Hermes CLI use **completely separate SQLite databases**. This was identified by investigating why the Web UI showed only 1 session while `hermes sessions` showed 317+.

## Database Comparison

| Aspect | Hermes CLI DB | Web UI DB |
|--------|--------------|-----------|
| **Path** | `~/.hermes/state.db` | `~/.hermes-web-ui/hermes-web-ui.db` |
| **Size (2026-05-28)** | 281 MB | 6.7 MB |
| **Sessions** | 321 | 124 |
| **Schema** | 29 columns | 24 columns |
| **Source filter** | Shows all | Sidebar excludes `api_server` |

## Schema Differences

### Columns in Web UI DB only:
- `profile` (TEXT) — Profile name
- `preview` (TEXT) — First user message preview
- `last_active` (REAL) — Last message timestamp
- `workspace` (TEXT) — User workspace assignment

### Columns in CLI DB only:
- `model_config` (TEXT)
- `system_prompt` (TEXT)
- `parent_session_id` (TEXT)
- `billing_provider`, `billing_base_url`, `billing_mode`
- `cache_read_tokens`, `cache_write_tokens`, `reasoning_tokens`
- `api_call_count`
- `handoff_state`, `handoff_platform`, `handoff_error`
- `pricing_version`, `cost_source`

### Shared columns (with possible type differences):
id, source, user_id, model, title, started_at, ended_at, end_reason,
message_count, tool_call_count, input_tokens, output_tokens,
estimated_cost_usd, actual_cost_usd, cost_status

## Sync Mechanism: `syncAllHermesSessionsOnStartup`

Located in the Web UI server bundle (`/opt/hermes-web-ui/dist/server/index.js`), this function is called during bootstrap:

```javascript
// Simplified deobfuscated logic:
async function syncAllHermesSessionsOnStartup() {
  // Check if Web UI DB already has sessions
  let result = db.prepare("SELECT COUNT(*) as count FROM sessions").get();
  if (result && result.count > 0) {
    p.info("Hermes Session DB: skipping initial sync — DB already populated");
    return;
  }
  
  // Only runs when Web UI DB is empty
  // Reads from Hermes CLI's state.db via hermes CLI commands
  // Inserts into Web UI DB
  p.info("Hermes Session DB: initial sync completed");
}
```

**Key behavior**: This is a ONE-TIME sync. Once the Web UI DB has any sessions, it never re-syncs from the CLI DB. This means:
- New sessions created after Web UI first starts are invisible to the Web UI
- Sessions created via API server are auto-added to Web UI DB (they go through the Web UI's session creation path)
- Sessions created via CLI or other sources are NOT added

## Session Listing API Paths

The Web UI server has two API handlers for session listing:

1. **`_C` handler** (GET /api/sessions): Shows sessions from all sources
2. **`qC` handler** (GET /api/sessions/sidebar): **Excludes** `api_server` source sessions

Both first try the Web UI DB (`mZ()` function), then fall back to CLI DB (`zs()`) only on query failure.

## Session Store Mode

Controlled by `SESSION_STORE` environment variable (default: `"local"`):

- `"local"` — Uses Web UI's own `hermes-web-ui.db` (default)
- `"hermes"` — Uses Hermes CLI's `state.db` directly

The `ZG()` function checks this: `process.env.SESSION_STORE || "local"`

## Impact on Data Pipeline

The `robust-db-persistence` backup script (`backup_sessions`) only operates on `~/.hermes/state.db`. It does NOT sync to the Web UI DB. This means the 3-phase pipeline (JSON→DB, DB→JSON, DB→HF) keeps the CLI DB healthy but leaves the Web UI DB stale.

## Proposed Solutions

### Option 1: Add Web UI sync phase to backup_sessions cron
Add Phase D: `state.db` → `hermes-web-ui.db` incremental sync with column mapping.

Column mapping for INSERT:
```
CLI DB column        → Web UI DB column
─────────────────────────────────────────
id                   → id
source               → source
user_id              → user_id
model                → model
title                → title
started_at           → started_at
ended_at             → ended_at
end_reason           → end_reason
message_count        → message_count
tool_call_count      → tool_call_count
input_tokens         → input_tokens
output_tokens        → output_tokens
estimated_cost_usd   → estimated_cost_usd
actual_cost_usd      → actual_cost_usd
cost_status          → cost_status
NULL                 → profile (default: "default")
NULL                 → preview (computed from messages)
started_at           → last_active (fallback)
NULL                 → workspace
```

### Option 2: Set SESSION_STORE=hermes
Change Web UI to read directly from CLI DB. Simpler but loses Web UI-specific features (workspace, local profile management).

### Option 3: Restart Web UI with empty DB
Triggers full re-sync. Quick fix but loses workspace data and is temporary (drift reoccurs).

## How to Investigate Web UI Server Logic

The Web UI server is a compiled Next.js bundle at `/opt/hermes-web-ui/dist/server/index.js`. Key grep patterns:

```bash
# Find session-related functions
grep -n 'syncAllHermesSessions\|sessionMap\|getOrCreateSession\|listSession' /opt/hermes-web-ui/dist/server/index.js

# Find DB path logic
grep -n 'state\.db\|hermes-web-ui\.db\|dataDir\|homedir' /opt/hermes-web-ui/dist/server/index.js

# Find API route handlers
grep -n 'api/sessions\|/api/hermes' /opt/hermes-web-ui/dist/server/index.js

# Find session store mode check
grep -n 'SESSION_STORE\|sessionStore\|ZG()' /opt/hermes-web-ui/dist/server/index.js
```

## Key Deobfuscated Function Names (minified → original)

| Minified | Likely Original | Purpose |
|----------|----------------|---------|
| `sI()` | `getActiveProfileDir()` | Returns active Hermes profile directory |
| `l2()` | `getDbPath()` | Returns `${sI()}/state.db` |
| `mZ()` | `listSessionSummaries()` | Query sessions from Web UI DB |
| `zs()` | `listSessionsFromCLI()` | Fallback: query sessions from CLI DB |
| `ZG()` | `isLocalSessionStore()` | Check if using local or hermes session store |
| `_b()` | `getActiveProfileName()` | Returns active profile name |
| `NC()` | `formatSessionRow()` | Convert DB row to API response format |
| `_C` | `handleListSessions` | API handler for GET /api/sessions |
| `qC` | `handleListSidebarSessions` | API handler for sidebar (excludes api_server) |
