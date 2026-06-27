# GRPO v6.13 -- 重要回歸: Complexity Reward 結構錯誤診斷與修正範本

## 問題摘要

v6.12 看似加入了 `operator_bonus` 和 `short_formula_penalty`，實際上 **formula 長度全部退化為 1**，`best_ops=0`  across all regimes。

## 根因分析

### Root Cause 1: `_default_backtest` 回傳 `float`

```python
# v6.12 錯誤寫法
combined = w["ic"] * (ic * 10) + w["sharpe"] * (sharpe * 5) + ...
return combined  # float only
```

`reward_weights["complexity"]=0.25` 被定義但從未在 `_default_backtest` 中使用。compute_group_rewards 中雖有
`n_operators * self.config.operator_bonus`，但 bonus value 僅 0.3 per operator，0 operator 時=0，完全無法對抗 base reward 的負值。

### Root Cause 2: operator_bonus / short_formula_penalty 權重過低

| 參數 | v6.12 | 效果 |
|------|-------|------|
| operator_bonus | 0.3 | 1 operator → +0.3（以 -1.5 base reward 而言杯水車薪） |
| short_formula_penalty | 1.0 | len=1 僀罰 2.0，但 base -1.5 + penalty -2.0 = -3.5 仍然是最不負的選擇 |

### Root Cause 3: reward_weights["complexity"] 未被使用

`reward_weights` dict 中 `complexity=0.25`，但 `_default_backtest` 只使用 `ic`、`sharpe`、`mdd`、`turnover` 四個 key。`complexity` 的 weight 完全被拋棄。

## v6.13 修正方案

### 修正 1: `_default_backtest` 回傳 `dict` (v6.13)

```python
def _default_backtest(self, signal, returns):
    ...
    ic = self._spearman_corr(sig, ret)
    sharpe = ...
    mdd = ...
    turnover = ...
    return {
        "ic_comp": ic,
        "sharpe_comp": sharpe,
        "mdd_comp": -mdd,  # penalty already built-in
        "turnover_comp": -turnover,
        "complexity_comp": 0.0,  # filled later in compute_group_rewards
    }
```

### 修正 2: `compute_group_rewards` 分離計算 (v6.13)

```python
def compute_group_rewards(...):
    for each formula:
        details = self._default_backtest(...)  # dict
        base_reward = (
            w["ic"] * details["ic_comp"] * 5 +         # IC ×5 (v6.13缩減)
            w["sharpe"] * details["sharpe_comp"] * 2 +   # Sharpe ×2
            w["mdd"] * details["mdd_comp"] +
            w["turnover"] * details["turnover_comp"]
        )
        complexity_r = (
            n_operators * self.config.operator_bonus +
            (-self.config.short_formula_penalty if len < min_len else 0)
        )
        total = base_reward + w["complexity"] * complexity_r
        rewards.append(total)
```

### 修正 3: 參數調升 (v6.13)

| 參數 | v6.12 | v6.13 |
|------|-------|-------|
| operator_bonus | 0.3 | **1.0** |
| short_formula_penalty | 1.0 | **3.0** |
| reward_weights["complexity"] | 0.25 | **0.35** |
| IC縮放 | ×10 | **×5** |
| Sharpe縮放 | ×5 | **×2** |
| MDD權重 | 0.10 | **0.05** |
| group_size (traditional) | 16 | **32** |
| group_size (financial) | 16 | **32** |
| early_stop_warmup | 1500 | **2000** |
| early_stop_patience | 800 | **1200** |

## 預期效果

1 operator * 1.0 bonus * 0.35 weight = **+0.35 total reward per operator**
加上 base_reward 不再過激（IC×5 + Sharpe×2 + MDD×0.05 + Turnover×0.05）
→ 1 operator 即可在 Rank-Based Advantage 中獲得正向排名，迫使 formula 長度 >1

## v6.13 新增的關鍵 debug print

```python
print(f"  [v6.13 DBG] ops={n_operators} len={len(tokens)} "
      f"base_r={base_reward:.3f} complexity_r={complexity_r:.3f} "
      f"weighted_total={total_reward:.3f}")
print(f"  [v6.13] best_r={best_reward:.4f} ops={best_n_ops} len={len(best_toks)} "
      f"val_ic={best_val_ic:.4f} formula={formula_repr}")
```

## 驗收標準

| 指標 | 失敗 (v6.12) | 合格 (v6.13) |
|------|-------------|-------------|
| `best_r` | -1.7 ~ -1.9 (全負) | > -0.5 (部分為正) |
| `best_ops` | 0 | > 0 |
| `best_len` | 1 | > 1 |
| `val_ic` | 0.08-0.15 | > 0.10 |
| Early stop | 2400-2600 step | >= 4000 step |
```
