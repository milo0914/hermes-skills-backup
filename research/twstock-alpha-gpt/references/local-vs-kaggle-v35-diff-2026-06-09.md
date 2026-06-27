# 本地版 vs Kaggle v3.5 差異分析 (2026-06-09)

## 比對版本
- 本地版: `ai_dig_money_core.py` (1913 行)
- Kaggle v3.5: `grpo_regime_training_kaggle_v35.py` (2207 行)

## 定位差異
| | 本地版 | Kaggle v3.5 |
|---|---|---|
| 定位 | 完整篩選管線 (Stage1-4 / Phase1-5) | 純 GRPO 訓練腳本 |
| GRPO 引擎 | `from grpo_alpha_trainer import` (外部模組，**不存在**) | 完整內聯 GRPOAlphaTrainer + GRPOConfig |
| 因子數 / VOCAB | 22 / 34 ✓ | 22 / 34 ✓ |

## CRITICAL — 上線阻塞 (Blocker)

### E1: Import 不存在的模組
- 位置: `ai_dig_money_core.py` L837 `from grpo_alpha_trainer import GRPOAlphaTrainer, GRPOConfig`
- 影響: 執行 phase2 必炸 ImportError
- 修復: 內聯 GRPOAlphaTrainer（從 Kaggle v3.5 移植）

### E2: 隨機 returns
- 位置: L877 `np.random.randn(...).astype(np.float32) * 0.02`
- 影響: 訓練出的公式毫無意義
- 修復: 改為按 regime reward_horizon 計算真實前向報酬（Kaggle v3.5 L2036-2041）

### E3: GRPOConfig 缺失
- 位置: phase2 用到 `GRPOConfig.auto_detect()`
- 修復: 移植 Kaggle v3.5 的 GRPOConfig dataclass

## HIGH — 功能缺失

### E4: RegimeConfig / RegimeTrainingPlan
- 本地版無法按股性分群訓練
- 參考: Kaggle v3.5 L261-353

### E5: walk_forward_validation
- 本地版無任何 out-of-sample 驗證機制
- 參考: Kaggle v3.5 L1895-1932

### E6: REINFORCE 修復
- PPO clipped surrogate 在 on-policy GRPO 中 ratio≡1 → loss≡0
- 改用 REINFORCE: `L = -mean(log_prob * advantage)`
- 參考: Kaggle v3.5 L1515-1522

### E7: NaN Guard
- 訓練可能 NaN 炸掉，需 step-level skip + param-level reinit
- 參考: Kaggle v3.5 L1544-1563

### E8: robust_normalize (MAD)
- zscore 對極端值敏感，MAD 更穩健
- 參考: Kaggle v3.5 L1822-1851

## MEDIUM — 品質提升

### E9: RegimeConfig.feature_weights 只有16維
- 缺6個v3.1因子權重（TX_INST_NET_OI, MTX_RETAIL_OI, TX_MTX_SPREAD, NASDAQ_CLOSE, SP500_CLOSE, DOWJONES_CLOSE）
- 需為每個 regime 定義這6個因子的權重

### E10: GitHubLogPusher
- Kaggle 訓練時可即時推送 log 到 GitHub 監控
- 參考: Kaggle v3.5 L843+

### E11: TWFeatureEngineer 重複
- Kaggle 版是 class method，本地版是獨立 function — 邏輯應一致

### E12: feature_df 不保證含 close
- compute_features 只輸出 date+stock_id+22因子，無 close
- phase2 L875 用到 `stock_feat["close"]` 會 KeyError
- 修復: compute_features 輸出保留 close 欄位或另行傳入

## 修復計畫

### Phase A: 上線前必須修復 (blocker)
1. [E1+E3] 內聯 GRPOAlphaTrainer + GRPOConfig — 從 Kaggle v3.5 移植 StackVM / StackVMState / GRPOConfig / GRPOAlphaTrainer / GRPORewardCalculator / StableRankMonitor
2. [E2] 修正 phase2 的 returns 計算 — 用 close 算真實前向報酬
3. [E6] 同步 REINFORCE 修復
4. [E7] 移植 NaN Guard
5. [E4] 移植 RegimeConfig + RegimeTrainingPlan

### Phase B: 驗證框架
6. [E5] 移植 walk_forward_validation
7. [E9] 更新 feature_weights 為 22 維
8. [E8] 移植 robust_normalize

### Phase C: 運維強化
9. [E10] 移植 GitHubLogPusher
10. [E12] compute_features 輸出保留 close
11. TWDataLoader.load_full() 真實資料源
12. Kaggle kernel 重新推送

### Phase D: 端到端測試
13. mock 資料跑通 `run_daily_scan(use_v3=True)` 全流程
14. Walk-Forward IC > 0 且 t-stat > 2.0 才能移除 [UNCALIBRATED]
15. Docker / systemd 配置
