# Web UI Profile vs User ID — Code Evidence

## Investigation Date: 2026-05-28

## Key Finding

The Open WebUI frontend's "使用者" (User) dropdown is **NOT** a user identity selector. It is a **Hermes Profile** (設定檔) switcher for configuration isolation (different models, gateways, API keys).

## Architecture Map

```
Frontend (ProfileSelector.vue)
  ↓ sidebar.profiles i18n key
  ↓ s.switchProfile(name)  — switches Hermes config profile
  ↓
BFF Server (hermes-web-ui)
  ↓ sessions table: profile TEXT DEFAULT 'default'
  ↓ sessions table: user_id TEXT DEFAULT NULL  ← ALWAYS NULL
  ↓ WebSocket: G.handshake.query?.profile || "default"
  ↓
API Server (gateway/platforms/api_server.py)
  ↓ _route_chat_completions() reads X-Hermes-Session-Id
  ↓ DOES NOT read X-Hermes-User-Id (header not implemented)
  ↓ DOES NOT read OpenAI spec "user" field from request body
  ↓ _create_agent() — no user_id parameter passed to AIAgent
  ↓
AIAgent (run_agent.py)
  ↓ _ensure_db_session() — always passes user_id=None
  ↓
State DB (hermes_state.py)
  ↓ sessions.user_id — ALL 206 rows are NULL
```

## BFF Session Creation — Exact Code Path

The BFF's `Ad()` (createSession) function INSERT statement:
```sql
INSERT INTO sessions (id, profile, source, model, title, started_at, last_active, workspace)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
```

**No `user_id` column in the INSERT at all.** The fallback path also hardcodes `user_id: null`.

## BFF Proxy Headers — What Gets Forwarded

The BFF's `uYI()` header builder adds:
- `X-Hermes-Session-Key` — from session ID
- Does NOT add `X-Hermes-User-Id`

## API Server — User Field Ignored

In `_route_chat_completions()` (api_server.py ~L2675-2720):
- Reads `X-Hermes-Session-Id` header (requires API_SERVER_KEY)
- Does NOT read `X-Hermes-User-Id` header
- Does NOT read `user` field from OpenAI chat completion request body
- `_create_agent()` call has no user_id parameter

## Profile vs User ID Comparison

| Aspect | Profile (設定檔) | user_id |
|--------|------------------|---------|
| UI Label | sidebar.profiles → "設定檔" | N/A (no UI) |
| DB Column | sessions.profile (TEXT, DEFAULT 'default') | sessions.user_id (TEXT, DEFAULT NULL) |
| Values | "default", custom names | ALL NULL |
| Purpose | Configuration isolation (model, gateway, API key) | User identity (never used) |
| Passed to API Server | Via WebSocket query param | Never passed |
| BFF INSERT | Included | Excluded |

## GroupChat Exception

The BFF's GroupChat feature (`gc_room_members` table) has real `userId` and `userName` fields, but this is isolated to the multi-user chat room feature and does not flow into the regular chat session system.

## Where Real User Identity Could Come From

1. **X-Hermes-User-Id header** — Not yet implemented in API Server
2. **OpenAI spec `user` field** — Present in request body but not parsed by api_server.py
3. **BFF password login** — Has username/password auth but does NOT set user_id in sessions
4. **HF Spaces X-Gradio-User** — Available in HF Spaces environment but not wired through

## Data Count Inconsistency

As of 2026-05-28:
- JSON files in /data/.hermes/sessions/: **497**
- backup_state.json tracked sessions: **198**
- SQLite state.db sessions: **206**
- user_id values across all stores: **ALL NULL / NOT_SET**
