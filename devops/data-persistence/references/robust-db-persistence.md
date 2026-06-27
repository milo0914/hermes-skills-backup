---
name: robust-db-persistence
version: 1.0.0
category: devops
description: 強化 DB 寫入機制 — 確保會話創建時立即寫入 DB，消除 JSON 與 SQLite 不同步問題
tags: [session, database, persistence, sqlite, json-sync, hermes-core, huggingface]
author: hermes-agent
created: 2026-05-28
status: implementation-plan
---

# 強化 DB 寫入機制 — 會話即時持久化方案

## ⚠️ Known Gap: Web UI DB Not Synced

The 3-phase pipeline operates on `~/.hermes/state.db` (Hermes CLI DB) only. The Web UI uses a **separate database** at `~/.hermes-web-ui/hermes-web-ui.db` with a different schema. The Web UI's `syncAllHermesSessionsOnStartup` only runs when the Web UI DB is empty — once populated, new CLI-side sessions never appear in the Web UI.

**Symptom**: `hermes sessions` shows 300+ sessions, Web UI shows ~1 session.
**Root cause**: Two separate SQLite files with no ongoing sync.
**See**: `hermes-session-analysis` skill → `references/webui-dual-db-architecture.md` for full details and proposed solutions.

**Proposed Phase D** (not yet implemented): Incremental sync from `state.db` → `hermes-web-ui.db` with column mapping. This would be added to the backup_sessions cron after Phase C.

## 相關技能
- `huggingface-sync` — HF Dataset 同步（Phase C 的執行者）
- `data-persistence` — 數據持久化總覽

## 參考文件
- `references/pipeline-architecture.md` — 3-phase pipeline 架構詳解、組件清單、數據源不一致分析

## 問題分析

當前系統的 DB 寫入是延遲的（deferred），導致大量會話只存在 JSON 備份中而未寫入 SQLite：

### 數據佐證

| 指標 | 數值 | 說明 |
|------|------|------|
| SQLite DB 會話數 | 185 | 唯一可靠查詢源 |
| JSON 備份會話數 | 471 | 包含所有歷史會話 |
| 僅在 JSON 中 | 85 | 從未寫入 DB 的「孤兒會話」 |
| eph_ 臨時會話 | 37 | 全部未寫入 DB |
| 日期格式會話 | 39 | 全部未寫入 DB |

### 根本原因

1. **延遲寫入設計**（`run_agent.py` L1854）：
   ```python
   self._session_db_created = False  # DB row deferred to run_conversation()
   ```
   DB row 要等到 `_flush_messages_to_session_db()` 才真正寫入，如果在此之前進程崩潰或中斷，會話就只在 JSON 中。

2. **SQLite 鎖衝突**（`run_agent.py` L2442-2447）：
   ```python
   except Exception as e:
       # Transient failure (e.g. SQLite lock). Keep _session_db alive —
       # _session_db_created stays False so next run_conversation() retries.
   ```
   並發寫入時 SQLite 鎖定，寫入失敗後重試但如果 session 在重試前結束，會話就丟失。

3. **JSON 備份獨立運作**：JSON 文件由不同的寫入路徑管理，與 DB 無同步保證。

4. **Web UI 僅查詢 DB**：`list_sessions_rich()` 只查 SQLite，所以 DB 中不存在的會話在 UI 中「消失」。

### 影響的代碼位置

| 文件 | 行號 | 當前行為 | 問題 |
|------|------|----------|------|
| `run_agent.py` | L1854 | `_session_db_created = False` | 延遲寫入 |
| `run_agent.py` | L2427-2447 | `_ensure_db_session()` | 首次 flush 才寫入 |
| `run_agent.py` | L4469-4518 | `_flush_messages_to_session_db()` | 延遲觸發點 |
| `run_agent.py` | L10072-10099 | compression 後重建 session | 重置 `_session_db_created` |
| `hermes_state.py` | L713+ | `create_session()` | 無冪等性保護 |
| `hermes_state.py` | L1160+ | `list_sessions_rich()` | 僅查 DB |
| `gateway/session.py` | L687+ | `_ensure_loaded()` | JSON 與 DB 獨立 |

## 實現方案

### Phase 1：Eager DB Write — 會話創建即寫入

**核心改動：將 `_session_db_created = False` 改為在 `__init__` 中立即寫入**

```python
# run_agent.py — AIAgent.__init__() 修改

# 現有（L1854）：
self._session_db_created = False  # DB row deferred to run_conversation()

# 改為：
self._session_db_created = False
if self._session_db and self.session_id:
    try:
        self._ensure_db_session()
    except Exception as e:
        logger.warning("Eager DB session creation failed (will retry): %s", e)
```

**修改 `_ensure_db_session()` 使其冪等**：

```python
def _ensure_db_session(self) -> None:
    """Create session DB row. Idempotent — safe to call multiple times."""
    if self._session_db_created or not self._session_db:
        return
    try:
        # 檢查是否已存在（冪等性）
        existing = self._session_db.get_session(self.session_id)
        if existing:
            self._session_db_created = True
            return
        
        self._session_db.create_session(
            session_id=self.session_id,
            source=self.platform or os.environ.get("HERMES_SESSION_SOURCE", "cli"),
            model=self.model,
            model_config=self._session_init_model_config,
            system_prompt=self._cached_system_prompt,
            user_id=self._user_id,
            parent_session_id=self._parent_session_id,
        )
        self._session_db_created = True
    except Exception as e:
        logger.warning("Session DB creation failed (will retry next turn): %s", e)
```

**修改 `hermes_state.py` — `create_session()` 加入 UPSERT**：

```python
def create_session(self, session_id, source, model, ...):
    """Create a session record. Uses INSERT OR IGNORE for idempotency."""
    now = time.time()
    try:
        self.conn.execute("""
            INSERT OR IGNORE INTO sessions 
            (id, source, model, model_config, system_prompt, user_id, 
             parent_session_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (session_id, source, model, model_config, system_prompt,
              user_id, parent_session_id, now, now))
        self.conn.commit()
    except sqlite3.IntegrityError:
        # Session already exists — this is fine (idempotent)
        pass
```

### Phase 2：JSON↔DB 雙向同步（合併進 session-backup cron）

**⚠️ 重要：不要用獨立 daemon 跑 JSON→DB 同步再串 HF 上傳！**

sync_daemon.py 本身只寫本地 SQLite（不觸發 HF commit），但如果把高頻 daemon（每 5 分鐘）和 `data_sync.py` 的 HF 上傳串接，每次 daemon cycle 都可能觸發一次全量 `upload_large_folder()` commit → 每天約 288 次 commit，遠超 HF 免費層級建議（每小時 100-200 API 調用、commit 間隔 >1 分鐘）。

**正確架構：合併進現有 session-backup cron（每 6hr）的 3-phase pipeline：**

```
session-backup cron (每 6hr)
  ├─ Phase A: JSON → DB  （sync_daemon 功能：補孤兒會話）
  ├─ Phase B: DB → JSON  （backup_sessions 功能：增量 hash 比對備份）
  └─ Phase C: DB → HF    （可選，僅在 HF_DATASET_REPO + HF_TOKEN 設定時）
```

**優勢：**
- 整個 6hr 週期只產生 1 次 HF commit（而非 daemon 模式的 288 次/天）
- 先補缺漏再備份，保證 JSON 和 DB 雙向一致
- 不需要獨立 daemon 進程（省資源、減少鎖衝突）
- Phase A 和 Phase B 共用同一個 DB connection，避免中途斷開

**現有腳本位置：**
- `scripts/sync_daemon.py` — JSON→DB 同步（保留作為 `--once` 單次執行工具）
- `scripts/sync_json_to_db.py` — 另一個單次同步工具（含 dry-run 和分類統計）
- `/data/.hermes/bin/backup_sessions.py` — 現有 cron 的 DB→JSON 備份腳本
- `/app/src/data_sync.py` — HF 上傳模組（`upload_large_folder()` 全量覆寫）

**建議的改版 backup_sessions.py 流程：**

```python
def main():
    # Phase A: JSON → DB（補孤兒會話）
    orphan_stats = sync_json_to_db()  # 復用 sync_daemon.py 的 sync_pass()

    # Phase B: DB → JSON（增量 hash 備份，現有邏輯）
    backup_stats = backup_db_to_json()

    # Phase C: DB → HF（可選，條件觸發）
    if os.environ.get('HF_DATASET_REPO') and os.environ.get('HF_TOKEN'):
        hf_stats = sync_db_to_hf()
    else:
        hf_stats = {"skipped": True}

    print(f"Phase A (JSON→DB): {orphan_stats}")
    print(f"Phase B (DB→JSON): {backup_stats}")
    print(f"Phase C (DB→HF):   {hf_stats}")
```

**⚠️ Pitfall：import_session 中每個 session 單獨 commit**

sync_daemon.py 的 `import_session()` 對每個 session 執行 `db.commit()`（L93）。當孤兒會話量大（如首次同步 85+ sessions）時，這會產生 85+ 次 SQLite commit。建議改為 batch commit：

```python
# 改進：批量 commit（在 sync_pass 層級控制）
def import_session(db, session_id, filepath, commit=False):
    # ... INSERT OR IGNORE 邏輯不變 ...
    if commit:
        db.commit()
    return True

# sync_pass 中：
for sid in orphan_ids:
    import_session(db, sid, filepath, commit=False)
db.commit()  # 全部導入後一次 commit
```
