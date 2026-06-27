# v6.19 Kaggle Kernel Debug Session (2026-06-18/19)

## 問題背景
用戶推送 v6.19 notebook 到 Kaggle，Kernel 狀態直接從 RUNNING 跳到 COMPLETE（<20秒），無 stdout/stderr 訓練日誌，只有 nbconvert 輸出。

## 根因分析

### 1. Notebook source 格式錯誤
- 原本本地 notebook 的 code cell `source` 為 `list`（包含字面 `\n` 字符）而非 `str`
- 經 `json.load()` 讀取後發現：`isinstance(cell['source'], list) == True`
- 原因：`.py→.ipynb` 轉換時換行符被雙重轉義，導致整個 86KB 代碼變成單行、包含字面 `\n`
- Kaggle 遇到 `source=list` 時**跳過所有 cell 執行**，只跑 nbconvert 轉 HTML

### 2. Metadata 格式不匹配
- v6.19 初始 metadata 使用：`accelerator: "GPU_T4"`, `machine_shape: "NvidiaTeslaT4"`, `is_idle_no_idle: true`
- v6.18 成功 metadata：`machine_shape: "Gpu"`, `docker_image: "gcr.io/kaggle-private-byod/python@sha256:..."`
- 改用 v6.18 風格後 Kernel 正常進入 RUNNING 狀態（約 20 分鐘完成）

## 修復流程

### 步驟 1：從 GitHub 獲取正確版本
```bash
git clone https://$GITHUB_TOKEN@github.com/milo0914/aidigmoney.git /tmp/aidigmoney
# repo 中 "GRPO Regime-Aware Factor Training v6.19-composite score F" 為正確 .ipynb
```

### 步驟 2：驗證 Notebook 格式
```python
import json
with open('notebook.ipynb') as f:
    nb = json.load(f)
code = nb['cells'][1]['source']
assert isinstance(code, str), "source must be str!"
assert '\n' in code, "must have real newlines"
compile(code, 'test.py', 'exec')  # 語法檢查
```

### 步驟 3：使用 v6.18 風格 metadata 推送
```json
{
  "machine_shape": "Gpu",
  "docker_image": "gcr.io/kaggle-private-byod/python@sha256:57e612b484cf3df5026ee4dcc3cb176974b22b2bc0937fb1e16132a8be4cb13c",
  "enable_tpu": "false",
  "keywords": ["gpu"]
}
```

### 步驟 4：監控等待完成
- `kernels output` 在 RUNNING 時會阻塞，不回傳 "still running"
- 用 `kernels list -m --sort-by dateRun` 觀察 `lastRunTime` 更新
- 約 20 分鐘後 Kernel 完成，下載 log 成功

## 訓練結果分析

### 環境
- GPU：P100 (sm_60) → CUDA probe 失敗 → CPU fallback (GRPO_FORCE_CPU=1)
- 數據：成功載入 5 CSV（price_ohlcv, margin, us_indices, futures_oi, inst_flow），20 檔股票

### Collapse 現象
- `best_reward = -5.0`（觸發 `short_formula_penalty`）
- `val_IC = 0.0`, `train_IC = 0.0`
- `with_ops`: 23/32 → 0/32（探索完全崩潰）
- 最佳公式退化為單 feature token `[29]` → "INVALID"
- v6.18 強制重種觸發 4 次（step 1992/2992/3992/4992）但無法恢復

### 待修復方向
1. `short_formula_penalty=5.0` 過大 → 導致所有候選 reward=-5.0
2. Warmup operator seed 生成需確保長度 ≥4 的有效公式
3. CPU 模式 G=32 可能仍偏小（pitfall #63 建議 G≥16 但可能需更大）
4. 需 debug `compute_group_rewards` 對 invalid 公式的處理

## 關鍵經驗

1. **Notebook source 必須是 str + 真換行** — 最隱蔽致命坑
2. **Metadata 用 v6.18 風格（Gpu + docker_image）** — 非 accelerator/machine_shape 組合
3. **kernels output 阻塞行為** — RUNNING 時不回傳，只能間接監控
4. **GitHub repo 為權威來源** — 本地格式損壞時優先從 `milo0914/aidigmoney` clone
5. **P100 分配常態化** — 必須有 CPU fallback 邏輯，且 G≥16