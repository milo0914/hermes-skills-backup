# Kaggle v5.6 REINFORCE Build Record

## Date: 2026-06-10

## Problem

v5.5 kernel completed training but PPO loss was identically 0 for all 19500 steps. Root cause: on-policy GRPO with PPO clipped surrogate produces loss≡0 because:

1. `ratio = torch.exp(log_probs_tensor - log_probs_tensor.detach())` → forward value = exp(0) = 1.0
2. advantages standardized → mean = 0
3. `loss = -min(ratio*A, clip(ratio)*A).mean() = -min(A, A).mean() = -mean(A) = 0`

The gradient exists (d(ratio)/d(log_pi) = 1.0), but the loss VALUE is constant w.r.t. ratio, so model never learns.

## Fix: REINFORCE Policy Gradient

Replace PPO clipped surrogate with pure REINFORCE:

```python
# REMOVED (v5.5):
# ratio = torch.exp(log_probs_tensor - log_probs_tensor.detach())
# surr1 = ratio * advantages
# surr2 = torch.clamp(ratio, 1 - clip_ratio, 1 + clip_ratio) * advantages
# policy_loss = -torch.min(surr1, surr2).mean()

# ADDED (v5.6):
policy_loss = torch.mean(-log_probs_tensor * advantages.detach())
```

Also removed:
- `_old_log_probs` storage (off-policy path was mathematically broken anyway)
- `clip_ratio` parameter (not needed for REINFORCE)
- All references to `ratio` in training loop

## Build Method

Used Python build script (`/tmp/patch_v56.py`) with string replacement on v5.5 source (`/tmp/kaggle-v55-output/grpo_regime_training_v5.py`):

1. Replace PPO loss block → REINFORCE loss block
2. Remove `_old_log_probs` storage lines
3. Remove `clip_ratio` references
4. Fix indentation via `fix_indent_v56.py` and `fix_ratio_refs.py`
5. Validate with `py_compile.compile()`

## Kernel Details

- **Slug**: `mhhuang14/grpo-regime-aware-factor-training-v5-6`
- **Push**: Successful, status=RUNNING
- **Background monitor**: proc_d4a32a12df00 (60 rounds x 60s polling)
- **Expected runtime**: ~40 minutes (based on v5.5 which took 2382s)
- **GPU**: T4 (NvidiaTeslaT4)
- **Config**: G=8, batch=128, train_steps=20000

## Local Integration Status

- `ai_dig_money_core.py` already updated with v3.1 (22 features, VOCAB_SIZE=34)
- `best_strategy_per_regime.json` from v5.5: only `mid_cap_tech` regime (SP500_CLOSE single factor)
- Regime fallback: missing regimes use `"CLOSE"` formula + `alpha_const=0.01`
- E2E smoke test: V2 + V3 pipeline both pass (4 stocks, 22 features, 250 rows)

## Post-v5.6 Steps

1. Wait for kernel COMPLETE
2. Download: `kaggle kernels pull mhhuang14/grpo-regime-aware-factor-training-v5-6 -p /tmp/kaggle-v56-output/`
3. Verify loss is non-zero (should see small but real gradient signal)
4. Copy `best_strategy_per_regime.json` to local `scripts/`
5. If results good → replace synthetic data with real FinMind data and retrain

## Key Lesson

Every new Kaggle kernel version MUST carry forward all previously fixed pitfalls. v5.5 regressed the REINFORCE fix because it was built from v5 source (PPO version) instead of v5.1 (REINFORCE version). Use a checklist:
- [ ] REINFORCE loss (not PPO clipped surrogate)
- [ ] `_safe_logits` NaN guard
- [ ] os.walk dataset path (not flat os.listdir)
- [ ] groupby view .copy() (pitfall #77)
- [ ] Loss print format `.8f` (not `.4f`, pitfall #56)
