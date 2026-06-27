# GRPO v6.1/v6.2 Regime Bugs Found (2026-06-14)

## Context
Analyzed `grpo-regime-aware-factor-training-v6-1.ipynb` (docstring claims v6.2, filename v6-1) in `/home/appuser/twstock_kernel/` and `/home/appuser/kaggle_kernel/`. This is the latest available version (Kaggle has v5.9, no v6.8 exists despite internal version strings claiming v6.7/v6.8).

## Bug 1: KNOWN_REGIMES Incomplete — SMALL_CAP Never Assigned

**Location**: `KNOWN_REGIMES` dict (around line 6274)

**Problem**: `StockRegime` enum defines 5 regimes:
```python
class StockRegime(Enum):
    LARGE_CAP = "large_cap"
    MID_CAP_TECH = "mid_cap_tech"
    SMALL_CAP = "small_cap"
    TRADITIONAL = "traditional"
    FINANCIAL = "financial"
```

But `KNOWN_REGIMES` only maps stocks to 4 regimes (LARGE_CAP, MID_CAP_TECH, TRADITIONAL, FINANCIAL). `SMALL_CAP` is never assigned to any stock.

**Impact**: 
- 20 stocks → 4 regimes, so some regimes have 5-6 stocks, others 3-4
- SMALL_CAP regime has 0 stocks → never trained, wasted model capacity
- Regime distribution imbalance affects group-level advantage normalization

**Fix**: Define `KNOWN_REGIMES` for all 20 tickers, ensuring each of 5 regimes gets ~4 stocks.

```python
KNOWN_REGIMES = {
    # LARGE_CAP (4 stocks)
    "2330": StockRegime.LARGE_CAP,   # 台積電
    "2308": StockRegime.LARGE_CAP,   # 大聯大
    "2412": StockRegime.LARGE_CAP,   # 中華電
    "1303": StockRegime.LARGE_CAP,   # 台塑
    # MID_CAP_TECH (4 stocks)
    "2454": StockRegime.MID_CAP_TECH, # 聯發科
    "3008": StockRegime.MID_CAP_TECH, # 大立光
    "3034": StockRegime.MID_CAP_TECH, # 聯詠
    "3711": StockRegime.MID_CAP_TECH, # 日月光 (已除牌，需替換)
    # SMALL_CAP (4 stocks)
    "2382": StockRegime.SMALL_CAP,   # 廣達
    "2303": StockRegime.SMALL_CAP,   # 聯電
    "1301": StockRegime.SMALL_CAP,   # 台塑化
    "1326": StockRegime.SMALL_CAP,   # 台化
    # TRADITIONAL (4 stocks)
    "1101": StockRegime.TRADITIONAL, # 台泥
    "2002": StockRegime.TRADITIONAL, # 中鋼
    "2882": StockRegime.TRADITIONAL, # 國泰金
    "2886": StockRegime.TRADITIONAL, # 兆豐金
    # FINANCIAL (4 stocks)
    "2891": StockRegime.FINANCIAL,   # 中信金
    "2884": StockRegime.FINANCIAL,   # 玉山金
    "2881": StockRegime.FINANCIAL,   # 富邦金
    "4938": StockRegime.FINANCIAL,   # 和碩 (替換 3711)
}
```

Note: 2311 (日月光) delisted — replace with 4938 (和碩) or similar.

## Bug 2: Reward Function Not Regime-Aware

**Location**: `GRPORewardCalculator.compute_rewards()` (around line ~60086)

**Problem**: 
```python
def compute_rewards(self, preds: np.ndarray, returns: np.ndarray) -> np.ndarray:
    # Computes Spearman IC across ALL stocks in batch
    ic = spearman_corr(preds, returns)
    # ... Sharpe, Turnover
    return reward
```

Computes single IC across mixed regimes. Different regimes have different return distributions (financials low vol, tech high vol). Cross-regime IC is meaningless — a formula good for tech may look bad on financials.

**Impact**: Reward signal polluted, GRPO cannot learn regime-specific patterns.

**Fix**: Compute rewards **per regime**, then normalize within regime:
```python
def compute_rewards_regime_aware(self, preds, returns, regime_labels):
    rewards = np.zeros_like(preds)
    for regime in unique(regime_labels):
        mask = regime_labels == regime
        if mask.sum() < 2: continue
        regime_ic = spearman_corr(preds[mask], returns[mask])
        regime_sharpe = compute_sharpe(returns[mask])
        # normalize within regime
        rewards[mask] = (regime_ic + regime_sharpe * 0.1) * 10
    return rewards
```

## Bug 3: Advantage Collapse Risk — group_size=64 Without Baseline

**Location**: `GRPOConfig` (group_size=64, entropy_coef=0.15) + training loop

**Problem**: 
- `group_size=64` candidates per step
- No group-level baseline subtraction (advantage = raw reward)
- `entropy_coef=0.15` too high → encourages random exploration over exploitation
- When rewards are similar (common in early training or homogeneous data), std ≈ 0 → advantage ≈ 0 → gradient vanishes

**Impact**: Structural collapse to single-token formulas (observed in v5.9), or no learning.

**Fix** (from v6.0 patterns):
1. Reduce `group_size=32` (CPU) or `16` (GPU)
2. Add group-level baseline: `advantage = (reward - reward.mean()) / (reward.std() + 1e-8)`
3. Reduce `entropy_coef=0.05`
4. Add rank-based fallback when `std < 0.01`: `advantage = linspace(-1, 1, G)[rank]`

## Bug 4: Data Path Hardcoded for Kaggle Mount

**Location**: `main()` function, `data_path` variable

**Problem**: 
```python
data_path = "/kaggle/input/twstock-v6-0-real-data-20stocks-5y/"
```
Assumes dataset mounted at specific path. Fails locally where data is at `/home/appuser/twstock_v6_data/` or `/home/appuser/twstock_kernel_out/twstock_v6_data/`.

**Fix**: Use auto-scan pattern (already in `adapt_finmind_data` v6.2+):
```python
def find_data_path():
    candidates = [
        "/kaggle/input/twstock-v6-0-real-data-20stocks-5y/",
        "/home/appuser/twstock_v6_data/",
        "/home/appuser/twstock_kernel_out/twstock_v6_data/",
    ]
    for p in candidates:
        if os.path.exists(p) and any(f.endswith('.csv') for f in os.listdir(p)):
            return p
    raise FileNotFoundError("No data path found")
```

## Files to Fix
- `/home/appuser/twstock_kernel/grpo-regime-aware-factor-training-v6-1.ipynb` (primary)
- `/home/appuser/kaggle_kernel/grpo-regime-aware-factor-training-v6-1.ipynb` (copy)
- Any derived training scripts

## Next Version
Create **v6.3** (filename `v6-3.ipynb`, internal "v6.3", metadata id `...-v6-3`) with all 4 fixes.