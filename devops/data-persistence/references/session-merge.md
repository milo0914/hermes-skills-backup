---
name: session-merge
version: 1.0.0
category: devops
description: 會話合併功能 — 將同一用戶的多個散落會話關聯合併，解決多裝置對話串碎片化問題
tags: [session, merge, consolidation, lineage, user-id, hermes-core]
author: hermes-agent
created: 2026-05-28
status: implementation-plan
---

# 會話合併功能 — 多裝置對話串碎片化解決方案

## 問題分析

當前系統中，同一用戶在不同裝置/時間產生的會話完全獨立，無法關聯：

### 碎片化場景

| 場景 | 產生的 Session | 問題 |
|------|---------------|------|
| 筆電發起對話 A | `api-20260528-100700-a1b2c3` | 手機看不到 |
| 手機接續討論 | `api-20260528-143000-d4e5f6` | 與 A 無關聯 |
| PC 新開話題 | `api-20260528-180000-g7h8i9` | 又一個孤立會話 |
| HF Space 重啟後重連 | `api-20260528-210000-j0k1l2` | 舊 session 找不到 |

### 現有 lineage 機制的局限

Hermes 已有 `parent_session_id` 欄位，但僅用於 context compression 分裂：
- 壓縮後生成新 session，`parent_session_id` 指向原 session
- 這是「垂直 lineage」（同一對話的壓縮分支），不是「水平合併」（不同對話的關聯）

### 需要的新概念：Session Group

```
Session Group (用戶「專利調研」主題)
├── api-20260528-100700-a1b2c3  (筆電發起)
├── api-20260528-143000-d4e5f6  (手機接續)
│   └── compressed-20260528-150000-x1y2z3  (壓縮分支, parent=d4e5f6)
└── api-20260528-180000-g7h8i9  (PC 補充)
```

## 實現方案

### Phase 1：DB Schema — Session Groups

**新增表**：

```sql
-- 會話群組：將多個獨立會話邏輯上關聯為一組
CREATE TABLE IF NOT EXISTS session_groups (
    group_id TEXT PRIMARY KEY,           -- 格式: grp-{timestamp}-{short_uuid}
    name TEXT NOT NULL DEFAULT '',       -- 用戶自定義名稱，如「專利調研」
    user_id TEXT,                        -- 關聯用戶（依賴 user-id-system）
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

-- 會話-群組關聯：多對多關係
CREATE TABLE IF NOT EXISTS session_group_members (
    group_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    joined_at REAL NOT NULL,
    relation_type TEXT NOT NULL DEFAULT 'member',  -- member | primary | continuation
    note TEXT DEFAULT '',                -- 備註：如「筆電發起」「手機接續」
    PRIMARY KEY (group_id, session_id),
    FOREIGN KEY (group_id) REFERENCES session_groups(group_id),
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

-- 會話間直接關聯：雙向連結
CREATE TABLE IF NOT EXISTS session_links (
    session_id_a TEXT NOT NULL,
    session_id_b TEXT NOT NULL,
    link_type TEXT NOT NULL,             -- continuation | related | fork | merged
    created_at REAL NOT NULL,
    created_by TEXT DEFAULT 'user',      -- user | auto | system
    PRIMARY KEY (session_id_a, session_id_b, link_type)
);

-- 用戶視圖：合併後的會話列表
CREATE VIEW IF NOT EXISTS user_sessions_grouped AS
SELECT 
    s.id as session_id,
    s.source,
    s.model,
    s.user_id,
    s.title,
    s.created_at,
    sg.group_id,
    sg.name as group_name,
    sgm.relation_type,
    sgm.note
FROM sessions s
LEFT JOIN session_group_members sgm ON s.id = sgm.session_id
LEFT JOIN session_groups sg ON sgm.group_id = sg.group_id
ORDER BY s.created_at DESC;
```

### Phase 2：合併 API

**修改 `hermes_state.py` — 新增方法**：

```python
class SessionDB:
    # ... 現有方法 ...
    
    def create_session_group(self, name: str, user_id: str = None) -> str:
        """Create a new session group and return its ID."""
        import uuid, time
        group_id = f"grp-{int(time.time())}-{uuid.uuid4().hex[:6]}"
        now = time.time()
        self.conn.execute("""
            INSERT INTO session_groups (group_id, name, user_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
        """, (group_id, name, user_id, now, now))
        self.conn.commit()
        return group_id
    
    def add_session_to_group(self, group_id: str, session_id: str,
                             relation_type: str = "member", note: str = "") -> None:
        """Add a session to a group."""
        import time
        self.conn.execute("""
            INSERT OR IGNORE INTO session_group_members 
            (group_id, session_id, joined_at, relation_type, note)
            VALUES (?, ?, ?, ?, ?)
        """, (group_id, session_id, time.time(), relation_type, note))
        self.conn.commit()
    
    def link_sessions(self, session_id_a: str, session_id_b: str,
                      link_type: str = "related", created_by: str = "user") -> None:
        """Create a direct link between two sessions."""
        import time
        # Ensure alphabetical order for consistency
        a, b = sorted([session_id_a, session_id_b])
        self.conn.execute("""
            INSERT OR IGNORE INTO session_links 
            (session_id_a, session_id_b, link_type, created_at, created_by)
            VALUES (?, ?, ?, ?, ?)
        """, (a, b, link_type, time.time(), created_by))
        self.conn.commit()
    
    def get_session_group(self, session_id: str) -> dict:
        """Get the group that a session belongs to, with all members."""
        cursor = self.conn.execute("""
            SELECT sg.group_id, sg.name, sg.user_id
            FROM session_groups sg
            JOIN session_group_members sgm ON sg.group_id = sgm.group_id
            WHERE sgm.session_id = ?
        """, (session_id,))
        row = cursor.fetchone()
        if not row:
            return None
        
        group_id, name, user_id = row
        
        # Get all members
        members_cursor = self.conn.execute("""
            SELECT s.id, s.title, s.source, s.created_at, sgm.relation_type, sgm.note
            FROM sessions s
            JOIN session_group_members sgm ON s.id = sgm.session_id
            WHERE sgm.group_id = ?
            ORDER BY s.created_at ASC
        """, (group_id,))
        
        return {
            "group_id": group_id,
            "name": name,
            "user_id": user_id,
            "members": [
                {
                    "session_id": m[0],
                    "title": m[1],
                    "source": m[2],
                    "created_at": m[3],
                    "relation_type": m[4],
                    "note": m[5],
                }
                for m in members_cursor.fetchall()
            ],
        }
    
    def get_related_sessions(self, session_id: str) -> list:
        """Get all sessions linked to this one."""
        cursor = self.conn.execute("""
            SELECT session_id_a, session_id_b, link_type, created_by
            FROM session_links
            WHERE session_id_a = ? OR session_id_b = ?
        """, (session_id, session_id))
        
        related = []
        for row in cursor.fetchall():
            other_id = row[1] if row[0] == session_id else row[0]
            related.append({
                "session_id": other_id,
                "link_type": row[2],
                "created_by": row[3],
            })
        return related
    
    def merge_sessions(self, session_ids: list, group_name: str = "",
                       user_id: str = None) -> str:
        """Merge multiple sessions into a group. Returns group_id."""
        if len(session_ids) < 2:
            raise ValueError("Need at least 2 sessions to merge")
        
        # Auto-generate group name if not provided
        if not group_name:
            # Use the earliest session's title
            cursor = self.conn.execute(
                "SELECT title FROM sessions WHERE id = ? ORDER BY created_at ASC LIMIT 1",
                (session_ids[0],)
            )
            row = cursor.fetchone()
            group_name = row[0] if row and row[0] else "Merged Session Group"
        
        group_id = self.create_session_group(group_name, user_id)
        
        # Add first session as primary, rest as continuation
        for i, sid in enumerate(session_ids):
            relation = "primary" if i == 0 else "continuation"
            self.add_session_to_group(group_id, sid, relation_type=relation)
        
        # Create bidirectional links between all pairs
        for i in range(len(session_ids)):
            for j in range(i + 1, len(session_ids)):
                self.link_sessions(
                    session_ids[i], session_ids[j],
                    link_type="merged", created_by="user"
                )
        
        return group_id
    
    def unmerge_session(self, session_id: str, group_id: str) -> None:
        """Remove a session from a group."""
        self.conn.execute("""
            DELETE FROM session_group_members 
            WHERE group_id = ? AND session_id = ?
        """, (group_id, session_id))
        
        # Remove links involving this session in this group
        group_members = self.conn.execute("""
            SELECT session_id FROM session_group_members WHERE group_id = ?
        """, (group_id,)).fetchall()
        member_ids = {m[0] for m in group_members}
        member_ids.add(session_id)
        
        self.conn.execute("""
            DELETE FROM session_links 
            WHERE (session_id_a = ? OR session_id_b = ?)
            AND link_type = 'merged'
        """, (session_id, session_id))
        
        # If group is empty or has only 1 member, clean up
        remaining = self.conn.execute("""
            SELECT COUNT(*) FROM session_group_members WHERE group_id = ?
        """, (group_id,)).fetchone()[0]
        
        if remaining <= 1:
            self.conn.execute("DELETE FROM session_group_members WHERE group_id = ?", (group_id,))
            self.conn.execute("DELETE FROM session_groups WHERE group_id = ?", (group_id,))
        
        self.conn.commit()
```

### Phase 3：Web UI 整合

**API Server 新增端點**：

```python
# api_server.py 新增路由

@app.post("/v1/sessions/merge")
async def merge_sessions(body: MergeRequest):
    """Merge multiple sessions into a group."""
    session_db = SessionDB()
    group_id = session_db.merge_sessions(
        session_ids=body.session_ids,
        group_name=body.group_name,
        user_id=body.user_id,
    )
    return {"group_id": group_id, "merged_count": len(body.session_ids)}

@app.get("/v1/sessions/{session_id}/group")
async def get_session_group(session_id: str):
    """Get the group that a session belongs to."""
    session_db = SessionDB()
    group = session_db.get_session_group(session_id)
    if not group:
        return {"group_id": None, "members": []}
    return group

@app.post("/v1/sessions/{session_id}/unmerge")
async def unmerge_session(session_id: str, body: UnmergeRequest):
    """Remove a session from its group."""
    session_db = SessionDB()
    session_db.unmerge_session(session_id, body.group_id)
    return {"status": "ok"}

@app.get("/v1/sessions/groups")
async def list_session_groups(user_id: str = None):
    """List all session groups, optionally filtered by user."""
    session_db = SessionDB()
    # ... query and return groups
```

### Phase 4：自動合併啟發式

**自動偵測可合併的會話**（基於語義相似度或時間/用戶關聯）：

```python
def auto_suggest_merges(self, user_id: str = None, time_window_hours: int = 24) -> list:
    """Suggest sessions that might belong together.
    
    Heuristics:
    1. Same user_id + similar title + within time window
    2. Same user_id + same model + within time window  
    3. Sessions that reference each other's content
    """
    suggestions = []
    cutoff = time.time() - (time_window_hours * 3600)
    
    query = """
        SELECT id, title, model, source, created_at 
        FROM sessions 
        WHERE created_at > ? AND user_id = ?
        ORDER BY created_at ASC
    """ if user_id else """
        SELECT id, title, model, source, created_at 
        FROM sessions 
        WHERE created_at > ?
        ORDER BY created_at ASC
    """
    
    params = (cutoff, user_id) if user_id else (cutoff,)
    sessions = self.conn.execute(query, params).fetchall()
    
    # Group by title similarity (simple: shared words > 50%)
    for i, s_a in enumerate(sessions):
        for s_b in sessions[i+1:]:
            title_sim = self._title_similarity(s_a[1], s_b[1])
            time_gap = abs(s_a[4] - s_b[4])
            
            if title_sim > 0.5 and time_gap < time_window_hours * 3600:
                suggestions.append({
                    "session_a": s_a[0],
                    "session_b": s_b[0],
                    "title_a": s_a[1],
                    "title_b": s_b[1],
                    "similarity": title_sim,
                    "time_gap_hours": time_gap / 3600,
                    "reason": "similar_title",
                })
    
    return suggestions

def _title_similarity(self, a: str, b: str) -> float:
    """Simple word-overlap similarity between two titles."""
    if not a or not b:
        return 0.0
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)
```

### Phase 5：跨裝置 Session 接續

**修改 API Server — 同一用戶+群組的 session 接續**：

```python
# api_server.py — 在處理新對話時，檢查是否可接續既有群組
async def _find_continuation_session(self, user_id: str, new_message: str) -> str:
    """Find an existing session that this message could continue.
    
    Only used when no X-Hermes-Session-Id is provided AND user_id is available.
    """
    if not user_id:
        return None
    
    session_db = SessionDB()
    # Find the user's most recent session that's still "active" (< 1 hour old)
    recent = session_db.conn.execute("""
        SELECT id FROM sessions 
        WHERE user_id = ? AND created_at > ?
        ORDER BY updated_at DESC LIMIT 1
    """, (user_id, time.time() - 3600)).fetchone()
    
    return recent[0] if recent else None
```

## 驗證步驟

1. 創建兩個獨立 session（模擬兩個裝置）
2. 執行 `merge_sessions([sid_a, sid_b], "測試群組")`
3. 查詢 `get_session_group(sid_a)` 確認包含兩個成員
4. 確認 Web UI 顯示群組視圖
5. 執行 `unmerge_session(sid_b, group_id)` 確認可解除合併
6. 測試 `auto_suggest_merges()` 確認建議合理

## 風險與注意事項

- **合併不是合併內容**：合併是邏輯關聯，不是將訊息合併到一個 session 中
- **壓縮 lineage 保留**：合併群組中的每個 session 仍保留自己的 parent_session_id lineage
- **權限**：只有同一 user_id 的 session 才能被合併（需 user-id-system）
- **刪除級聯**：刪除 session 時需清理 session_group_members 和 session_links
- **效能**：session_links 表需要 (session_id_a, session_id_b) 複合索引

## 相依技能

- `user-id-system`：合併需要 user_id 來識別同用戶的會話
- `unified-session-id`：統一 ID 格式後合併操作更可靠
- `robust-db-persistence`：DB 完整是合併的前提
