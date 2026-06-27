# 三版差異分析: 用戶版 vs Kaggle v3.5 vs 本地版

日期: 2026-06-09
來源: 用戶提供 ipynb from milo0914/aidigmoney (commit 55b8d69)

## 三版檔案

| 版本 | 檔案 | 行數 | 定位 |
|------|------|------|------|
| 用戶版 | `/tmp/user_version.py` (from ipynb) | 883 | 純 GRPO 訓練 (精簡修復版) |
| Kaggle v3.5 | `grpo_regime_training_kaggle_v35.py` | 2207 | 純 GRPO 訓練 (完整+監控) |
| 本地版 | `ai_dig_money_core.py` | 1913 | 完整篩選管線 (Stage1-4) |

## 共同基礎 (三版一致)

- FEATURE_NAMES: 22 因子 (含 v3.1 期貨OI+美股)
- VOCAB_SIZE: 34 (22 features + 12 operators)
- StackVM + StackVMState 引導式解碼
- GRPOConfig dataclass
- RegimeConfig + RegimeTrainingPlan
- robust_normalize (MAD)
- TWFeatureEngineer.compute_features
- decode_formula
- walk_forward_validation

## 用戶版優於 v3.5 的改進

### S1. Data Leakage 修復 (L770-788)
`train_all_regimes()` 按每檔股票獨立做 80/20 時間切割，再合併 train/val 集合。
v3.5 沒有驗證集切割，只在 compute_group_rewards 裡用 val_ic=0。

### S2. MTPHead 啟用 (L524-535, L554-556)
啟用了 3-pool fusion (mean+max+first + gating)。
v3.5 只用 mean pooling + 單獨 linear head。MTPHead 更有表達力。

### S3. Entropy 計算修復 (L724-727)
收集每條路徑的真實 entropy 並加總，保持梯度連接。
v3.5 用 detached no_grad 單獨計算 entropy（不參與梯度），削弱探索。

### S4. 精簡化
883 行 vs 2207 行，去掉了 generate_synthetic_data() / Kaggle dataset loading / JSON 儲存等。

## v3.5 優於用戶版的改進

### S5. REINFORCE Loss (L1515-1522)
v3.5 修了 PPO ratio≡1 零收斂 bug。
用戶版仍用 PPO clipped surrogate (L720-722):
```python
ratio = exp(log_probs - log_probs.detach())  # ≡ 1.0
loss = -min(ratio * adv, clipped * adv).mean()  # ≡ -adv.mean() ≡ 0
```
這是最嚴重的 bug — 模型不會收斂。

### S6. NaN Guard (L1544-1563)
v3.5 有 step-level NaN skip + param-level reinit。
用戶版完全沒有 NaN 保護。

### S7. _compute_ic 獨立計算
v3.5 的 _compute_ic 回傳 array（每公式獨立 IC）。
用戶版 _compute_ic_array 也有，但 reward calculator 裡 train_ic[i] 取值邏輯不同。

## 兩版共同缺失

### S8. TWFeatureEngineer 4個因子恆為0
用戶版 L320: `for f in ["TX_MTX_SPREAD", "NASDAQ_CLOSE", "SP500_CLOSE", "DOWJONES_CLOSE"]: g[f] = 0`
v3.5 也只計算了 TX_MTX_SPREAD 但美股也是0。
修復: TX_MTX_SPREAD = TX_INST_NET_OI - MTX_RETAIL_OI; 美股 merge us_indices_df

## 本地版獨有問題 (vs 兩個訓練版)

### E3: import 不存在的模組
L837 `from grpo_alpha_trainer import GRPOAlphaTrainer, GRPOConfig` — 模組不存在

### E4: 隨機 returns
L877 `np.random.randn() * 0.02` — 訓練出的公式毫無意義

### E12: feature_df 缺 close
compute_features 只輸出 date+stock_id+22因子，phase2 需要 close 算前向報酬

## 綜合版 TODO (排序)

### Phase A: Critical Bug (訓練收斂阻塞)
1. [E1] REINFORCE Loss 替換 PPO — 用戶版 PPO ratio≡1, loss≡0
2. [E2] NaN Guard 移植 — step-level skip + param-level reinit
3. [E3] 本地版 phase2 內聯 GRPO — 移除 import 不存在模組
4. [E4] 本地版 returns 修正 — 真實前向報酬替代隨機
5. [E5] TX_MTX_SPREAD 計算 — = TX_INST_NET_OI - MTX_RETAIL_OI
6. [E6] 美股指數因子計算 — merge us_indices_df

### Phase B: 架構改進 (訓練品質)
7. [E10] Data Leakage 防護 — 用戶版 per-stock 80/20 時間切割
8. [E11] MTPHead 啟用 — 用戶版 3-pool fusion
9. [E16] Entropy 梯度連接 — 用戶版真實路徑 entropy
10. [E9] RegimeConfig 22維權重 — 補6個v3.1因子權重

### Phase C: 驗證框架
11. [E7] Walk-Forward 移植到本地版
12. [E8] robust_normalize 移植到本地版
13. [E12] feature_df 保留 close
14. [E13] Kaggle 整合 main() — 保留 dataset loading

### Phase D: 運維
15. [E14] GitHubLogPusher 完整版
16. [E18] LoRD decay 抽方法
17. [E17] GPU capability sm_50 放寬
18. [E15] StableRankMonitor 精簡版
19. 三版統一為一個綜合版

## 用戶版特定代碼位置 (883行)

| 區塊 | 行號 | 說明 |
|------|------|------|
| check_environment | L19-47 | sm_70 閾值 |
| FEATURE_NAMES | L53-59 | 22 因子 |
| StackVM | L75-126 | execute + unary/binary/ternary |
| StackVMState | L132-169 | 引導式解碼 |
| StockRegime + KNOWN_REGIMES | L175-189 | 4 股性 |
| RegimeConfig | L192-210 | 16維權重 (缺v3.1) |
| RegimeTrainingPlan | L212-226 | create_plan |
| robust_normalize | L232-251 | MAD |
| TWFeatureEngineer | L253-353 | compute_features (L320: 4因子=0) |
| GRPOConfig | L359-401 | auto_detect |
| GitHubLogPusher | L403-407 | stub |
| GRPORewardCalculator | L413-478 | per-formula IC gap |
| build_looped_transformer | L484-558 | RMSNorm/SwiGLU/QKNorm/MTPHead/LoopedTransformer |
| StableRankMonitor | L564-584 | 精簡版 |
| GRPOAlphaTrainer | L586-804 | train_torch_regime + train_all_regimes |
| decode_formula | L810-823 | |
| walk_forward_validation | L825-844 | |
| main | L846-884 | 合成數據 standalone |
