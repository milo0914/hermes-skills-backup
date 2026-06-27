# Session-Backup Pipeline 架構

## ⚠️ 已知缺口：Web UI DB 未同步

上述 pipeline 僅操作 `~/.hermes/state.db`（Hermes CLI DB）。Web UI 使用獨立的 `~/.hermes-web-ui/hermes-web-ui.db`，兩者無持續同步機制。詳見 `hermes-session-analysis` skill 的 `references/webui-dual-db-architecture.md`。

提議的 Phase D（尚未實裝）：CLI DB → Web UI DB 增量同步，含欄位映射。

## 現有組件清單（2026-05-28 確認）

| 組件 | 路徑 | 功能 | 方向 |
|------|------|------|------|
| backup_sessions.py | `/data/.hermes/bin/backup_sessions.py` | DB→JSON 增量備份 | DB→JSON |
| sync_daemon.py | `scripts/sync_daemon.py` | JSON→DB 孤兒會話補錄 | JSON→DB |
| sync_json_to_db.py | `scripts/sync_json_to_db.py` | JSON→DB 單次同步（含 dry-run） | JSON→DB |
| data_sync.py | `/app/src/data_sync.py` | HF 全量上傳（upload_large_folder） | DB→HF |
| session-backup cron | job_id=6527076f63be, 每6hr | 執行 backup_sessions.py | 排程 |

## 提議的 3-Phase Pipeline（已實裝 A/B/C，D 待實裝）

```
session-backup cron (每 6hr)
 ├─ Phase A: JSON → CLI DB （補孤兒會話）✓
 ├─ Phase B: CLI DB → JSON （增量 hash 備份）✓
 ├─ Phase C: CLI DB → HF （可選）✓
 └─ Phase D: CLI DB → Web UI DB （增量同步）⏳
```

### Phase A: JSON→DB 詳細流程
1. 讀取 SQLite 所有 session IDs
2. 掃描 `/data/.hermes/sessions/` 目錄
3. 找出 DB 中不存在的孤兒會話（JSON only）
4. 逐個導入 session metadata + messages 到 DB
5. 批量 commit（不要每個 session 單獨 commit，避免大量 SQLite commit）

### Phase B: DB→JSON 詳細流程（現有 backup_sessions.py 邏輯）
1. 讀取 SQLite sessions 表
2. 計算每個 session data 的 MD5 hash
3. 與 backup_state.json 中的 hash 比對
4. 只寫入有變更的 JSON 文件
5. 更新 backup_state.json

### Phase C: DB→HF 詳細流程（可選）
1. 檢查 HF_DATASET_REPO 和 HF_TOKEN 環境變數
2. 呼叫 data_sync.py 的 DatasetManager.upload_to_dataset()
3. upload_large_folder() 做全量覆寫（整個 /data/.hermes 目錄樹）
4. 單次 commit（6hr 內只此一次）

## 為什麼不用獨立 daemon

| 因素 | daemon 模式（每5min） | cron pipeline（每6hr） |
|------|---------------------|----------------------|
| HF commits/天 | ~288（若串接HF） | 4 |
| SQLite 鎖衝突 | 高頻寫入增加衝突率 | 6hr 一次，低風險 |
| 資源佔用 | 常駐進程 | cron 觸發後釋放 |
| 數據一致性 | A/B 獨立，可能交叉 | 順序執行，保證一致 |

## 環境變數依賴

| 變數 | 用途 | 目前狀態 |
|------|------|----------|
| HF_DATASET_REPO | HF Dataset 倉庫名 | NOT_SET |
| HF_TOKEN / HUGGING_FACE_HUB_TOKEN | HF write token | NOT_SET |
| HERMES_HOME | Hermes 資料目錄 | /data/.hermes（預設） |

## backup_state.json 結構

記錄每個已備份 session 的 hash 和路徑，用於增量判斷：

```json
{
  "sessions": {
    "<session_id>": {
      "hash": "<md5>",
      "filepath": "/data/.hermes/sessions/session_<id>.json",
      "updated_at": "2026-05-26T12:03:29.xxx"
    }
  },
  "last_backup": "2026-05-28T12:04:53"
}
```

## 數據源不一致問題（2026-05-28，Phase A/B 實裝後）

JSON↔CLI DB 已透過 Phase A/B 同步。但 CLI DB ↔ Web UI DB 仍有缺口：

| 數據源 | 會話數 | 說明 |
|--------|--------|------|
| JSON 文件 | ~497 | sessions/ 目錄中的 .json 文件 |
| CLI SQLite state.db | 321 | DB 中的會話記錄（含孤兒補錄） |
| Web UI SQLite hermes-web-ui.db | 124 | Web UI 自己的 DB，僅 api_server 來源 |
| backup_state.json | ~313 | 有 hash 記錄的會話（與 CLI DB 同步） |

三個數據源不同步的原因：backup_sessions.py 只備份 DB 中的會話，但有些會話只存在 JSON 中（孤兒會話）。Phase A 解決這個問題——先將孤兒會話補進 DB，Phase B 才能完整備份。Phase D（待實裝）解決 CLI DB → Web UI DB 的同步缺口。
