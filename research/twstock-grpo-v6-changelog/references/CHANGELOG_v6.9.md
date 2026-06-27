# GRPO v6.9 Changelog
Date: 2026-06-15 00:57

## v6.9 — Rank-Based Advantage + Multi-Objective Reward + Regime Fix

### Fix 1: Rank-Based Advantage (P0 — Advantage Collapse)
- **問題**: Z-score normalization 在所有 reward 近似時 std→0，導致 advantage collapse
- **修復**: 用排名歸一化取代 Z-score
  - `advantages = (ranks - N/2) / (N/2)` → 保證 std≈0.577
  - `advantage_method = "rank"` (預設) 或 `"zscore"` (相容 v6.8)
- **驗證**: 64 個 reward 全部 ≈-1.0 時，Rank std=0.577 vs Z-score std=0.001

### Fix 2: Multi-Objective Reward
- **問題**: 單一 IC reward 容易 homogenization
- **修復**: 加權組合 4 個 reward 維度
  - IC (0.5) + Sharpe (0.25) + MDD penalty (0.15) + Turnover penalty (0.1)
- **新增**: `use_multi_objective=True` (預設)，`reward_weights` dict

### Fix 3: Regime Bug Fix
- **問題**: CPU 模式只訓練 MID_CAP_TECH (5 檔)，3/4 regime 被跳過
- **修復**: `auto_detect` CPU 模式不過濾 regime，改為縮小規模
  - group_size=32, train_steps=5000, batch_size=128

### Fix 4: Dynamic Group Size
- **問題**: group_size 太大導致 reward 同質性高
- **修復**: adv_std < 0.1 時自動縮小 group_size (min=16)
  - `need_reduce_group` flag 由 compute_group_rewards 返回
  - train_step 動態調整 current_group_size

### 新增 GRPOConfig 參數
- `advantage_method: str = "rank"`
- `min_group_size: int = 16`
- `adv_std_threshold: float = 0.1`
- `reward_weights: dict = {"ic": 0.5, "sharpe": 0.25, "mdd": 0.15, "turnover": 0.1}`
- `use_multi_objective: bool = True`

### 移除
- tech_stocks 過濾 (v6.1 CPU mode bug)
- advantage 噪聲注入 (v5.9/v6.5 band-aid fix)
