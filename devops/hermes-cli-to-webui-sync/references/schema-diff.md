# Hermes Sessions Schema 差異參考

產生日期：2026-05-28

## CLI DB (state.db) sessions 表完整欄位

```
id              TEXT PRIMARY KEY
source          TEXT NOT NULL
user_id         TEXT
model           TEXT
model_config    TEXT          -- 僅 CLI
system_prompt   TEXT          -- 僅 CLI
parent_session_id TEXT        -- 僅 CLI (FK → sessions.id)
started_at      REAL NOT NULL
ended_at        REAL
end_reason      TEXT
message_count   INTEGER
tool_call_count INTEGER
input_tokens    INTEGER
output_tokens   INTEGER
cache_read_tokens   INTEGER
cache_write_tokens  INTEGER
reasoning_tokens    INTEGER
billing_base_url    TEXT      -- 僅 CLI
billing_mode        TEXT      -- 僅 CLI
billing_provider    TEXT
cost_source         TEXT      -- 僅 CLI
pricing_version     TEXT      -- 僅 CLI
estimated_cost_usd  REAL
actual_cost_usd     REAL
cost_status         TEXT
api_call_count      INTEGER   -- 僅 CLI
handoff_session_id  TEXT      -- 僅 CLI
handoff_tool_name   TEXT      -- 僅 CLI
handoff_tool_input   TEXT     -- 僅 CLI
title               TEXT      -- partial unique index WHERE title IS NOT NULL
```

## Web UI DB (hermes-web-ui.db) sessions 表完整欄位

```
id              TEXT PRIMARY KEY
source          TEXT NOT NULL
user_id         TEXT
model           TEXT NOT NULL  -- 預設 ""
title           TEXT
started_at      REAL NOT NULL
ended_at        REAL
end_reason      TEXT
message_count   INTEGER NOT NULL DEFAULT 0
tool_call_count INTEGER NOT NULL DEFAULT 0
input_tokens    INTEGER NOT NULL DEFAULT 0
output_tokens   INTEGER NOT NULL DEFAULT 0
cache_read_tokens   INTEGER NOT NULL DEFAULT 0
cache_write_tokens  INTEGER NOT NULL DEFAULT 0
reasoning_tokens    INTEGER NOT NULL DEFAULT 0
billing_provider    TEXT
estimated_cost_usd  REAL NOT NULL DEFAULT 0.0
actual_cost_usd     REAL
cost_status         TEXT NOT NULL DEFAULT ""
profile             TEXT NOT NULL DEFAULT "default"  -- 僅 Web UI
preview             TEXT NOT NULL DEFAULT ""          -- 僅 Web UI
last_active         REAL                              -- 僅 Web UI
workspace           TEXT                              -- 僅 Web UI
```

## 同步映射規則

### INSERT（新 session）

CLI 欄位 → 直接對應寫入（經 coalesce NULL → 預設值）
Web UI 專屬欄位 → 填入預設值：
- profile = "default"
- preview = ""
- last_active = started_at 的值
- workspace = NULL

### UPDATE（已存在但有變化）

僅更新 COMMON_COLS 中的 mutable 欄位：
- title, ended_at, end_reason
- message_count, tool_call_count
- input_tokens, output_tokens
- cache_read_tokens, cache_write_tokens, reasoning_tokens
- billing_provider, estimated_cost_usd, actual_cost_usd, cost_status

不更新 Web UI 專屬欄位（profile, preview, last_active, workspace），
避免覆蓋用戶在 Web UI 中的手動設定。

## 注意事項

1. title 的 unique index：CLI DB 使用 `WHERE title IS NOT NULL` 的 partial unique index，
   多個 session 可以有 NULL title，但不能有重複的非 NULL title。
   Web UI DB 沒有此限制（取決於版本）。

2. CLI DB 獨有欄位（model_config, system_prompt, parent_session_id, billing_* 等）
   在同步時被忽略，Web UI 不需要這些資料。

3. 如果未來 Web UI schema 新增 NOT NULL 欄位，需要在
   WEBUI_NOTNULL_DEFAULTS 和 WEBUI_DEFAULTS 中補上預設值。
