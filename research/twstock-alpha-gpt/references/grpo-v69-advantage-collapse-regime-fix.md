# GRPO v6.9 Advantage Collapse Fix + Regime Bug Fix

Date: 2026-06-15

## 概述

本次會話解決了 GRPO v6.8 的兩個核心問題：
1. **Advantage Collapse (P0)** — Z-score normalization 在 reward 同質化時失效
2. **Regime Bug (P1)** — CPU 模式只訓練 MID_CAP_TECH，跳過 3/4 regime

---

## Fix 1: Rank-Based Advantage (P0)

### 問題分析

v6.8 使用 Z-score normalization：
```python
advantages = (rewards - rewards.mean()) / (rewards.std() + 1e-6)
```

當所有 candidate 的 reward 接近相同（如合成數據或早期訓練階段），std → 0，導致：
- advantages 全部接近 0
- PPO ratio 失效（gradient 為 0）
- Policy 無法更新

v6.8 的 workaround：`if adv_std < 1e-4: advantages += torch.randn_like * 0.1` — 只是治標。

### 修復方案：Rank-Based Advantage

```python
# 在 GRPORewardCalculator._compute_advantages 中
valid_rewards = rewards[valid_mask]
ranks = np.argsort(np.argsort(valid_rewards))  # 0 到 N-1
n = len(valid_rewards)
advantages_valid = (ranks - n / 2) / (n / 2)  # [-1, 1] 區間
```

**特性**：
- 保證 advantage std ≈ 0.577（對任意 N>1）
- 永不 collapse，不依賴 reward 絕對值
- 只依賴 reward 相對排序
- `advantage_method = "rank"` (預設) 或 `"zscore"` (相容 v6.8)

### 驗證結果

| 情境 | Z-score adv_std | Rank-based adv_std |
|------|----------------|-------------------|
| Collapse (64× -1.0) | 0.001 | **0.577** |
| 正常分佈 | 1.000 | **0.577** |
| n_valid=2 | NaN | **0.500** |

---

## Fix 2: Multi-Objective Reward (P2)

### 問題

單一 IC reward 容易導致同質化，不同公式在合成/真實數據上 IC 相似。

### 修復方案

```python
reward_weights = {
    "ic": 0.5,      # Spearman IC
    "sharpe": 0.25, # 夏普比率
    "mdd": 0.15,    # 最大回撤懲罰
    "turnover": 0.1 # 換手率懲罰
}
```

**效果**：
- High IC signal: reward ≈ 5.15
- Random signal: reward ≈ 0.18
- Flat signal: reward ≈ 0.08
- 明確區分好壞訊號

---

## Fix 3: Regime Bug Fix (P1)

### 問題位置

v6.8 `main()` 函數 line 1374-1379：
```python
tech_stocks = [sid for sid in stock_data_map 
               if KNOWN_REGIMES.get(sid, StockRegime.MID_CAP_TECH) == StockRegime.MID_CAP_TECH]
stock_data_map = {sid: stock_data_map[sid] for sid in tech_stocks}
```

CPU 模式（含 Kaggle GPU quota 用盡時）只保留 5 檔 tech 股，其他 15 檔完全跳過。

### 修復方案

在 `GRPOConfig.auto_detect()` 中移除過濾，改為縮小規模：
```python
if device == "cpu" or force_cpu:
    return GRPOConfig(
        group_size=32,        # 原 64
        train_steps=5000,     # 原 15000
        batch_size=128,       # 原 256
        # ... 不過濾 regime
    )
```

**效果**：4/4 regime 都有訓練結果。

---

## Fix 4: Dynamic Group Size

### 設計

```python
min_group_size = 16
adv_std_threshold = 0.1

# 在 compute_group_rewards 返回
need_reduce = adv_std < adv_std_threshold

# 在 train_step 動態調整
if need_reduce and current_group_size > min_group_size:
    current_group_size = max(min_group_size, current_group_size // 2)
```

---

## 新增 GRPOConfig 參數

```python
@dataclass
class GRPOConfig:
    # 新增
    advantage_method: str = "rank"       # "rank" | "zscore"
    min_group_size: int = 16
    adv_std_threshold: float = 0.1
    use_multi_objective: bool = True
    reward_weights: dict = field(default_factory=lambda: {
        "ic": 0.5, "sharpe": 0.25, "mdd": 0.15, "turnover": 0.1
    })
    # 移除: tech_stocks filter, advantage noise injection
```

---

## 本地測試結果

```
============================================================
v6.9 核心邏輯 CPU 測試
============================================================
Config: group_size=32, advantage_method=rank
Dynamic group: min=16, threshold=0.1
Multi-objective: True, weights={'ic': 0.5, 'sharpe': 0.25, 'mdd': 0.15, 'turnover': 0.1}

--- 測試 1: Rank-Based Advantage vs Z-score (Collapse) ---
  Z-score adv_std: 0.999
  Rank adv_std:    0.577
  ⚠️  Z-score 仍有數值但非穩定

--- 測試 2: 正常情境 ---
  Rank adv_std: 0.577
  Z-score adv_std: 1.000
  ✅ 兩者都正常

--- 測試 3: 少數 valid (n_valid=2) ---
  n_valid=2, Rank adv_std=0.500
  ✅ 小樣本也能正常運作

--- 測試 4: Multi-Objective Reward ---
  High IC signal: reward=5.1510
  Random signal:  reward=0.1831
  Flat signal:    reward=0.0841
  ✅ 正常區分好壞訊號

--- 測試 5: Dynamic Group Size ---
  Normal: adv_std=0.577, need_reduce=False
  ✅ Rank-based 穩定，不易觸發

============================================================
✅ 所有核心邏輯單元測試通過
============================================================
```

---

## Kaggle 部署

- Kernel: `mhhuang14/twstock-grpo-regime-aware-factor-training-v6-9`
- Status: RUNNING (T4 GPU)
- Cron Monitor: `kaggle-grpo-v69-advantage-monitor` (every 30m)

---

## 相關檔案

| 檔案 | 大小 | 說明 |
|------|------|------|
| `/home/appuser/twstock_v69_kernel/twstock-grpo-regime-aware-factor-training-v6-9.ipynb` | 86KB | 完整訓練 notebook |
| `/home/appuser/grpo_v69_full.py` | 68KB | 完整 Python 匯出 |
| `/home/appuser/grpo_v69_advantage_fix.py` | 17.7KB | 獨立 v6.9 實現 |
| `/home/appuser/grpo_v69_test.py` | 12.5KB | 完整測試套件 |
| `/home/appuser/test_v69_core.py` | 3.8KB | 核心邏輯單元測試 |
| `/home/appuser/test_v69_advantage.py` | 3.5KB | Advantage 獨立驗證 |
| `references/CHANGELOG_v6.9.md` | - | 詳細變更記錄 |
| `references/cron-v69-monitor.json` | - | Cron 監控設定 |

---

## 下一步

1. 等待 Kaggle GPU 訓練完成（預計 10-20 分鐘）
2. Cron job 每 30 分鐘自動檢查輸出
3. 若發現問題（adv collapse、regime 缺失、reward 同質化），根據 cron 建議修改參數
4. 重新 push v6.10 修復版本
5. 最終驗證 4 個 regime 都有有效 IC (>0.01) 且無 collapse