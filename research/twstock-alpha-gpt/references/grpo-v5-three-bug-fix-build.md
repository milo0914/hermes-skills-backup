# GRPO v5 3-Bug Fix Build (2026-06-09)

基於 v3.2 source 修復 3 大 bug，推送為 `grpo-regime-aware-factor-training-v5-3-bug-fix`。

## 3 Bug 根因與修復

### Bug 1: Dataset 掛載路徑寫死 (v3.1 root cause)

- **症狀**: v3.1 log 顯示「無 Kaggle Dataset，使用合成數據」
- **根因**: `data_path = "/kaggle/input/twstock-training-data"` 寫死，但 dataset slug 為 `twstock-grpo-training-data`
- **v5 修復**: 保留 auto-detect 遞迴掃描 `/kaggle/input/`，加入 verbose debug:
  ```python
  print(f" [v5 Debug] /kaggle/input contents: {os.listdir('/kaggle/input/')}")
  print(f" [v5 Debug] data_path = {data_path} (type={type(data_path)}, exists={os.path.exists(str(data_path) if data_path else '')})")
  ```

### Bug 2: Kaggle 環境分配 CPU-only PyTorch (v3.2 root cause)

- **症狀**: v3.2 log 顯示 `PyTorch: 2.10.0+cpu`，`torch.cuda.is_available()=False`
- **根因**: Kaggle 執行環境預裝 CPU 版 PyTorch，即使 metadata 設 `enable_gpu: true`
- **v5 修復**: 腳本開頭加入:
  ```python
  if not torch.cuda.is_available():
      import subprocess
      subprocess.check_call([sys.executable, "-m", "pip", "install", "torch",
          "--index-url", "https://download.pytorch.org/whl/cu128"])
      importlib.reload(torch)
  ```

### Bug 3: Loss 梯度消失 — advantage 歸一化壓縮有效信號 (v3.2 root cause)

- **症狀**: v3.2 log 顯示 12500 步 `loss=-0.0000`，reward 停滯 (mean_r 不動)
- **根因鏈**: 合成數據 → reward 差異極小 → group advantages ≈ 0 → loss ≈ 0 → 梯度 ≈ 0
- **v5 修復 (三管齊下)**:
  1. **Advantage variance scaling**: `scaled_advantages = advantages / (advantages.std() + 1e-8)` 替代 `(advantages - mean) / (std + 1e-8)` 標準化
     - 保留符號和相對大小
     - 避免均值為零時整組歸零（標準化後 advantages 均值=0 是 PPO loss=0 的另一個貢獻因素）
  2. **REINFORCE 首步**: `loss_first = -(dist.log_prob(action) * advantages.detach()).mean()`
     - 確保第一步梯度非零（v3.5 REINFORCE 修復的補充）
  3. **增大 group_size**: GPU=16, CPU=8
     - group 越大，advantage 估計方差越低
     - 配置: LARGE_CAP=8, MID_CAP_TECH=6, TRADITIONAL=4, FINANCIAL=4
  4. **根本解決**: 用真實 FinMind 數據（twstock_daily.csv, 2022-2025）讓 reward 有真實差異

## v3.2 合成數據訓練實測結果 (2026-06-09 確認)

v3.2 使用合成數據完成執行（CPU-only PyTorch，因 dataset 掛載失敗 fallback）：

| 指標 | 值 |
|------|-----|
| 唯一完成 regime | FINANCIAL (2882) |
| 最佳公式 | NASDAQ_CLOSE |
| Val IC | 0.203 |
| Walk-Forward IC | 0.242 |
| t-stat | 1.12 |
| loss (全部步數) | -0.0000 (4位小數格式，實際可能非零) |
| mean_r (停滯) | 0.639 / 2.620 |

**關鍵發現**：
1. 僅 financial regime 完成訓練（合成數據 4 檔股票中只有 2882 有足夠變異）
2. loss 印出 `.4f` 格式掩蓋了可能的微小非零值（見 pitfall #56）
3. 公式選擇 NASDAQ_CLOSE（合成數據中美股因子恆為 0，此選擇無意義）
4. 合成數據訓練結果不可用——必須用真實 FinMind 數據重新訓練

## 版本演進時間線

| 版本 | Kernel Slug | 狀態 | 主要 Bug | 關鍵修復 |
|------|-------------|------|----------|----------|
| v3.1 | `twse-grpo-regime-aware-alpha-factor-training-v3-1` | ERROR | Dataset 路徑寫死 + action.unsqueeze(0) 維度 | — |
| v3.2 | `grpo-regime-aware-alpha-factor-training-v3-2-fix` | COMPLETE (合成數據) | CPU-only PyTorch + loss=-0.0000 | PPO ratio 梯度修復 + merge 模式 |
| v3.3 | `grpo-v33-dsfix` / `grpo-v33-nogpu-test` | RUNNING | 待驗證 os.walk 路徑偵測 | os.walk 遞迴掃描 + squeeze(0) |
| v3.4 | `grpo-regime-aware-factor-training-v3-4` | RUNNING | NaN logits 崩潰 | _safe_logits + lr=3e-4 + GradScaler |
| v3.5 | `grpo-regime-aware-factor-training-v3-5` | IndentationError | PPO loss≡0 | REINFORCE policy gradient |
| v4 | `grpo-regime-aware-factor-training-v4` | COMPLETE (CPU fallback) | P100 sm_60 不相容 | 三版統合 + CUDA probe + CPU fallback |
| v5 | `grpo-regime-aware-factor-training-v5-3-bug-fix` | RUNNING | 3 bug (路徑/CPU-PyTorch/loss梯度) | auto-detect + CUDA pip + advantage scaling |

## v5 Source

- 路徑: `/tmp/kaggle-kernel-v5/grpo_regime_training_v5.py` (2358 行)
- 7 處 `### v5 FIX` 標記
- Metadata: `/tmp/kaggle-kernel-v5/kernel-metadata.json`
- Kernel slug: `mhhuang14/grpo-regime-aware-factor-training-v5-3-bug-fix`
- Dataset: `mhhuang14/twstock-grpo-training-data`

## 監控

- Cron job: `kaggle-grpo-v5-monitor` (job_id=fff8a21f2e10)
- 排程: 每 5 分鐘，共 12 次
- 輸出目錄: `/tmp/kaggle-v5-output/`

## 待驗證項目

1. `[v5 Debug]` 輸出確認 dataset 掛載成功
2. `PyTorch: ...+cu128` 和 `device=cuda` 確認 GPU 啟用
3. `loss=...` 非 -0.0000 且有收斂趨勢
4. 4 regime 訓練完成並產出 `best_strategy_per_regime.json`
