#!/usr/bin/env python3
"""Apply zero-convergence bug fix to grpo_regime_training_kaggle.py"""

import py_compile

filepath = '/data/.hermes/skills/research/twstock-alpha-gpt/scripts/grpo_regime_training_kaggle.py'

with open(filepath, 'r') as f:
    content = f.read()

lines = content.split('\n')
total_lines = len(lines)
print(f"Total lines: {total_lines}")

def find_line(needle, start=0):
    for i in range(start, total_lines):
        if needle in lines[i]:
            return i
    return -1

# ====================================================================
# FIX 0: Fix pre-existing syntax error - missing "class LoopedTransformer"
# The LoopedTransformer class definition is missing the "class" keyword
# Line 875 has just "def __init__" but no "class LoopedTransformer"
# ====================================================================
# Actually, let me check what line 875 says
print(f"Line 875: {lines[874]}")
# It says " class LoopedTransformer(nn.Module):" but something is wrong
# Let me look more carefully

for i in range(870, 920):
    print(f"  {i+1}: {lines[i][:80]}")
