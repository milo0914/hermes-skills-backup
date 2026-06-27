# Kaggle GRPO 訓練已知問題與修復 (2026-06)

## GPU 訓練只跑 1 個 regime (v5.1/v5.4)

**現象**: v5.1 和 v5.4 kernel 只訓練了 mid_cap_tech (2882)，其他 3 檔 (2330/2454/1301) 未出現在 regime 分類中。v4 (CPU) 成功訓練全部 4 regime。

**可能原因**:
- 合成數據的 regime 分類邏輯有 bug
- group_size 過濾條件太嚴格（每個 regime 需要最少樣本數）
- 數據載入後只有 2882 符合 mid_cap_tech 的分類標準

**修復方向**: 檢查 `assign_regime()` 邏輯，確認 4 檔股票都正確分類；降低 group_size 門檻或為小 regime 降級處理。

## loss=-0.0000 格式掩蓋問題

**現象**: PPO 和 REINFORCE 版本的 log 都顯示 `loss=-0.0000`。

**原因**: 訓練 log 使用 `.4f` 格式，微小的 gradient 被截斷為 0。

**區分方法**:
- PPO: `clip_ratio=50.0%` 表示有梯度 clipping 發生
- REINFORCE: 有 `baseline=X.XXX` 欄位，PPO 沒有

**建議**: log 格式改為 `.6f` 或 `.2e`（科學記號）。

## best_reward 早期收斂

**現象**: v5.1 REINFORCE 在 step 500 後 best_reward 就不再改善 (1.373)，後續 9500 步為浪費。

**建議**: 加入 early stopping — best_reward 連續 N 步（建議 2000）無改善時停止。

## phase2_alpha_refine 三層 fallback 架構 (v3.2)

```
路徑1: try import grpo_alpha_trainer → GPU 本地 GRPO 訓練
路徑2: 載入 best_strategy_per_regime.json → per-regime 公式 + val_ic
路徑3: feature_df 最近 20 日均值作為 alpha 信號
```

**搜尋路徑**: `./best_strategy_per_regime.json` → `scripts/` → `/tmp/kaggle-output-v51/` → `/tmp/grpo_v4_results/`

**phase1_result 必要格式** (phase2_alpha_refine 輸入):
```python
{
    "candidate_pool": ["2330", "2454", ...],  # list of stock_ids
    "s2_passed": {"2330": 65.0, "2454": 55.0, ...},  # stock_id -> stage2 score
}
```

## alpha_bonus 映射 [UNCALIBRATED]

`alpha_bonus = np.clip(alpha_s * 10, -20, 20)` — 待累積多週期訓練數據後整體校準。用戶指示暫不校準。

## 訓練結果摘要 (截至 2026-06-10)

| Regime | 公式 | Train IC | Val IC | 來源 |
|:---|:---|:---|:---|:---|
| traditional (1301) | LIQ_SCORE | 0.1900 | 0.3731 | v4 CPU |
| large_cap (2330) | LIQ_SCORE | 0.1800 | 0.2533 | v4 CPU |
| mid_cap_tech (2882) | SP500_CLOSE | 0.1373 | 0.1816 | v5.1 GPU |
| financial (1301) | CLOSE_POS | 0.0000 | 0.0000 | v4 CPU (最弱) |
