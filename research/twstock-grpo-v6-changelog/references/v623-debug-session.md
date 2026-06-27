# v6.23 Kaggle 實測與 Debug Session (2026-06-20)

## 任務背景
v6.22 遺留 4 大根因 Bug，v6.23 實作修復並推送 Kaggle 驗證。

## 關鍵修復 (v6.23)
| # | Bug | 修復 |
|---|-----|------|
| 1 | min_formula_len 硬過濾 (-999) | 降級懲罰: `composite -= 0.15 * (4 - len)` |
| 2 | 探索重啟無 cooldown | 新增 `last_restart_step`，兩處觸發條件加 `step - last_restart_step >= 500` |
| 3 | _best_toks 指向當前步 | 改指向歷史最佳 `best_formula` |
| 4 | reward_weights complexity 0.45 壓過 ic 0.30 | 重新平衡: `ic=0.35, complexity=0.25, sharpe=0.15, mdd=0.08, turnover=0.04` |

## 部署流程與語法錯誤修復

### 語法錯誤：Comment in lambda default_factory 破壞 Parser
**現象**: Kernel 推送後瞬間失敗，log 顯示 `SyntaxError: '{' was never closed` at line 730。

**錯誤代碼**:
```python
reward_weights: dict = field(default_factory=lambda: {"ic": 0.35, ..., "length": 0.08  # 【v6.23 P0】complexity 0.45→0.25 讓IC信號主導  # 【v6.13】complexity 終於生效})
```

**根因**: Python parser 將 comment 視為延伸到行尾，導致 lambda 的 closing `)` 被 comment「吃掉」，dict 的 `}` 也因此未閉合。

**修復**: 正**: 將 comment 移至獨立行
```python
# 【v6.23 P0】reward_weights: complexity 0.45→0.25 讓IC信號主導  # 【v6.13】complexity 終於生效
reward_weights: dict = field(default_factory=lambda: {"ic": 0.35, ..., "length": 0.08})
```

**通用規則**: **在 `lambda:`、`field(default_factory=...)`、或任何 inline expression 內的 dict/list literal 後，切勿在同一行加 comment**，否則 closing delimiter 會被吞噬。應將 comment 放在上一行或分行。

### Kernel 推送與監控

#### 推送 v2 (修復後)
- **Slug**: `mhhuang14/twstock-grpo-v6-23-4-bug-root-cause-fix`
- **Kernel-metadata.json 關鍵設定** (參照 kaggle-api skill):
  - `machine_shape: "Gpu"` (非 NvidiaTeslaT4)
  - `docker_image` 指定具體 sha256
  - `is_idle_no_idle: "true"` 確保 auto-run
  - `dataset_sources: ["mhhuang14/twstock-v6-0-real-data-20stocks-5y"]`
  - `id: "mhhuang14/twstock-grpo-v6-23"` (與前版本一致，產生 version 2)

#### 監控腳本
```bash
#!/bin/bash
export KAGGLE_API_TOKEN="KGAT_..."
KERNEL="mhhuang14/twstock-grpo-v6-23-4-bug-root-cause-fix"
OUTDIR="/tmp/kout_v623_v2"

mkdir -p "$OUTDIR"
while true; do
    RESULT=$(~/.local/bin/kaggle kernels output "$KERNEL" -p "$OUTDIR" 2>&1)
    if echo "$RESULT" | grep -q "still running"; then
        echo "[$(date +%H:%M:%S)] Still running..."
        rm -f "$OUTDIR"/*
        sleep 60
    elif ls "$OUTDIR"/*.log 2>/dev/null; then
        echo "[$(date +%H:%M:%S)] Completed! Log downloaded."
        break
    else
        echo "[$(date +%H:%M:%S)] Empty output, waiting..."
        sleep 60
    fi
done
```

#### Python API 狀態檢查 (比 CLI 穩定)
```python
from kaggle.api.kaggle_api_extended import KaggleApi
api = KaggleApi(); api.authenticate()
status = api.kernels_status('mhhuang14/twstock-grpo-v6-23-4-bug-root-cause-fix')
# 回傳: {"status": "RUNNING", "failureMessage": ""}
```

## 當前狀態
- Kernel v2 已推送，**RUNNING 中** (背景監控進行中)
- 預期訓練時間: GPU ~10-15 min, CPU ~45 min
- 關鍵觀察指標: `best_reward` (應為正), `val_ic_best`, `with_ops`, `avg_ops`, `best_composite`

## 相關檔案
- 本地 notebook: `/tmp/kpull_v623/twstock-grpo-v6-23-4-bug-root-cause-fix.ipynb` (已修復語法)
- Kaggle Kernel: https://www.kaggle.com/code/mhhuang14/twstock-grpo-v6-23-4-bug-root-cause-fix
- 監控腳本: `/tmp/monitor_v623.sh`