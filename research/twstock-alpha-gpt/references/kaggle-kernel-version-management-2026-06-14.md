# Kaggle Kernel Version Management Pattern (2026-06-14)

## Version Numbering Confusion
Three different "version" identifiers exist and must be kept in sync:

| Layer | Location | Example | Notes |
|-------|----------|---------|-------|
| **Notebook filename** | File system | `grpo-regime-aware-factor-training-v6-1.ipynb` | Static filename, rarely changed |
| **Notebook internal title** | `metadata.title` / markdown | "v6.2" / "v6.7 Advantage Collapse Fix" | What users see in UI |
| **Kernel metadata id** | `kernel-metadata.json` → `id` | `mhhuang14/grpo-regime-aware-factor-training-v6-8` | **Authoritative for Kaggle pushes** |

## Current State (2026-06-14) — **CORRECTED 2026-06-14 (v6.8 CONFIRMED)**
- File: `grpo-regime-aware-factor-training-v6-1.ipynb` (unchanged since v6.1)
- Internal markdown: **v6.2** (No Synthetic Fallback)
- Code prints: **v6.7 Advantage Collapse Fix + Debug**
- **Kernel metadata: v6.8 EXISTS on Kaggle** — `mhhuang14/twstock-grpo-regime-aware-factor-training-v6-8` (slug has `twstock-` prefix, internal title `v6.2`)
- **v6.8 key improvements over v6.1**:
  - KNOWN_REGIMES: 20 stocks × 4 regimes (5 each: LARGE_CAP, MID_CAP_TECH, TRADITIONAL, FINANCIAL)
  - RegimeTrainingPlan: feature_weights, operator_mask, training_params per regime
  - Advantage collapse fix: noise injection + group_size=64
  - auto-scan `/kaggle/input/` for dataset files
- **This session verified**: `kaggle kernels list --user mhhuang14` shows v6.8. **Lesson: always check Kaggle directly before assuming local is latest.**

## Best Practices
1. **Kernel metadata `id` is the source of truth** — increment this on every `kaggle kernels push`
2. **Notebook filename** — only change when major refactor (e.g. v6-1 → v7-1)
3. **Internal version strings** — update markdown + code prints together to reflect actual changes
4. **Dataset sources in metadata** — must match actual dataset slug: `"mhhuang14/twstock-v6-0-real-data-20stocks-5y"`
5. **Always verify with `kaggle kernels list --user OWNER` before assuming version exists** — don't trust internal version strings

## Push Workflow
```bash
# 1. Update kernel-metadata.json id version
# 2. Push
kaggle kernels push -p /home/appuser/twstock_kernel/
# 3. Monitor
kaggle kernels status mhhuang14/twstock-grpo-regime-aware-factor-training-v6-8
# 4. Get output after completion
kaggle kernels output mhhuang14/twstock-grpo-regime-aware-factor-training-v6-8 -p /tmp/out/
```

## Auto-Scan Pattern for Dataset Mounting
Kaggle mounts datasets under `/kaggle/input/<owner>/<dataset-slug>/` but the exact path varies. Use auto-scan:

```python
def find_csv_files(data_path: str = "/kaggle/input"):
    import os, glob
    csv_files = {}
    for root, dirs, files in os.walk(data_path):
        for f in files:
            if f.endswith('.csv'):
                csv_files[f] = os.path.join(root, f)
    return csv_files

# Usage in adapt_finmind_data
csv_files = find_csv_files()
# Support multiple filename variants
ohlcv_path = csv_files.get("price_ohlcv.csv") or csv_files.get("twstock_daily.csv") or csv_files.get("ohlcv.csv")
inst_path = csv_files.get("inst_flow.csv") or csv_files.get("inst_data.csv")
# ... etc
```

## Files
- Kernel source: `/home/appuser/twstock_kernel/grpo-regime-aware-factor-training-v6-1.ipynb`
- Metadata: `/home/appuser/twstock_kernel/kernel-metadata.json`
- Current kernel: `mhhuang14/grpo-regime-aware-factor-training-v6-8` (RUNNING)