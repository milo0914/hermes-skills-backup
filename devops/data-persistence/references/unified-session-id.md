---
name: unified-session-id
version: 1.0.0
category: devops
description: 統一 Session ID 格式 — 消除 eph_ 等不一致的臨時 ID，實現跨裝置、跨平台的穩定會話標識
tags: [session, session-id, eph, uuid, stability, hermes-core]
author: hermes-agent
created: 2026-05-28
status: implementation-plan
---

# 統一 Session ID 格式 — 消除臨時 ID 方案

## 問題分析

當前系統存在三種 Session ID 格式，導致會話管理混亂：

| 格式 | 範例 | 來源 | 數量 | 問題 |
|------|------|------|------|------|
| `eph_` 前綴 | `eph_moo69gww_fpyggj` | 舊版 TUI/CLI | 37 | 無法確定性重建、DB 查不到 |
| 日期格式 | `20260502_152315_349039` | AIAgent 自動生成 | 39 | 不同裝置產生不同 ID |
| UUID 格式 | `662b8a3d-11a4-427b-9dd0-...` | API Server/Gateway | 109 | 穩定但跨裝置不共享 |
| `api-` 前綴 | `api-1a2b3c4d5e6f7g8h` | `_derive_chat_session_id()` | 少量 | 基於內容指紋，換首句即斷 |

### eph_ 的根源

`eph_mooXXXX_YYYYYY` 格式的 ID 來自舊版 Hermes Agent 的 TUI 互動模式：
- `moo` 前綴看起來像是 sqids/nanoid 類的短 ID 生成器輸出
- 目前代碼中已**找不到** `eph_` 的生成邏輯（可能在 v0.10.0 前被移除）
- 這些會話的 JSON 備份存在但**未寫入 SQLite DB**
- 新版已改用 `YYYYMMDD_HHMMSS_XXXXXX` 格式

### _derive_chat_session_id 的問題

```python
# api_server.py L536-551
def _derive_chat_session_id(system_prompt, first_user_message):
    seed = f"{system_prompt or ''}\n{first_user_message}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
    return f"api-{digest}"
```

問題：
1. 相同首句 = 相同 session ID（看似功能，實為 bug）
2. 不同裝置發送相同內容 → 同一 session（意外合併）
3. 不同裝置發送不同內容 → 不同 session（期望行為但用戶困惑）
4. system_prompt 變化 → session ID 變化（不穩定）

## 實現方案

### Phase 1：統一 ID 格式規範

**目標格式**：`{platform}-{timestamp}-{short_uuid}`

```
api-20260528-115700-a1b2c3   # API Server
tui-20260528-115700-d4e5f6   # TUI/Dashboard
cron-20260528-040000-g7h8i9  # Cron Job（已符合）
gw-20260528-115700-j0k1l2   # Gateway (Telegram/Discord/...)
```

**優點**：
- 可讀性高（一眼看出平台和時間）
- 可排序（按時間排列）
- 全域唯一（timestamp + uuid6 字元）
- 不依賴內容指紋（避免內容變化導致 ID 斷裂）

**修改 `run_agent.py` L1818-1825**：

```python
# 現有：
if session_id:
    self.session_id = session_id
else:
    timestamp_str = self.session_start.strftime("%Y%m%d_%H%M%S")
    short_uuid = uuid.uuid4().hex[:6]
    self.session_id = f"{timestamp_str}_{short_uuid}"

# 改為：
if session_id:
    self.session_id = session_id
else:
    timestamp_str = self.session_start.strftime("%Y%m%d-%H%M%S")
    short_uuid = uuid.uuid4().hex[:6]
    platform_prefix = (self.platform or "cli").replace("_", "-")[:3]
    self.session_id = f"{platform_prefix}-{timestamp_str}-{short_uuid}"
```

### Phase 2：替換 _derive_chat_session_id

**修改 `api_server.py` L536-551**：

```python
# 替換基於內容指紋的 ID 生成，改用確定性的 session 續接機制
def _derive_chat_session_id(system_prompt, first_user_message):
    """Generate a unique session ID for new conversations.
    
    DEPRECATED: Content-fingerprinting is unreliable. Use X-Hermes-Session-Id
    header for session continuity instead.
    """
    timestamp_str = datetime.now().strftime("%Y%m%d-%H%M%S")
    short_uuid = uuid.uuid4().hex[:6]
    return f"api-{timestamp_str}-{short_uuid}"
```

### Phase 3：eph_ 遺留會話遷移

**遷移腳本**：

```python
#!/usr/bin/env python3
"""Migrate eph_ and legacy session IDs to unified format."""

import json, os, sqlite3, re
from pathlib import Path
from datetime import datetime

SESSIONS_DIR = Path("/data/.hermes/sessions")
DB_PATH = Path("/data/.hermes/state.db")

def migrate_session_id(old_id: str) -> str:
    """Convert legacy session ID to unified format."""
    # eph_mooXXXX_YYYYYY → eph-migrated-XXXX-YYYY
    if old_id.startswith("eph_"):
        parts = old_id[4:]  # 去掉 eph_
        return f"eph-migrated-{parts.replace('_', '-')}"
    
    # 20260502_152315_349039 → legacy-20260502-152315-349039
    if re.match(r'^\d{8}_\d{6}_', old_id):
        return f"legacy-{old_id.replace('_', '-')}"
    
    # UUID 格式和 cron 格式保持不變
    return old_id

def migrate():
    db = sqlite3.connect(str(DB_PATH))
    mapping = {}
    
    for fname in os.listdir(SESSIONS_DIR):
        if not fname.startswith("session_") or not fname.endswith(".json"):
            continue
        
        old_id = fname[8:-5]  # 去掉 session_ 前綴和 .json 後綴
        new_id = migrate_session_id(old_id)
        
        if old_id != new_id:
            # 重命名 JSON 文件
            old_path = SESSIONS_DIR / fname
            new_path = SESSIONS_DIR / f"session_{new_id}.json"
            
            # 更新 JSON 內容中的 session_id
            with open(old_path) as f:
                data = json.load(f)
            data["session_id"] = new_id
            
            with open(new_path, "w") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.unlink(old_path)
            
            mapping[old_id] = new_id
            
            # 更新 DB（如果存在）
            try:
                db.execute("UPDATE sessions SET id = ? WHERE id = ?", (new_id, old_id))
            except:
                pass
    
    db.commit()
    db.close()
    
    # 更新 backup_state.json
    backup_path = SESSIONS_DIR.parent / "backup_state.json"
    if backup_path.exists():
        with open(backup_path) as f:
            backup = json.load(f)
        sessions = backup.get("sessions", {})
        for old_id, new_id in mapping.items():
            if old_id in sessions:
                entry = sessions.pop(old_id)
                entry["filepath"] = entry["filepath"].replace(old_id, new_id)
                sessions[new_id] = entry
        with open(backup_path, "w") as f:
            json.dump(backup, f, indent=2, ensure_ascii=False)
    
    print(f"Migrated {len(mapping)} sessions")
    return mapping

if __name__ == "__main__":
    migrate()
```

### Phase 4：Session ID 穩定性保障

**修改 `api_server.py` — Session 續接流程**：

當前行為：
- 有 `X-Hermes-Session-Id` → 用它
- 沒有 → 用內容指紋 `_derive_chat_session_id()`

改為：
```python
# L1071-1082
else:
    # 優先使用客戶端提供的 session ID（Open WebUI 等前端通常管理 conversation ID）
    client_session_id = body.get("session_id", "") or body.get("conversation_id", "")
    if client_session_id:
        session_id = f"api-{client_session_id}"
    else:
        # 最後手段：生成新的唯一 ID（不再用內容指紋）
        session_id = _derive_chat_session_id(system_prompt, first_user_message)
```

**確保前端傳遞穩定的 conversation ID**：

Open WebUI 的每個 conversation 有唯一 ID，BFF 層需映射：

```javascript
// BFF: 將 Open WebUI 的 conversation_id 映射為 Hermes session_id
const upstreamHeaders = {
    'X-Hermes-Session-Id': `owui-${conversationId}`,
    'X-Hermes-User-Id': userId,
};
```

## 驗證步驟

1. 啟動新 session，確認 ID 格式為 `api-YYYYMMDD-HHMMSS-XXXXXX`
2. 用相同 `X-Hermes-Session-Id` 從兩個裝置連入，確認會話續接
3. 不帶 `X-Hermes-Session-Id` 的兩次請求，確認生成不同 ID
4. 執行遷移腳本，確認 eph_ 和日期格式會話正確遷移
5. 確認 Web UI 能正確顯示遷移後的會話

## 風險與注意事項

- **向後兼容**：遷移腳本必須同時更新 JSON 文件、DB、backup_state.json
- **壓縮分裂**：context compression 後會生成新 session_id（`_compress_context`），需確保新 ID 格式一致
- **Cron Job**：cron 的 session_id 格式 `cron_XXXX` 已穩定，不需修改
- **前端配合**：Open WebUI 等前端需配置傳遞 conversation ID
- **遷移回滾**：保留舊 ID → 新 ID 的映射表，以便回滾

## 相依技能

- `user-id-system`：User ID 可增強 session key 的穩定性
- `session-merge`：遷移後的 ID 格式統一，便於合併操作
