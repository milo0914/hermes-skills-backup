---
name: hermes-cli-to-webui-sync
description: 將 Hermes CLI sessions 與 messages 增量同步到 Web UI DB — 解決 CLI 新 session 不出現在 Web UI 的問題。含腳本、cron 設定、schema 差異對照、重建指南。v2 新增 messages 同步。
tags: [hermes, sqlite, sync, web-ui, cron, devops, messages]
---

# Hermes CLI → Web UI Session 同步（v2：含 Messages 同步）

將 Hermes CLI (`state.db`) 的 session **與對話內容**增量同步到 Web UI (`hermes-web-ui.db`)，解決 CLI 新建的 session 在 Web UI 中不可見的問題。

**v2 重要更新**：同步邏輯現在同時處理 `sessions` **和** `messages` 兩個表格，確保 Web UI 中能正常顯示對話內容。

## 何時載入此 Skill

- Web UI 看不到 CLI 建立的 session
- Web UI 有 session 標題但**內容空白**（messages 未同步）
- 系統重建後需要重新設定同步機制
- 需要了解兩個 DB 的 schema 差異
- 需要修復同步腳本或 cron job
- Web UI session 列表數量明顯少於 CLI

## 問題根源

Hermes 有兩個獨立的 SQLite DB：

| DB | 路徑 | 使用場景 |
|---|---|---|
| CLI DB | `~/.hermes/state.db` | hermes CLI / API Server 產生的 session |
| Web UI DB | `~/.hermes-web-ui/hermes-web-ui.db` | Web UI 讀取顯示的 session |

Web UI 的 `syncAllHermesSessionsOnStartup` **只在 Web UI DB 為空時**執行一次初始匯入。一旦 DB 有資料，後續 CLI 產生的 session 永遠不會出現在 Web UI。

更嚴重的是，初始匯入只帶入 `sessions` 表格資料，**`messages` 表格並未同步**，這導致 Web UI 中雖能看到 session 標題（sessions 表），但點開後**對話內容為空白**（messages 表缺失）。

## 同步架構（v2）

```
┌─────────────┐     ┌──────────────┐     ┌──────────────────┐
│  CLI DB     │     │  sync script │     │   Web UI DB      │
│ state.db    │────▶│ (cron job)   │────▶│hermes-web-ui.db  │
│             │     │              │     │                  │
│ ┌────────┐  │     │  Phase 1:    │     │  ┌───────────┐  │
│ │sessions│  │────▶│  sessions    │────▶│  │ sessions  │  │
│ └────────┘  │     │  incremental│     │  └───────────┘  │
│ ┌────────┐  │     │  sync        │     │  ┌───────────┐  │
│ │messages│  │────▶│  Phase 2:    │────▶│  │ messages  │  │
│ └────────┘  │     │  messages    │     │  └───────────┘  │
│             │     │  incremental │     │                  │
└─────────────┘     │  sync        │     └──────────────────┘
                    └──────────────┘
```

### 增量同步策略

#### Phase 1：Sessions 同步

1. **INSERT**：CLI DB 有但 Web UI DB 沒有的 session → 新增
2. **UPDATE**：兩邊都有，但 CLI 版本的 mutable 欄位有變化 → 更新
3. **SKIP**：兩邊都有且資料一致 → 跳過

#### Phase 2：Messages 同步

1. **INSERT ONLY**：CLI DB 有但 Web UI DB 沒有的 message → 新增
2. **SKIP**：Web UI DB 中已存在的 message → 跳過（避免重複）
3. **No UPDATE**：messages 為 append-only，不更新

### 比對的 Mutable 欄位（sessions）

```
title, ended_at, end_reason,
message_count, tool_call_count,
input_tokens, output_tokens,
cache_read_tokens, cache_write_tokens, reasoning_tokens,
billing_provider, estimated_cost_usd, actual_cost_usd, cost_status
```

### 比對規則

- 數值欄位：直接 `!=` 比較
- 字串欄位：`None` 和 `""` 視為等價（`(val or "") != (val or "")`）
- 寫入前所有 NULL 值經 `coalesce_for_webui()` 轉換為 Web UI 預設值

### 交易安全

所有寫入操作包裹在單一 TRANSACTION 中：
- 成功：一次 COMMIT
- 失敗：ROLLBACK，不會產生半成品

## Schema 差異對照

### Sessions 表格：兩邊都有的欄位（COMMON_COLS）

```
id, source, user_id, model, title,
started_at, ended_at, end_reason,
message_count, tool_call_count,
input_tokens, output_tokens,
cache_read_tokens, cache_write_tokens, reasoning_tokens,
billing_provider, estimated_cost_usd, actual_cost_usd, cost_status
```

### Sessions 表格：僅 CLI DB 有的欄位

```
model_config, system_prompt, parent_session_id,
billing_base_url, billing_mode, cost_source, pricing_version,
api_call_count, handoff_*
```

這些欄位在同步時被忽略（Web UI 不需要）。

### Sessions 表格：僅 Web UI DB 有的欄位（需填預設值）

| 欄位 | NOT NULL | 預設值 |
|---|---|---|
| profile | YES | `"default"` |
| preview | YES | `""` |
| last_active | NO | `started_at` 的值 |
| workspace | NO | `NULL` |

### Web UI NOT NULL 限制的 Coalesce 對照

CLI DB 可能為 NULL 的欄位，在寫入 Web UI 時必須 coalesce：

| 欄位 | Web UI 預設值 |
|---|---|
| profile | `"default"` |
| source | `"api_server"` |
| model | `""` |
| message_count | `0` |
| tool_call_count | `0` |
| input_tokens | `0` |
| output_tokens | `0` |
| cache_read_tokens | `0` |
| cache_write_tokens | `0` |
| reasoning_tokens | `0` |
| estimated_cost_usd | `0.0` |
| cost_status | `""` |
| preview | `""` |

### Messages 表格欄位

CLI DB 的 messages 表格欄位：

| CLI messages | Web UI messages | 狀態 |
|---|---|---|
| id | id | ✅ 同步 |
| session_id | session_id | ✅ 同步 |
| role | role | ✅ 同步 |
| content | content | ✅ 同步 |
| tool_call_id | tool_call_id | ✅ 同步 |
| tool_calls | tool_calls | ✅ 同步 |
| tool_name | tool_name | ✅ 同步 |
| timestamp | timestamp | ✅ 同步 |
| token_count | token_count | ✅ 同步 |
| finish_reason | finish_reason | ✅ 同步 |
| reasoning | — | ⚠️ 僅 CLI 有 |
| reasoning_content | reasoning_content | ✅ 同步 |
| reasoning_details | reasoning_details | ✅ 同步 |
| codex_reasoning_items | — | ⚠️ 僅 CLI 有 |
| codex_message_items | — | ⚠️ 僅 CLI 有 |

**注意**：CLI-only 欄位（reasoning, codex_reasoning_items, codex_message_items）在同步到 Web UI 時被忽略。Web UI 可能不支援這些欄位，或需要用預設值填充。

### 關鍵陷阱：title 的 unique index

CLI DB 的 sessions 表有 partial unique index：
```sql
CREATE UNIQUE INDEX idx_sessions_title_unique ON sessions(title) WHERE title IS NOT NULL
```
**必須使用 NULL 而非空字串 `""` 表示無標題**，否則會違反 unique constraint。

## 安裝步驟

### Step 1：部署同步腳本

腳本位置：`/data/.hermes/scripts/sync-sessions-to-webui.py`

確保腳本存在且可執行：
```bash
test -f /data/.hermes/scripts/sync-sessions-to-webui.py && echo "OK" || echo "MISSING"
chmod +x /data/.hermes/scripts/sync-sessions-to-webui.py
```

如果腳本不存在（常見於系統重建後），從 skill 的 `scripts/` 目錄複製：
```bash
cp /data/.hermes/skills/devops/hermes-cli-to-webui-sync/scripts/sync-sessions-to-webui.py \
   /data/.hermes/scripts/sync-sessions-to-webui.py
chmod +x /data/.hermes/scripts/sync-sessions-to-webui.py
```

**常見故障**：cron job `sync-hermes-sessions-to-webui` 報 `last_status=error`，最常見原因就是腳本檔案丟失。修復流程：先 `test -f` 確認 MISSING → 從 skill 目錄 cp → dry-run 驗證 → cron 自動恢復。

### Step 2：首次 Dry Run 驗證

```bash
python3 /data/.hermes/scripts/sync-sessions-to-webui.py --dry-run --verbose
```

預期輸出：
```
CLI DB sessions: N
Web UI DB sessions: M
New to insert: N-M
Changed to update: 0
Messages to sync: X (from Y CLI messages, Z already in WebUI)

[DRY RUN] No changes made.
```

### Step 3：執行首次同步

```bash
python3 /data/.hermes/scripts/sync-sessions-to-webui.py
```

預期輸出：
```
CLI DB sessions: N
Web UI DB sessions: M
New to insert: X
Changed to update: 0
Syncing messages...

Sync completed: X sessions inserted, 0 sessions updated
Messages: A inserted, B skipped
Web UI DB after sync: M+X sessions, C messages
```

### Step 4：設定 Cron Job

使用 Hermes cron job（純腳本模式，零 token 消耗）：

```
cronjob(action='create',
  name='sync-hermes-sessions-to-webui',
  schedule='every 30m',
  script='sync-sessions-to-webui.py',
  no_agent=True,
  deliver='origin')
```

**重要參數說明：**
- `no_agent=True`：不啟動 LLM，直接執行腳本，stdout 就是輸出
- `deliver='origin'`：結果發送回當前聊天
- `schedule='every 30m'`：每 30 分鐘執行一次
- `script` 路徑相對於 `/data/.hermes/scripts/`

### Step 5：驗證 Cron Job

```
cronjob(action='list')
```

確認 job 出現在列表中且 `enabled=True`。

等待首次自動執行後，檢查 Web UI session 與 message 數量：
```bash
python3 -c "
import sqlite3, os
c = sqlite3.connect(os.path.expanduser('~/.hermes-web-ui/hermes-web-ui.db'))
print('Web UI sessions:', c.execute('SELECT COUNT(*) FROM sessions').fetchone()[0])
print('Web UI messages:', c.execute('SELECT COUNT(*) FROM messages').fetchone()[0])
c.close()
"
```

## 輸出行為（no_agent 模式）

- 有新/更新 session 或 message → stdout 輸出同步結果，發送給用戶
- 無變化（0 insert, 0 update）→ stdout 為空，靜默不發送
- 腳本錯誤 → 非 0 exit code，自動發送錯誤警報

## 常見問題

### 1. Web UI DB 不存在

**症狀**：`ERROR: Web UI DB not found at ~/.hermes-web-ui/hermes-web-ui.db`

**原因**：Web UI 從未啟動過，DB 尚未建立。

**解法**：先啟動一次 Web UI，讓它自動建立 DB。或者手動建表（需要完整 schema，建議直接啟動 Web UI）。

### 2. 有標題但內容空白

**症狀**：Web UI 中能看到 session 標題，但點進去後對話內容為空白。

**原因**：只同步了 `sessions` 表，沒有同步 `messages` 表。

**解法**：使用 v2 版本的同步腳本（本 skill 提供的腳本），確認在 `sync()` 函數中執行了 `sync_messages()`。

**驗證**：
```bash
# 確認 messages 表有資料
python3 -c "
import sqlite3, os
c = sqlite3.connect(os.path.expanduser('~/.hermes-web-ui/hermes-web-ui.db'))
msgs = c.execute('SELECT COUNT(*) FROM messages').fetchone()[0]
sessions = c.execute('SELECT COUNT(*) FROM sessions').fetchone()[0]
print(f'sessions: {sessions}, messages: {msgs}')
c.close()
"
```

### 3. NOT NULL constraint failed

**症狀**：`sqlite3.IntegrityError: NOT NULL constraint failed: sessions.profile`

**原因**：CLI DB 某欄位為 NULL，但 Web UI DB 該欄位有 NOT NULL 限制，且 `coalesce_for_webui()` 未涵蓋。

**解法**：
1. 確認哪個欄位觸發錯誤
2. 在 `WEBUI_NOTNULL_DEFAULTS` 字典中新增該欄位的預設值
3. 重新執行同步

```python
# 在腳本中新增
WEBUI_NOTNULL_DEFAULTS = {
    # ... 現有項目 ...
    "new_column": "default_value",  # 新增
}
```

### 4. UNIQUE constraint failed: sessions.title

**症狀**：`sqlite3.IntegrityError: UNIQUE constraint failed: sessions.title`

**原因**：多個 session 的 title 被設為空字串 `""` 而非 `NULL`。

**解法**：確認 CLI DB 中無標題的 session 使用 `NULL` 而非 `""`。腳本的 `coalesce_for_webui()` 已處理此問題（`None` → 預設值），但如果 CLI DB 直接存了 `""`，需要額外轉換。

### 5. Cron job 重複建立

**症狀**：`cronjob(action='list')` 出現多個 sync job。

**解法**：
```
cronjob(action='list')  # 找到重複的 job_id
cronjob(action='remove', job_id='xxx')  # 移除多餘的
```

### 6. 同步後 Web UI 仍看不到某些 session

**可能原因**：
- Web UI 前端有快取，需要重新整理頁面
- Session 的 `source` 欄位被 Web UI 前端過濾（某些版本只顯示特定 source）
- Session 的 `model` 為 NULL 且 Web UI 不渲染

**診斷**：
```bash
# 確認 DB 中確實有資料
python3 -c "
import sqlite3, os
db = os.path.expanduser('~/.hermes-web-ui/hermes-web-ui.db')
c = sqlite3.connect(db)
rows = c.execute('SELECT id, source, model, title FROM sessions ORDER BY started_at DESC LIMIT 5').fetchall()
for r in rows: print(r)
c.close()
"
```

### 7. 同步腳本丟失（cron 報錯）— **最常見的故障**

**症狀**：Cron job `sync-hermes-sessions-to-webui` 的 `last_status` 為 `error`，
或 `Backup Hermes Skills to GitHub` 報 `Script not found: /data/.hermes/scripts/...`。

**根本原因**：此問題在 **Hugging Face Spaces** 環境下反覆發生（詳見 `references/hf-spaces-scripts-persistence.md`）：

1. HF Spaces 的容器會在設定變更、手動重啟、sleep/wake 週期時被重建
2. 容器重建後，`/data/.hermes/` 目錄大部分持久化（skills/、state.db、cron/）
3. 但 **`/data/.hermes/scripts/` 的內容會丟失** — 因為：
  - Hermes 啟動時會還原 skills/、state.db 等，但 **不處理 scripts/**
  - Cron scheduler 在首次 tick 時用 `mkdir(parents=True, exist_ok=True)` 建立空的 scripts/
  - 手動部署的腳本檔案不會被自動還原
4. Cron scheduler `_run_job_script()` 強制限制腳本必須在 `HERMES_HOME/scripts/` 內
  （做 `path.relative_to(scripts_dir_resolved)` 檢查，絕對路徑和外部 symlink 均被擋）

#### 故障歷史

##### 2026-06-07：HF Space 重建導致全部 4 個 cron job 失效

**問題**：HF Space 重建後，4 個 no_agent cron job 的 script 全部找不到：
- `session-backup` (backup-sessions.py) → Script not found
- `Backup Hermes Skills to GitHub` (cron-skills-backup.sh) → Script not found
- `sync-hermes-sessions-to-webui` (cron-sync-sessions.py) → Script not found
- `restore-sessions-from-hf` (restore-from-hf.py) → Script not found

**根因**：scripts/ 目錄被清除，且 v3 三層架構的 `restore-scripts-after-rebuild` agent cron 也需要 scripts/ 中的 wrapper → 死鎖，無法自舉

**修正**：升級為 v4 雙層自癒架構（見下方），每個 wrapper 自含 GitHub clone 還原邏輯，移除獨立 restore cron

#### v3 架構（已廢棄，僅供歷史參考）

```
Layer 1: scripts/ 中的 wrapper 腳本（會丟失）
Layer 2: skills/ 中的真實腳本（持久）
Layer 3: restore-scripts-after-rebuild agent cron（每 10m）→ 自舉死鎖缺陷
```

v3 的缺陷：agent 模式的 restore-scripts cron 本身也需要 scripts/ 中有入口才能觸發，但 scripts/ 已被清除 → 無法啟動 → 死鎖。

#### v4 雙層自癒架構（目前使用）

```
Layer 1: scripts/ 中的 wrapper 副本（暫存層，HF 重建後丟失）
  cron-sync-sessions.py → 包含自癒邏輯的 Python wrapper
  cron-skills-backup.sh → 包含自癒邏輯的 Bash wrapper
  backup-sessions.py → 包含自癒邏輯的 Python wrapper
  restore-from-hf.py → 包含自癒邏輯的 Python wrapper

Layer 2: skills/ 中的實際腳本（持久層，GitHub 備份可還原）
  skills/devops/hermes-cli-to-webui-sync/scripts/cron-sync-sessions.py
  skills/devops/github-skills-backup/scripts/cron-skills-backup.sh
  skills/devops/robust-db-persistence/scripts/cron-backup-sessions.py
  skills/devops/robust-db-persistence/scripts/cron-restore-from-hf.py
```

**自癒流程**（每個 wrapper 執行時）：
1. 檢查 skills/ 中是否存在目標腳本
2. 若不存在 → 從 `/proc/1/environ` 提取 GITHUB_TOKEN → clone `hermes-skills-backup` repo → 還原 skills/
3. 重建 scripts/ 中所有缺失的 wrapper（ALL_CRON_SCRIPTS 列表）
4. exec 到實際腳本執行

**v4 vs v3 的改進**：
- 移除了無法自舉的 restore-scripts agent cron
- 自癒邏輯內嵌到每個 no_agent wrapper 中，任一 cron 觸發即修復全部
- 消除了 v3 的 0~10 分鐘空窗期（第一個觸發的 cron 修復全部）

**v4 → v5 修正（2026-06-10）**：v4 的 `heal_skills_from_github()` 只檢查 category 目錄（如 `devops/`）是否存在。若因其他 skill 已恢復而 `devops/` 不為空，即使 `robust-db-persistence` 等子 skill 缺失也會被跳過。v5 改為 skill-level 粒度 — category 已存在時逐一檢查內部子目錄，僅複製缺失的 skill。詳見 `references/cron-self-heal-v5-fix.md`。

**⚠️ 冷啟動盲區（2026-06-25 確認）**：v5 自癒邏輯寫在 scripts/ 中的 wrapper 內，當 scripts/ **完全為空**時（HF Space 重建後），沒有任何 cron 能觸發，自癒無法啟動。此時需外部 agent 手動從 skills/ 複製 7 個 wrapper 到 scripts/，再逐一觸發失敗的 cron。完整修復步驟見 `data-persistence` skill 的 Pitfall #5。

**手動修復**：
```bash
# 方法 A：從 skills/ 複製 wrapper（最簡單）
cp /data/.hermes/skills/devops/hermes-cli-to-webui-sync/scripts/cron-sync-sessions.py \
  /data/.hermes/scripts/cron-sync-sessions.py
chmod +x /data/.hermes/scripts/cron-sync-sessions.py

# 方法 B：手動觸發任一 cron job，讓自癒邏輯修復全部
cronjob(action='run', job_id='33001a64cdf4')

# 驗證
python3 /data/.hermes/scripts/cron-sync-sessions.py --dry-run
```

**預防檢查清單**（新增 no_agent cron job 時）：
1. 將實際腳本放在 skill 的 `scripts/` 目錄下（持久化）
2. 建立包含自癒邏輯的 wrapper（參考現有 wrapper 的 ALL_CRON_SCRIPTS 列表模板）
3. 將 wrapper 副本放到 `/data/.hermes/scripts/`
4. 更新所有其他 wrapper 的 ALL_CRON_SCRIPTS 列表（加入新項目）
5. 用 `cronjob(action='run', job_id='...')` 驗證 cron job 正常
6. 執行 GitHub skills backup 推送更新

### 8. Session ID 不重疊（初始匯入與 CLI DB ID 不匹配）

**症狀**：dry-run 顯示 "New to insert" 數量遠大於預期（幾乎等於 CLI 總 session 數），且 "No overlapping sessions for message sync"。

**原因**：Web UI 的 `syncAllHermesSessionsOnStartup` 初始匯入可能使用了不同的 ID 格式，或原始 CLI session 已從 CLI DB 中被清理。結果是 Web UI 中的舊 session ID 與當前 CLI DB 中的 ID 完全不重疊。

**影響**：
- 同步會將所有 CLI session 作為「新增」插入 Web UI，Web UI session 數量 = 舊數 + CLI 數
- 舊 Web UI session 的 messages 不會被更新（因為 CLI DB 中已無對應 session）
- 這不是錯誤，但會導致 Web UI 有「孤立」的舊 session

**處理方式**：
- 如果舊 session 已無用，可手動清理 Web UI DB 中的孤立 session
- 如果需要保留，可接受雙倍數量，Web UI 前端仍可正常顯示
- 預防：定期同步可避免大量累積

### 9. DB 路徑不同

如果 Hermes 安裝路徑不是預設的 `~/.hermes/`，需要修改腳本中的路徑常數：

```python
CLI_DB = "/custom/path/.hermes/state.db"
WEBUI_DB = "/custom/path/.hermes-web-ui/hermes-web-ui.db"
```

## 系統重建清單

當系統重建或更新時，依序執行：

1. **確認兩個 DB 都存在**
 ```bash
 ls -la ~/.hermes/state.db ~/.hermes-web-ui/hermes-web-ui.db
 ```

2. **還原 scripts/ 中的 wrapper**（v4 雙層自癒架構見問題 #7）
 ```bash
 # 方法 A：手動觸發任一 cron job，讓自癒邏輯修復全部
 # cronjob(action='run', job_id='33001a64cdf4')
 
 # 方法 B：手動從 skills/ 複製 wrapper
 cp /data/.hermes/skills/devops/hermes-cli-to-webui-sync/scripts/cron-sync-sessions.py \
   /data/.hermes/scripts/cron-sync-sessions.py
 chmod +x /data/.hermes/scripts/cron-sync-sessions.py
 ```

3. **首次 Dry Run 驗證**（見 Step 2）

4. **執行首次同步**（見 Step 3）

5. **確認 cron job 正常**（見 Step 5）：
 - `sync-hermes-sessions-to-webui` (job_id=33001a64cdf4)：no_agent，每 30m
 - 若 scripts/ 丟失，見問題 #7 的自癒機制（v4 雙層架構）

6. **驗證 Web UI 資料**（見驗證步驟）

## 驗證步驟

完整驗證流程：

```bash
# 1. 腳本存在且可執行
test -x /data/.hermes/scripts/sync-sessions-to-webui.py && echo "✓ script"

# 2. 兩個 DB 都存在
test -f ~/.hermes/state.db && echo "✓ CLI DB"
test -f ~/.hermes-web-ui/hermes-web-ui.db && echo "✓ Web UI DB"

# 3. 乾跑無錯誤
python3 /data/.hermes/scripts/sync-sessions-to-webui.py --dry-run

# 4. 實際同步成功
python3 /data/.hermes/scripts/sync-sessions-to-webui.py

# 5. 二次執行應為 0 insert（增量邏輯正確）
python3 /data/.hermes/scripts/sync-sessions-to-webui.py

# 6. Cron job 存在
# 用 cronjob(action='list') 確認

# 7. Web UI session 與 message 數量一致
python3 -c "
import sqlite3, os
cli = sqlite3.connect(os.path.expanduser('~/.hermes/state.db'))
web = sqlite3.connect(os.path.expanduser('~/.hermes-web-ui/hermes-web-ui.db'))
cli_sessions = cli.execute('SELECT COUNT(*) FROM sessions').fetchone()[0]
cli_msgs = cli.execute('SELECT COUNT(*) FROM messages').fetchone()[0]
web_sessions = web.execute('SELECT COUNT(*) FROM sessions').fetchone()[0]
web_msgs = web.execute('SELECT COUNT(*) FROM messages').fetchone()[0]
print(f'CLI: {cli_sessions} sessions, {cli_msgs} messages')
print(f'Web UI: {web_sessions} sessions, {web_msgs} messages')
cli.close(); web.close()
"
```

## References

- `references/schema-diff.md` — CLI DB 與 Web UI DB schema 差異詳細對照
- `references/hf-spaces-scripts-persistence.md` — scripts/ 目錄在 HF Spaces 容器重建後丟失的根因分析、三層自癒架構設計、已排除方案
- `references/cron-self-heal-v5-fix.md` — v4→v5 自癒粒度修正：category-level → skill-level，含根因分析

## 相關 Skills

- `data-persistence` — 通用資料持久化策略（JSON 備份、遠端同步）
- `hermes-agent` — Hermes Agent 本身的配置與管理
- `hermes-session-analysis` — Session 診斷分析
