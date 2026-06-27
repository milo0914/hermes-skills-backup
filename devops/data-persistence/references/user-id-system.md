---
name: user-id-system
version: 1.0.0
category: devops
description: 實現 User ID 系統 — 讓不同裝置透過同一帳號識別身份，解決多裝置會話隔離問題
tags: [session, user-id, multi-device, auth, hermes-core]
author: hermes-agent
created: 2026-05-28
status: implementation-plan
---

# User ID 系統 — 多裝置身份識別方案

## 問題分析

Hermes Agent 當前沒有使用者身份識別機制（經 2026-05-28 代碼級調查確認）：
- `create_session()` 的 `user_id` 參數始終為 `None`
- 所有 206 個 SQLite 會話 + 497 個 JSON 會話的 `user_id` 都是 `NULL` / `NOT_SET`
- 不同裝置連入時無法關聯為同一用戶
- API Server 依賴 `X-Hermes-Session-Id` header 做會話續接，但無身份綁定
- **Web UI「使用者」下拉選單是 Profile（設定檔），不是 user_id** — 見 references/web-ui-profile-vs-userid.md
- BFF createSession INSERT 不包含 user_id 欄位，fallback 路徑硬編碼 `user_id: null`
- BFF proxy 不轉發任何 user identity header 給 API Server
- API Server 不解析 OpenAI spec 的 `user` body 字段

### 影響的代碼位置

| 文件 | 行號 | 當前行為 | 需修改 |
|------|------|----------|--------|
| `run_agent.py` | L2432-2440 | `_ensure_db_session()` 傳 `user_id=None` | 改為接受外部 user_id |
| `hermes_state.py` | L713 | `create_session()` 接受 user_id 但不使用 | 加入 user_id 寫入 |
| `api_server.py` | L2675-2720 | `_route_chat_completions()` 讀 `X-Hermes-Session-Id` | 新增 `X-Hermes-User-Id` header 解析 |
| `api_server.py` | L820-860 | `_create_agent()` 無 user_id 參數 | 加入 user_id 傳遞 |
| `gateway/session.py` | L594-659 | `build_session_key()` 無 user_id 概念 | 加入 user_id 維度 |
| BFF (`index.js`) | createSession `Ad()` | INSERT 不含 user_id | 加入 user_id 欄位 |
| BFF (`index.js`) | proxy `uYI()` | 不轉發 user identity | 加入 `X-Hermes-User-Id` header |
| `api_server.py` | chat completions | 不解析 OpenAI spec `user` body 字段 | 解析並傳遞 user_id |

## 實現方案

### Phase 1：API Server User ID Header（最小改動）

**原理**：OpenAI-compatible API 前端（Open WebUI、LobeChat 等）通常已有用戶系統。透過 header 傳遞 user_id。

**修改 `api_server.py`**：

```python
# 在 /v1/chat/completions 處理函數中（約 L1042 附近）
# 現有：
provided_session_id = request.headers.get("X-Hermes-Session-Id", "").strip()

# 新增：
provided_user_id = request.headers.get("X-Hermes-User-Id", "").strip()
if not provided_user_id:
    # 嘗試從 API key 關聯的用戶資料中提取
    provided_user_id = self._api_key_to_user_id.get(self._api_key, "anonymous")
```

**修改 `run_agent.py`**：

```python
# _ensure_db_session() — L2432
self._session_db.create_session(
    session_id=self.session_id,
    source=self.platform or os.environ.get("HERMES_SESSION_SOURCE", "cli"),
    model=self.model,
    model_config=self._session_init_model_config,
    system_prompt=self._cached_system_prompt,
    user_id=self._user_id,  # ← 改為從初始化參數傳入
    parent_session_id=self._parent_session_id,
)
```

**修改 `AIAgent.__init__()` — L1079**：

```python
def __init__(self, ..., user_id: str = None, ...):
    ...
    self._user_id = user_id  # 新增屬性
```

### Phase 2：DB Schema 擴展

**修改 `hermes_state.py`**：

1. 確認 `sessions` 表已有 `user_id` 欄位（當前 schema 已定義但未使用）
2. 新增 `user_devices` 表：

```sql
CREATE TABLE IF NOT EXISTS user_devices (
    user_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    device_name TEXT,
    last_seen REAL NOT NULL,
    first_seen REAL NOT NULL,
    PRIMARY KEY (user_id, device_id)
);
```

3. 新增 `user_sessions` 視圖：

```sql
CREATE VIEW IF NOT EXISTS user_sessions AS
SELECT s.*, ud.device_name
FROM sessions s
LEFT JOIN user_devices ud ON s.user_id = ud.user_id
WHERE s.user_id IS NOT NULL;
```

### Phase 3：Web UI 登入整合

**修改 Web UI BFF（`/opt/hermes-web-ui`）**：

1. 登入頁面增加用戶名/密碼 或 OAuth 選項
2. 登入後將 `user_id` 注入到所有 API 請求的 `X-Hermes-User-Id` header
3. Cookie/Session 存儲 `user_id`，跨分頁共享

**配置示例**：

```yaml
# config.yaml
auth:
  enabled: true
  provider: "token"  # token | oauth | huggingface
  # Hugging Face Spaces 可使用 HF User Info
  huggingface:
    enabled: true
    # HF Spaces 提供 X-Gradio-User header
    header: "X-Gradio-User"
```

### Phase 4：Session Key 包含 User ID

**修改 `gateway/session.py` — `build_session_key()`**：

```python
def build_session_key(
    source: SessionSource,
    group_sessions_per_user: bool = True,
    thread_sessions_per_user: bool = False,
) -> str:
    ...
    # 在 key_parts 中加入 user_id
    if source.user_id:
        key_parts.insert(2, f"user:{source.user_id}")
    ...
```

## 前端配置（Open WebUI / LobeChat）

Open WebUI 已支持 `X-User-Id` header，需在 BFF 層映射：

```javascript
// BFF 代理層
upstreamHeaders['X-Hermes-User-Id'] = req.session.user_id;
upstreamHeaders['X-Hermes-Session-Id'] = conversationId;
```

## 驗證步驟

1. 設定 `API_SERVER_KEY` 啟用認證
2. 用 curl 測試：
```bash
curl -X POST http://localhost:8642/v1/chat/completions \
  -H "Authorization: Bearer $API_KEY" \
  -H "X-Hermes-User-Id: user-alice" \
  -H "X-Hermes-Session-Id: shared-session-1" \
  -H "Content-Type: application/json" \
  -d '{"model":"...","messages":[{"role":"user","content":"hello"}]}'
```
3. 從另一裝置用相同 User-Id 和 Session-Id 發送：
```bash
# 筆電
curl ... -H "X-Hermes-User-Id: user-alice" -H "X-Hermes-Session-Id: shared-session-1"
# 手機
curl ... -H "X-Hermes-User-Id: user-alice" -H "X-Hermes-Session-Id: shared-session-1"
```
4. 確認 DB 中兩個請求的 `user_id` 相同

## 風險與注意事項

- **向後兼容**：`user_id=None` 必須繼續正常工作（匿名模式）
- **安全**：`X-Hermes-User-Id` header 僅在啟用 `API_SERVER_KEY` 時接受
- **HF Spaces 限制**：Gradio 不傳遞用戶身份，需自行實現登入
- **隱私**：user_id 不應包含敏感信息，建議使用 hash 或匿名 ID
- **Profile ≠ User ID**：前端 ProfileSelector 是配置隔離，不能作為身份標識。BFF sessions.profile 存的是 "default" 等配置名，sessions.user_id 才是身份但從未寫入
- **BFF 不轉發身份**：即使前端有密碼登入，BFF proxy 不會將 username 映射為 X-Hermes-User-Id 傳給 API Server

## 參考文件

- `references/web-ui-profile-vs-userid.md` — Web UI Profile vs User ID 完整代碼證據（BFF 架構、INSERT 語句、proxy header、API Server 忽略的 user 字段）

## 相依技能

- `unified-session-id`：統一 ID 格式後，user-id 的 session 查詢更可靠
- `session-merge`：合併功能依賴 user_id 來識別同用戶的會話
