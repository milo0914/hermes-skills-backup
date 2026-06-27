# GRPO v5.7 REINFORCE Advantage Normalization Fix

**Date**: 2026-06-10
**Kernel slug**: `mhhuang14/grpo-regime-aware-factor-training-v5-7`
**Status**: Pushed to Kaggle, monitoring

## Bug Chain

### v5.5: PPO loss=0
- `ratio = exp(log_pi - log_pi.detach()) = exp(0) = 1.0`
- `loss = -min(ratio*A, clip(ratio)*A).mean() = -min(A, A).mean() = -mean(A) = 0`
- Root cause: PPO math fundamentally incompatible with on-policy single-epoch GRPO

### v5.6: REINFORCE still loss=0
- Changed to `loss = -(log_probs_tensor * advantages).mean()`
- But advantages STILL zero → loss STILL zero
- **Root cause**: Advantage normalization uses zero-mean centering:
  ```python
  advantages = (rewards - group_mean) / group_std  # mean(A) = 0 by construction
  ```
- When log_probs variance is tiny (G=6-8, all formulas similar):
  `loss = -(log_probs * A).mean() ≈ -mean(log_probs) * mean(A) = 0`
- The REINFORCE fix was correct in principle, but advantage centering neutralized it

### v5.7 Fix: Min-Max Normalization
- Replace zero-mean centering with min-max normalization:
  ```python
  r_min = rewards[valid_mask].min()
  r_max = rewards[valid_mask].max()
  r_range = r_max - r_min + 1e-8
  advantages = (rewards - r_min) / r_range  # A ∈ [0, 1], mean > 0
  advantages = np.where(valid_mask, advantages, 0.0)
  ```
- Key insight: `mean(A) > 0` when rewards are positive (which they should be after guided decoding + warmup)
- This ensures `loss = -(log_probs * A).mean() < 0` with non-trivial gradient magnitude
- Invalid formulas (reward < -5) get advantage = 0.0 (via valid_mask), not negative advantage

### GPU Detection Fix (v5.7 companion)
- `if cc[0] >= 7:` → `if cc[0] >= 5:` (sm_70 → sm_50)
- T4 GPU is sm_75, should pass this check
- P100 is sm_60 — passes sm_50 check but may fail CUDA ops with PyTorch 2.10+cu128 (see pitfall #35)
- Safer approach: `try: torch.zeros(1, device="cuda"); except: GRPO_FORCE_CPU=1`

### Gradient Debug Logging (v5.7 companion)
- Every 500 steps, log advantage and log_prob statistics:
  ```python
  if step % 500 == 0:
      with torch.no_grad():
          print(f"    adv=[{_a_min:.3f},{_a_max:.3f}] mean={_a_mean:.3f} logp=[{_lp_min:.3f},{_lp_max:.3f}]")
  ```
- Critical for diagnosing: (a) advantage range, (b) whether mean(A) is truly 0, (c) log_prob variance

## Build Script Method (v5.7)

v5.7 used a Python build script (`/tmp/patch_v57_v5.py`) that reads the v5.6 source line-by-line and applies targeted replacements using the **original line's indentation as base** (`orig_indent = line[:len(line) - len(line.lstrip())]`), then constructs new lines as `orig_indent + "    " + content` for each nested level.

This avoids the write_file indentation stripping problem (see below).

## Critical Tool Bug: write_file Strips Leading Spaces

**Discovered**: When writing Python code via `write_file` with multi-line strings containing leading spaces, the tool strips leading whitespace from each line. This means:

- `"        if step % 500 == 0:\n"` (8sp) → written as `"if step % 500 == 0:\n"` (0sp)
- This systematically destroys Python indentation
- `patch()` tool has the same problem (already documented in pitfall #25)

**Workaround**: Use a Python build script that:
1. Reads the source file as lines
2. For each replacement, extracts `orig_indent = line[:len(line) - len(line.lstrip())]`
3. Constructs new lines as `orig_indent + content` or `orig_indent + "    " + content`
4. Writes the modified lines back using `f.writelines(new_lines)`
5. Validates with `py_compile.compile(file, doraise=True)`

**Pattern** (proven in v5.7):
```python
with open(source_file) as f:
    lines = f.readlines()

new_lines = []
for i, line in enumerate(lines):
    # Targeted replacement using orig_indent
    if "target_string" in line:
        orig_indent = line[:len(line) - len(line.lstrip())]
        new_lines.append(orig_indent + "new_code_here\n")
        continue
    new_lines.append(line)

with open(output_file, "w") as f:
    f.writelines(new_lines)

import py_compile
py_compile.compile(output_file, doraise=True)
```

## Diagnostic Checklist for REINFORCE loss=0

1. Check `mean_reward` — if it never changes across steps, model is not learning
2. Check `loss` with `.8f` precision — `-0.0000` with `.4f` might be `-0.0000038`
3. Check advantage statistics: `adv=[min, max] mean=???`
   - If `mean ≈ 0.0` → zero-mean centering is the culprit
   - If `min == max` → all rewards identical (no signal in data)
4. Check `logp` range: if `[min, max]` are very close → model is not differentiating formulas
5. Check valid_mask percentage: if 0% → guided decoding broken (root cause A)
