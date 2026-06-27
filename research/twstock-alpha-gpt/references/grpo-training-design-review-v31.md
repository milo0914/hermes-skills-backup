# GRPO Training Design Review — v3.1/v3.3 Bug Analysis (2026-06-09)

Comprehensive code review of `grpo_regime_training_kaggle.py` (2191 lines) and `ai_dig_money_core.py` (1913 lines).

## Syntax Status

- `ai_dig_money_core.py` — SYNTAX OK, v3.1 integration complete
- `grpo_regime_training_kaggle.py` — SYNTAX FAIL @L1175 (QKNormAttention nested inside SwiGLU due to patch indentation corruption)

## ai_dig_money_core.py Integration Status (v3.1)

All integration points verified complete:

| Item | Lines | Status |
|------|-------|--------|
| ALL_FEATURE_NAMES = 22 | L62 | Done |
| N_FEATURES = 22 | L63 | Done |
| VOCAB_SIZE = 34 | L71 | Done |
| Stage1.filter(futures_oi_df, us_indices_df) | L218-230 | Done |
| V2Pipeline.run(futures_oi_df, us_indices_df) | L616-617 | Done |
| V2Pipeline.stage1.filter() call | L635-636 | Done |
| V3Pipeline.phase1_rough_filter(futures_oi_df, us_indices_df) | L745-746, L762 | Done |
| V3Pipeline.phase2_alpha_refine(futures_oi_df, us_indices_df) | L784-785, L839-855 | Done |
| V3Pipeline.run(futures_oi_df, us_indices_df) | L1260-1261, L1287-1294 | Done |
| compute_features(futures_oi_df, us_indices_df) | L1409-1410, L1524-1602 | Done |
| compute_features → keep_cols filter | L1640 | Done |
| compute_features → ALL_FEATURE_NAMES zscore | L1623-1637 | Done |
| run_daily_scan V3 path | L1893-1898 | Done |
| run_daily_scan V2 path | L1905-1907 | Done |

## Critical Bugs (P0 — Will Prevent Convergence)

### P0-1: GRPO Importance Sampling Formula Wrong

**File**: grpo_regime_training_kaggle.py L1519-1526

**Problem**: `_old_log_probs` stores log_probs from the **previous batch's different formulas**. When the new batch generates completely different formulas, `ratio = exp(log_π_new - log_π_old)` compares probabilities of different actions — mathematically meaningless. Produces extreme ratio values that destroy gradient stability.

**v3.3 partial fix**: L1521 has on-policy fallback `ratio = exp(log_probs_tensor - log_probs_tensor.detach())` which is correct (ratio=1.0 with valid gradient). But L1522-1526 still retain the broken off-policy path — when `self._old_log_probs` is non-empty (which it always is after step 1, due to L1549-1550), the wrong path executes.

**Fix**: Delete L1522-1526 and L1549-1550 (`_old_log_probs` storage). On-policy single-epoch GRPO only needs ratio=1.0 with valid gradient chain.

### P0-2: Entropy Bonus Inside no_grad + Only 1 Token

**File**: grpo_regime_training_kaggle.py L1535-1541

**Problem**:
1. `with torch.no_grad():` means entropy produces zero gradient. `loss -= coef * entropy` only changes the loss value, not parameters.
2. `dummy_inp = zeros(1,1)` only computes entropy at the BOS position, not representative of the full sequence's exploration.

**Fix**: Remove `no_grad()`. Accumulate per-step entropy during the autoregressive loop, average, and add to loss with gradient.

### P0-3: Autoregressive Start Token Inconsistency

**File**: grpo_regime_training_kaggle.py
- L1415: Guided path → `inp = torch.zeros(1, 1)` (token 0 = RET feature)
- L1402: Warmup → `warmup_inp = torch.tensor([[feat_idx]])` (input=feat_idx)
- L1485: Fallback → `fb_inp = torch.tensor([[feat_idx]])` (input=feat_idx)

**Problem**: Warmup/Fallback paths feed the model its own prediction as input ("predict feat_idx given feat_idx as context"), while the guided path feeds zeros. These two training signals are contradictory — the model learns inconsistent input-output mappings.

**Fix**: Unify all paths to use `zeros(1,1)` as starting input. Better: add a dedicated BOS token to VOCAB.

### P0-4: Train-Val Data Leakage (Catastrophic)

**File**: grpo_regime_training_kaggle.py L1651-1660

**Problem**: `np.concatenate(all_feat, axis=1)` concatenates multiple stocks' time series, then splits 80/20 by time. Example: 4 stocks × 500 days → 2000 days concatenated. Train = first 1600 days (contains 100% of stocks A, B, C + partial D). Val = last 400 days (only stock D's tail). This completely breaks cross-sectional time-series validation.

**Fix**: Split each stock independently 80/20 first, then concatenate Train splits and Val splits separately.

## High Bugs (P1 — Impair Training Quality)

### P1-1: Synthetic Data Alpha Injection is Fake

**File**: grpo_regime_training_kaggle.py L632-656

**Problem**: v3.3 added `alpha_config` specifying features and weights (e.g., 2330 → RET + INST_FLOW + TX_INST_NET_OI + NASDAQ_CLOSE). However, `alpha_mat` (L650-655) is independently generated AR(1) random noise — completely uncorrelated with the actual computed feature values. The model cannot learn the relationship because features and target are independent.

**Fix**: Alpha component should use the actual computed feature values with known weights, or at minimum create a known correlation structure between alpha_mat and feature_mat.

### P1-2: Group Overfit Penalty "Collective Punishment"

**File**: grpo_regime_training_kaggle.py L1068-1072

**Problem**: `train_ic` and `val_ic` are the best formula's IC from the entire group (L1497-1498). The IC gap penalty is then applied identically to ALL group members. If one formula overfits, all members (including good non-overfit formulas) get the same penalty deduction.

**Fix**: Compute per-formula IC gap for individual penalty, or use group mean IC instead of best IC.

### P1-3: MTPHead is Dead Code

**File**: grpo_regime_training_kaggle.py L1300-1306

**Problem**: L1301 `logits, value = self.mtp_head(h)` correctly calls the gated fusion (mean+max+first pool with learned gate weights). But L1305 immediately overrides with `logits_per_pos = self.mtp_head.head_mean(h)` — only using the simple linear projection. The gate, head_max, and head_first computations are entirely wasted.

**Fix**: Use the MTPHead output directly. If per-position logits are needed, extend MTPHead.forward to return (B, T, vocab) format instead of (B, vocab).

### P1-4: get_valid_tokens Doesn't Fully Check Remaining Steps for Feature Push

**File**: grpo_regime_training_kaggle.py L178-184

**Problem**: Feature push only checks `if remaining > 0` (L183), but doesn't use the `min_needed` calculated at L182. When remaining=1 and stack_depth=1, pushing a feature makes stack=2 which can never reduce to 1 in 0 remaining steps. This creates invalid formulas that trigger fallback.

**Fix**: Change L183-184 to:
```python
if remaining - 1 >= min_needed:
    valid.update(range(N_FEATURES))
```

### P1-5: GPU Performance Bottleneck — Rebuilding Mask Every Step

**File**: grpo_regime_training_kaggle.py L1439-1443, L1447-1454

**Problem**: Each autoregressive step creates numpy arrays on CPU, then calls `torch.tensor(mask, device=...)` for Host-to-Device transfer. Done twice per step (guided_mask + regime_mask). This is a major performance bottleneck for autoregressive generation.

**Fix**: Pre-allocate GPU mask tensors, update in-place each step. Avoid Host-to-Device transfer in the inner loop.

## Medium Issues (P2 — Code Quality)

### P2-1: robust_normalize Defined But Never Used

**File**: grpo_regime_training_kaggle.py L1806-1830

Rolling median + MAD normalization is fully implemented but never called anywhere in the file. Current zscore uses rolling mean/std instead.

**Decision needed**: Either replace zscore with robust_normalize in TWFeatureEngineer, or delete the dead function.

### P2-2: Kaggle Script Indentation Error @L1175

All classes from QKNormAttention onward (L1175-1306) are incorrectly nested inside SwiGLU due to patch() indentation corruption. Need to move them to top level.

## TODO List (Priority Order)

### Phase 1: P0 Critical (Model Convergence)
- T1: Delete `_old_log_probs` off-policy path (L1519-1526, L1549-1550)
- T2: Fix Entropy Bonus — remove no_grad, accumulate in autoregressive loop
- T3: Unify start token — all paths use zeros(1,1) or BOS
- T4: Fix Train-Val Split — per-stock 80/20 then merge

### Phase 2: P1 High (Training Quality)
- T5: Fix alpha injection — use actual feature values or known correlation
- T6: Per-formula IC gap penalty (not collective)
- T7: Enable MTPHead — remove head_mean override
- T8: Fix get_valid_tokens feature push check
- T9: Pre-allocate GPU mask tensors

### Phase 3: P2 Code Quality
- T10: Fix L1175+ indentation (move classes to top level)
- T11: Decide robust_normalize fate
- T12: Sync core.py and Kaggle StackVM/GRPO logic
- T13: Add BOS/EOS tokens to VOCAB

### Phase 4: Monitoring & Integration
- T14: Monitor Kaggle kernel status
- T15: Download training outputs
- T16: Integrate results back to skill
- T17: Replace synthetic with real twstock data
- T18: End-to-end validation

## Architecture Recommendations

1. **Training vs Inference Separation**: Kaggle script should only train + output model weights/formulas. ai_dig_money_core.py should only load results for inference. Both currently have StackVM/GRPO implementations that need unification.

2. **Model Serialization**: Trained LoopedTransformer should save state_dict; ai_dig_money_core.py loads it for guided decoding.

3. **Synthetic Data Transition**: Current alpha injection has fundamental flaws. Recommend jumping directly to real data. If synthetic validation is needed, features and returns must have known causal structure.
