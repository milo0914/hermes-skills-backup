# Kaggle Notebook Source Format: str vs list

## The Critical Discovery (2026-06-18)

**Kaggle notebook code cells require `source` to be a `str` type.**
If `source` is a `list` (even `["entire code as single element"]`), the kernel runner
skips all execution and only runs nbconvert. Kernel appears as COMPLETE with
only nbconvert log output — no training stdout, no result files.

## Reproduction

- v6.18 (working): `source_type=str`, 1 code cell, no cell IDs → **RUNNING, COMPLETE** with real output
- v6.19 v1 (broken): `source_type=list`, source converted during build → **COMPLETE** in <10s, only nbconvert log
- v6.19 v2 (broken): same as v1 with `enable_gpu: true` → same result
- v6.19 v3 (broken): same with cell IDs added → same result
- v6.19 v4 (fixed): `source_type=str`, built without nbformat normalization → **RUNNING** (real execution)

## Root Cause

The notebook build process in v1-v3 used nbformat normalization which
converted code cell source from `str` to `list`:

```python
# v6.18 (works):  source is str "whole script"
# v6.19 v3 (broken): source is list ["whole script"]  ← single str in list
```

Kaggle's internal kernel runner apparently only recognizes `str` as
executable code. When source is a `list`, the runner treats it as
already-processed output and skips execution.

## Fix

Never use nbformat APIs to normalize notebook JSON. Work directly with
`json.load()` / `json.dump()`. After any modification, assert source is str:

```python
import json, uuid

with open('notebook.ipynb') as f:
    nb = json.load(f)

# Modify cell source (keep as str)
code = nb['cells'][1]['source']
assert isinstance(code, str)

# Add cell IDs (direct dict manipulation, not nbformat)
for cell in nb['cells']:
    if 'id' not in cell:
        cell['id'] = uuid.uuid4().hex[:10]

# If source somehow became list, fix it
for cell in nb['cells']:
    if isinstance(cell['source'], list):
        cell['source'] = ''.join(cell['source'])

# Verify before writing
assert isinstance(nb['cells'][1]['source'], str)

with open('notebook.ipynb', 'w') as f:
    json.dump(nb, f)
```

## Verification after push

```bash
KAGGLE_API_TOKEN="KGAT_xxx" kaggle kernels status OWNER/SLUG
# Wait 15-30 seconds
# RUNNING = good (real execution started)
# COMPLETE immediately = source format problem
```

## Build Script Pattern That Works

```python
# 1. Load JSON directly (not nbformat)
with open("source.ipynb") as f:
    nb = json.load(f)

code = nb['cells'][1]['source']
assert isinstance(code, str)  # critical check

# 2. Apply string replacements to code
code = code.replace("old_string", "new_string")
# ... multiple replacements ...

# 3. Update metadata
nb['metadata']['kernelspec']['display_name'] = 'New Title'
nb['cells'][0]['source'] = nb['cells'][0]['source'].replace('v6.16', 'v6.19')

# 4. Set source back (same str object)
nb['cells'][1]['source'] = code

# 5. Remove any cell IDs (avoid source format issues)
for cell in nb['cells']:
    if 'id' in cell:
        del cell['id']

# 6. Final verification
assert isinstance(nb['cells'][1]['source'], str)

# 7. Write
with open('output.ipynb', 'w', encoding='utf-8') as f:
    json.dump(nb, f, ensure_ascii=False)
```

## Why nbformat Causes This

nbformat 4.x normalizer converts code sources from single string to
list of strings (one per line) when:
- Reading via `nbformat.read()` (not `json.load()`)
- Writing via `nbformat.write()` (not `json.dump()`)
- Calling `nbformat.validate()` with the `upgrade` parameter
- Any `nbformat.v4.new_code_cell()` call creates list-format source

The normalization is "correct" per nbformat spec (both formats are valid),
but Kaggle's execution engine only handles `str` format.