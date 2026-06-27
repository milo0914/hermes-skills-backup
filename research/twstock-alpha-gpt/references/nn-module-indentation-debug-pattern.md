# nn.Module Indentation Debug Pattern

## Problem

Patch tool corrupts `class Foo(nn.Module)` indentation: `def __init__` and `def forward` get over-indented (e.g., 12sp instead of 8sp). Python `py_compile` and `ast.parse` PASS (syntax is legal), but PyTorch `nn.Module.__call__` fails at runtime:

```
NotImplementedError: Module [SwiGLU] is missing the required "forward" function
```

This is because over-indented `def forward` becomes a nested function inside `__init__`, not a class method.

## Diagnosis: Precise Indentation Check Script

```python
#!/usr/bin/env python3
"""Check indentation of all nn.Module subclasses in a Python file."""
import re

filepath = 'target_file.py'
with open(filepath) as f:
    lines = f.readlines()

# Find all nn.Module subclasses
for i, line in enumerate(lines, 1):
    stripped = line.rstrip('\n')
    indent = len(stripped) - len(stripped.lstrip())
    
    # Flag class definitions
    if re.match(r'^\s*class \w+.*nn\.Module', stripped):
        print(f"L{i}: CLASS  indent={indent} | {stripped[:80]}")
    # Flag method definitions inside classes (indent 4-12)
    elif re.match(r'^\s{1,12}def (__(init|forward|call)__', stripped):
        print(f"L{i}: METHOD indent={indent} | {stripped[:80]}")
```

Expected structure for correct indentation (4sp base):
- `class Foo(nn.Module):` → indent=4
- `def __init__(self, ...):` → indent=8
- `self.xxx = ...` → indent=12
- `def forward(self, x):` → indent=8  ← **MUST be 8, not 12**
- `return ...` → indent=12

## Fix: Write-file Python Script Pattern

```python
#!/usr/bin/env python3
"""Fix over-indented def forward in nn.Module subclasses."""
filepath = 'target_file.py'
with open(filepath) as f:
    lines = f.readlines()

# Fix specific lines (example: L1170 should be 8sp, L1171-1173 should be 12sp)
fixes = {
    1170: (' ' * 8, ' ' * 12),  # (old_prefix_len, new_prefix)
}
# More reliable: fix by detecting over-indented methods
for i, line in enumerate(lines):
    stripped = line.lstrip()
    indent = len(line) - len(stripped)
    # If "def forward" is at indent 12 inside a class (should be 8)
    if stripped.startswith('def forward(') and indent == 12:
        # Check if previous class def is at indent 4
        lines[i] = ' ' * 8 + stripped  # Fix to 8sp
    # If body of forward is at indent 16 (should be 12)
    elif indent == 16 and i > 0:
        # Check if we're inside a just-fixed forward method
        prev_indent = len(lines[i-1]) - len(lines[i-1].lstrip())
        if prev_indent == 8 and lines[i-1].lstrip().startswith('def forward'):
            lines[i] = ' ' * 12 + stripped

with open(filepath, 'w') as f:
    f.writelines(lines)

# Validate
import py_compile
py_compile.compile(filepath, doraise=True)
print("SYNTAX OK")
```

## Key Insight

`cat -A` output is NOT reliable for checking space counts when the file contains multi-byte UTF-8 characters (Chinese comments, etc.). The `^` markers shift. Use Python `len(line) - len(line.lstrip())` instead for precise counts.

## Related Pitfalls

- twstock-alpha-gpt pitfall #25: patch tool indentation corrosion (causes IndentationError)
- twstock-alpha-gpt pitfall #72: nn.Module over-indentation (passes py_compile but fails at PyTorch runtime)
- These are two manifestations of the same root cause (patch tool strips leading spaces)

## Session Reference

- 2026-06-09: SwiGLU.forward() at L1170 had indent=12 (should be 8), causing `NotImplementedError` on Kaggle. Fixed via write_file Python script. Kernel v3.1 re-pushed successfully after fix.
