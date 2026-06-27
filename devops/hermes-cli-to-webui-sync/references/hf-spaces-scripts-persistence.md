# HF Spaces Scripts/ 目錄持久化問題

## 問題

在 Hugging Face Spaces 上運行 Hermes Agent 時，`/data/.hermes/scripts/` 目錄的內容
會在容器重建後丟失，導致所有 `no_agent=True` 的 cron job 報錯 `Script not found`。

## 根因分析

### 容器重建觸發條件

- Space 設定變更（環境變數、secrets、hardware）
- 手動重啟（Factory reboot 或 Settings 重啟）
- Sleep/wake 週期（免費版 Spaces 會休眠）
- Runtime 更新（Docker base image 變更）

### 持久化行為

`/data/` 是 HF Spaces 的持久存儲（persistent storage），但持久化是**文件級別**的，
不是**目錄結構級別**的。具體行為：

| 路徑 | 持久化 | 原因 |
|---|---|---|
| `/data/.hermes/state.db` | 是 | 文件存在於容器啟動前 |
| `/data/.hermes/skills/` | 是 | 目錄和文件在容器啟動前已存在 |
| `/data/.hermes/cron/jobs.json` | 是 | 文件在容器啟動前已存在 |
| `/data/.hermes/scripts/*.py` | **否** | 目錄被 mkdir 建立，但文件是運行時才寫入的 |

### 為什麼 scripts/ 會丟失

1. Hermes 啟動流程（`hermes gateway run`）**不自動還原 scripts/ 內容**
2. Cron scheduler 在 `_run_job_script()` 中只做 `scripts_dir.mkdir(parents=True, exist_ok=True)`
   — 建立空目錄，不還原文件
3. Agent 手動部署的腳本（`cp` 到 scripts/ 的）不會被任何自動機制還原

### Cron Scheduler 安全限制

`_run_job_script()` 的路徑檢查邏輯（`cron/scheduler.py` line ~700）：

```python
scripts_dir = _get_hermes_home() / "scripts"
scripts_dir_resolved = scripts_dir.resolve()

raw = Path(script_path).expanduser()
if raw.is_absolute():
    path = raw.resolve()
else:
    path = (scripts_dir / raw).resolve()

# Guard against path traversal — scripts MUST reside within HERMES_HOME/scripts/
try:
    path.relative_to(scripts_dir_resolved)
except ValueError:
    return False, "Blocked: script path resolves outside the scripts directory"
```

結論：**絕對路徑、外部 symlink、路徑遍歷全部被擋**，腳本必須在 `scripts/` 內。

## 解決方案：三層自癒架構

### Layer 1: Wrapper 腳本（scripts/，會丟失）

極簡 delegate，Python 用 `subprocess.call`，Bash 用 `exec`：

```python
#!/usr/bin/env python3
"""Wrapper: delegates to the real script in skills/ (persistent storage)."""
import subprocess, sys, os
REAL = '/data/.hermes/skills/devops/hermes-cli-to-webui-sync/scripts/sync-sessions-to-webui.py'
if not os.path.exists(REAL):
    print(f'ERROR: Real script not found at {REAL}')
    sys.exit(1)
sys.exit(subprocess.call([sys.executable, REAL] + sys.argv[1:]))
```

```bash
#!/bin/bash
# Wrapper: delegates to the real script in skills/ (persistent storage)
REAL='/data/.hermes/skills/devops/github-skills-backup/scripts/github-skills-backup.sh'
if [ ! -f "$REAL" ]; then
    echo "ERROR: Real script not found at $REAL"
    exit 1
fi
exec bash "$REAL" "$@"
```

### Layer 2: 真實腳本（skills/，持久）

放在 skill 的 `scripts/` 子目錄中，由 HF Spaces 持久存儲保護。

### Layer 3: 自癒 cron job（agent 模式）

- 名稱：`restore-scripts-after-rebuild`
- 頻率：每 10 分鐘
- 模式：**agent**（不能是 no_agent，因為 no_agent 也需要 scripts/ 中有腳本）
- 執行：`python3 /data/.hermes/skills/devops/hermes-cli-to-webui-sync/scripts/restore-scripts.py`
- 無變化時靜默（節省 token），有還原時才輸出

### 空窗期

容器重建後 0~10 分鐘，sync job 可能失敗一次。restore job 在下次 tick 時修復。
這是 token 成本 vs 可用性的合理平衡。

## 驗證步驟

```bash
# 1. 確認 skills/ 中的真實腳本存在
test -f /data/.hermes/skills/devops/hermes-cli-to-webui-sync/scripts/sync-sessions-to-webui.py && echo "OK"

# 2. 確認 scripts/ 中的 wrapper 存在
test -f /data/.hermes/scripts/sync-sessions-to-webui.py && echo "OK"

# 3. 手動觸發 restore 測試
python3 /data/.hermes/skills/devops/hermes-cli-to-webui-sync/scripts/restore-scripts.py

# 4. 確認 cron job 正常
cronjob(action='list')  # restore-scripts-after-rebuild 應為 ok
```

## 已排除的方案

| 方案 | 問題 |
|---|---|
| Symlink（scripts/x.py → skills/.../x.py） | symlink 本身在容器重建後也會丟失 |
| 絕對路徑在 cron job script 欄位 | 被 `_run_job_script()` 安全檢查擋掉 |
| 修改 hermes_cli 代碼加 startup hook | 無法修改 HF Spaces 的預裝包 |
| no_agent 模式的 restore job | 雞生蛋問題：no_agent 需要 script 在 scripts/，但 scripts/ 已丟失 |
