# GRPO v6.11 Changelog
Date: 2026-06-16

## v6.11 — Early Stop + Param Tune + GPU Fix sm_50

### 基線
- **Kaggle 來源**: `mhhuang14/twstock-grpo-regime-aware-factor-training-v6-9` version 8
- **確認**: 該 version 8 即 v6.10 內容（title 顯示 v6.10，含 Rank-Based Advantage + stock_id int 鍵修復）
- **下載指令**: `python3 -m kaggle kernels pull mhhuang14/twstock-grpo-regime-aware-factor-training-v6-9`
- **下載位置**: `/tmp/v610_download/` (73789 bytes)

### v6.10 version 8 基線參數
| 參數 | v6.10 值 |
|------|---------|
| sm_arch | sm_70 |
| cc[0] threshold | >= 7 |
| train_steps | 15000 |
| temperature_decay_steps | 5000 |
| temperature_end | 0.5 |
| entropy_coef | 0.15 |
| diversity_penalty | 3.0 |
| adv_std_threshold | 0.1 |
| min_group_size | 16 |
| LARGE_CAP group_size | 64 (RegimeConfig) |
| MID_CAP_TECH group_size | 12 (RegimeConfig) |
| reward_weights | ic:0.5, sharpe:0.25, mdd:0.15, turnover:0.1 |

### 修改 1: GPU 相容性擴大
- **問題**: v6.10 仍限制 sm_70 (cc >= 7)，P100/GTX1060 等無法使用
- **修復**: `sm_70 → sm_50`, `cc[0] >= 7 → cc[0] >= 5`
- **新增 CUDA kernel 實測**: 不只檢查 CC，還執行 `torch.zeros + synchronize()` 驗證
- **Why sm_50**: Maxwell 架構 (GTX 900系列, GTX 750 Ti)，涵蓋所有 Kaggle/Colab 免費 GPU

### 修改 2: Early Stopping (新增功能)
- **問題**: v6.10 訓練到 step 15000 但 IC 在 step 1000 後停滯，浪費 GPU 時間
- **新增參數**: `early_stop_patience=500`, `early_stop_min_delta=1e-4`
- **實作邏輯**:
  - 每 200 step 檢查 val_IC
  - `best_val_ic` 追蹤歷史最佳
  - 連續 patience_counter >= 500 → break
  - `n_steps` 回報 `step+1`（實際步數，非 config.train_steps）
  - 新增 `best_step` 欄位到 return dict

### 修改 3: 參數優化
| 參數 | v6.10 | v6.11 | 原因 |
|------|-------|-------|------|
| train_steps | 15000 | 8000 | IC step 1000 後停滯，縮短省時 |
| temperature_decay_steps | 5000 | 8000 | 溫度衰減延長到訓練結束 |
| temperature_end | 0.5 | 0.8 | 保留探索動力到後期 |
| entropy_coef | 0.15 | 0.25 | 更強探索 |
| adv_std_threshold | 0.1 | 0.05 | 更靈敏的 group 縮小觸發 |
| min_group_size | 16 | 8 | 允許更小的動態 group |

### 修改 4: Regime-specific group_size
| Regime | v6.10 | v6.11 | 原因 |
|--------|-------|-------|------|
| TRADITIONAL | 16 | 16 | 維持不變 |
| LARGE_CAP | 64 | 64 | 維持不變（v6.10已有64） |
| MID_CAP_TECH | 12 | 24 | IC 退化，增加探索 |
| FINANCIAL | 16 | 16 | 維持不變 |

### 修改 5: 公式複雜度獎勵 (新增功能)
- **問題**: v6.10 因子多為單一特徵（1-2 tokens），缺乏運算符
- **新增參數**: `min_formula_len=3`, `operator_bonus=0.1`
- **reward_weights 新增**: `"complexity": 0.05`
- **效果**: 鼓勵生成更長的公式，包含運算符（+、-、*、/）

### 新增 GRPOConfig 參數
- `early_stop_patience: int = 500`
- `early_stop_min_delta: float = 1e-4`
- `min_formula_len: int = 3`
- `operator_bonus: float = 0.1`
- reward_weights 新增 `"complexity": 0.05`

### 版本號更新
- v6.9 → v6.11 (全域 25 處)
- v6.10 → v6.11 (全域 1 處)
- Title: `TWStock GRPO Regime-Aware Factor Training v6.11 (Early Stop + Param Tune + GPU Fix)`

### 驗證
- [x] 所有 v6.9 殘留清除（0 出現）
- [x] 所有 v6.10 殘留清除（0 出現）
- [x] py_compile exit_code=0
- [x] 全部 21 項參數檢查通過

### Kaggle Push
- **Push 目錄**: `/tmp/kpush_v611/`
- **Notebook**: `twstock-grpo-regime-aware-factor-training-v6-11.ipynb` (88861 bytes)
- **Kernel metadata**: `kernel-metadata.json` (id 沿用舊 slug v6-9, title 改為 v6.11)
- **結果**: `Kernel version 4 successfully pushed.`
- **URL**: https://www.kaggle.com/mhhuang14/twstock-grpo-regime-aware-factor-training-v6-11
- **注意**: Kaggle 自動從 title 產生新 slug，但 id 仍指向 v6-9 舊 slug

### 監控項目 (Step 4)
- [ ] IC 曲線是否持續改善到 step 8000
- [ ] 公式長度分佈（應有 3+ tokens）
- [ ] Large_Cap val_IC 是否轉正
- [ ] 是否觸發 early stopping
- [ ] adv_std 是否穩定 (Rank-based ≈0.577)
- [ ] temperature 遞減是否正常（到 step 8000 仍保持 0.8 附近）

### 本地檔案索引
| 檔案 | 路徑 | 大小 |
|------|------|------|
| v6.11 Notebook | `/app/twstock-grpo-regime-aware-factor-training-v6-11.ipynb` | 88861 bytes |
| v6.10 下載來源 | `/tmp/v610_download/twstock-grpo-regime-aware-factor-training-v6-9.ipynb` | 73789 bytes |
| Push metadata | `/tmp/v611_metadata.json` | 546 bytes |
| Push 目錄 | `/tmp/kpush_v611/` | - |

### v6.10 訓練結果診斷（v6.11 改版依據）

**4-Regime 結果摘要:**

| Regime | Best Formula | Train IC | Val IC | IC Gap | 問題 |
|--------|-------------|----------|--------|--------|------|
| TRADITIONAL | LIQ_SCORE | 0.045 | 0.024 | 0.021 | IC 弱 |
| LARGE_CAP | LIQ_SCORE | 0.051 | -0.012 | 0.063 | val_IC 負值! |
| MID_CAP_TECH | SP500_CLOSE | 0.035 | 0.019 | 0.016 | IC 弱 + 退化 |
| FINANCIAL | CLOSE_POS | 0.028 | 0.015 | 0.013 | IC 最弱 |

**6 大核心問題:**
1. P0: IC 在 step 1000 後停滯，後續 14000 steps 幾乎無改善
2. P1: 因子全為單一特徵（1-2 tokens），缺乏運算符組合
3. P2: LARGE_CAP val_IC 負值（-0.012），完全無泛化能力
4. P3: MID_CAP_TECH IC 持續退化，group_size=12 太小
5. P4: temperature 衰減過快（step 5000 已到 0.5），後期探索不足
6. P5: 無 early stopping，GPU 時間浪費
