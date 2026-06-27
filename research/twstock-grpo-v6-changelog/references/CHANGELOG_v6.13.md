# TWStock GRPO v6.13 - Complexity Reward Fix + Comprehensive Param Tuning

## 版本: v6.13 (2026-06-12)

## 核心問題修復

### P0: Complexity Reward 完全失效
**症狀**: 所有 regime `best_ops=0, best_len=1` — 公式退化為單一 feature token

**根因**: `_default_backtest` 回傳 `float`（僅含 ic/sharpe/mdd/turnover），完全不含 complexity 權重計算。`compute_group_rewards` 中雖有 `operator_bonus` 和 `short_formula_penalty`，但：
- `operator_bonus=0.3` 太弱，0 operators 時加成=0，無法對抗 base reward 的負值
- `short_formula_penalty=1.0` 太弱，短公式僅懲罰 1.0/2.0/3.0 點

**根因**: v6.12 `reward_weights` 中 `complexity=0.25`，但 `_default_backtest` 只回傳 combined float，complexity 權重未被使用（應為 v6.13 設計 but v6.12實作遺漏）。

**修復**:
1. `_default_backtest` 回傳 `dict`（含各項 reward 分量及 `complexity_comp`）
2. `compute_group_rewards` 分離計算 base_reward + complexity_reward，完整應用 `reward_weights["complexity"]`
3. 新增 `complexity_comp = (operator_bonus + length_bonus + simplicity_bonus)` 量化公式複雜度
4. `operator_bonus` 從 0.3 → **1.0`**（0 operators 時無加成、1 operator 時 +1.0）
5. `short_formula_penalty` 從 1.0 → **3.0**（短公式強烈懲罰）
6. **新增 v6.13 debug print**: 每 step 印出 operator count、length、complexity_bonus 數值
7. **新增 v6.13 formula summary**: 每 200 step 印出 best formula 結構（operators + length + val_IC）

### P0: Base Reward 系統性偏負
**症狀**: 全部 best_r 為負值（-1.7 ~ -1.9），但 val_IC 為正

**根因**: 多目標 reward 縮放過激 — IC×10 + Sharpe×5 + MDD_penalty + Turnover_penalty，導致整體 reward 很容易被 MDD 和 turnover 拉負。

**修復**:
- IC縮放: 10 → **5**
- Sharpe縮放: 5 → **2**
- `reward_weights`: ic=0.40→0.50, complexity=0.25→0.35
- 新增 `reward_weights[7]` 權重驗證

### P1: Early Stop 過早觸發
**修復**:
- `warmup`: 1500 → **2000**
- `patience`: 800 → **1200**
- val_IC 需提升 > 1e-3 才不算停滯（min_delta: 5e-4 → 1e-3）

### P1: Group Size 過小
**修復**:
- `traditional`: 16 → **32**
- `financial`: 16 → **32**
- CPU floor: 最小 16 → **最小 32**（GPU 模式不受影響）
- 動態 group_size縮小: 下限維持 8（Rank-Based已穩定，不過度縮小）

## 參數彙總 (v6.13 vs v6.12)

| 參數 | v6.12 | v6.13 | 變化 |
|------|-------|-------|------|
| `operator_bonus` | 0.3 | **1.0** | +0.7 |
| `short_formula_penalty` | 1.0 | **3.0** | +2.0 |
| `min_formula_len` | 3 | **3** | 不變 |
| `reward_weights["ic"]` | 0.40 | **0.50** | +0.10 |
| `reward_weights["sharpe"]` | 0.20 | **0.20** | 不變 |
| `reward_weights["mdd"]` | 0.10 | **0.05** | -0.05 |
| `reward_weights["turnover"]` | 0.05 | **0.05** | 不變 |
| `reward_weights["complexity"]` | 0.25 | **0.35** | +0.10 |
| `IC縮放` | IC×10 | **IC×5** | 降低 |
| `Sharpe縮放` | Sharpe×5 | **Sharpe×2** | 降低 |
| `traditional group_size` | 16 | **32** | +16 |
| `financial group_size` | 16 | **32** | +16 |
| `early_stop_warmup` | 1500 | **2000** | +500 |
| `early_stop_patience` | 800 | **1200** | +400 |
| `early_stop_min_delta` | 5e-4 | **1e-3** | +5e-4 |

## 預期效果

- **Complexity reward 生效**: 1 operator 即可獲得 +1.0 base + 0.35 weighted = +1.35 加成
- **Base reward 不再過負**: IC×5 + Sharpe×2 + 降低的 MDD penalty，預期 combined 維持在 [-1, +3] 範圍
- **公式長度 > 1**: min_formula_len=3 + penalty=3.0 強烈懲罰短公式
- **Early stop 更穩**: 更多 warmup + patience，允許更充分探索
- **Group size 足夠**: 32 組在 GPU 上 不會 導致 collapse（Rank-Based 已穩定）
