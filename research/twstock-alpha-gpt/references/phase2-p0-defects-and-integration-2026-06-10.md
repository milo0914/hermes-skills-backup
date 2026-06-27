# Phase2 P0 Defects & Training Results Integration

Date: 2026-06-10

## P0 Defects in phase2_alpha_refine (ai_dig_money_core.py)

### E1: Import Non-existent Module (L837, L892)

```python
# L837 — ImportError at runtime
from grpo_alpha_trainer import GRPOAlphaTrainer, GRPOConfig

# L892 — Same issue
from grpo_alpha_trainer import FormulaDecoder
```

`grpo_alpha_trainer` 模組不存在於 Python path。即使存在，其 VOCAB_SIZE=28 (16 features) 與 ai_dig_money_core.py 的 VOCAB_SIZE=34 (22 features) 不匹配，推論會崩潰。

**修復策略 — 雙路徑設計**：

1. **路徑 A (優先): 載入 Kaggle 訓練結果做推論**
   - 讀取 `scripts/best_strategy.json`（由 `integrate_training_results.py` 從 Kaggle output 轉換而來）
   - 用本地 `FormulaDecoder`（已在 ai_dig_money_core.py L377 定義）解碼 token 序列
   - 用 feature_df 中的 22 因子值計算公式分數（StackVM 執行）
   - 此路徑不需要本地 GRPO 訓練能力

2. **路徑 B (後續): 本地內聯 GRPO 訓練**
   - 從 Kaggle grpo_regime_training_kaggle.py 提取核心類別（StackVM, LoopedTransformer, GRPORewardCalculator, train_torch_regime）
   - 內聯到 ai_dig_money_core.py（約 900 行額外代碼）
   - 僅在需要本地訓練時啟用（有 GPU 或接受 CPU 慢速）

### E2: Random Returns (L877)

```python
# L877 — 訓練目標為隨機噪聲，GRPO 訓練無意義
returns = np.random.randn(feat_tensor.shape[1]).astype(np.float32) * 0.02
```

**修復**: 改用 close 價計算真實前向報酬：

```python
if close is not None and len(close) > horizon:
    returns = np.diff(close[horizon:], prepend=close[horizon]) / (close[:-horizon] + 1e-6)
    returns = returns[:feat_tensor.shape[1]].astype(np.float32)
else:
    returns = np.zeros(feat_tensor.shape[1], dtype=np.float32)
```

其中 `horizon` 按 regime 設定：LARGE_CAP=5, MID_CAP_TECH=3, TRADITIONAL=5, FINANCIAL=7

### E3: FormulaDecoder Already Exists Locally

L892 `from grpo_alpha_trainer import FormulaDecoder` — 但 FormulaDecoder 已在 ai_dig_money_core.py L377-430 定義，使用 ALL_FEATURE_NAMES (22因子)。只需移除 import，改用本地定義即可。

## Training Results Integration Workflow

### Pipeline

```
Kaggle Kernel (v5.4) COMPLETE
  → kaggle kernels output ... -p /tmp/kaggle-output-v54/
  → python3 scripts/integrate_training_results.py /tmp/kaggle-output-v54/
  → scripts/best_strategy.json (本地推論用)
  → scripts/training_report.json (摘要報告)
  → references/v54-best_strategy_per_regime.json (歸檔)
```

### best_strategy.json 格式

```json
{
  "regimes": {
    "LARGE_CAP": {
      "formula_tokens": [0, 22, 6],
      "formula_str": "ADD(RET, INST_FLOW)",
      "ic": 0.15,
      "reward": 2.5,
      "train_steps": 20000
    }
  },
  "metadata": {
    "trained_at": "2026-06-10T...",
    "kernel_slug": "mhhuang14/grpo-regime-aware-factor-training-v5-4",
    "vocab_size": 34,
    "n_features": 22,
    "all_feature_names": ["RET", "LIQ_SCORE", ...]
  }
}
```

### Validation Checks

1. VOCAB_SIZE == 34 (22 features + 12 operators)
2. N_FEATURES == 22
3. All 4 regimes present (LARGE_CAP, MID_CAP_TECH, TRADITIONAL, FINANCIAL)
4. Every regime has non-empty formula_tokens

## Real Data Pipeline (TODO #15)

```
fetch_real_data_kaggle.py (Kaggle kernel, internet=True, GPU=False)
  → twstock: 11 stocks × 6 months OHLCV
  → FinMind: 期貨法人OI (TX/MTX)
  → yfinance: ^GSPC, ^DJI, ^IXIC
  → Kaggle Dataset: mhhuang14/twstock-grpo-real-training-data
  → 訓練 kernel dataset_sources 引用此 Dataset
  → 重新推送訓練 kernel → 22 因子全部非零
```

注意事項：
- FinMind institutional_investors 欄位是中文（外資/投信/自營商），非英文
- yfinance 回傳美東日期，需注意與台股日期時差
- Kaggle Dataset 掛載為三層巢狀 `/kaggle/input/datasets/{owner}/{slug}/{files}`，訓練腳本需 os.walk 遞迴搜尋
