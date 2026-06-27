# .py → .ipynb 轉換最佳實踐 (v4.1 驗證通過)

## 核心方法：Section Header 正則切割

用正則掃描 `# ====... # N. section_name` 模式定位切割點，不硬編碼行號。

```python
import json, uuid, re

def py_to_ipynb(source_path, output_path, kernel_display_name="Python 3"):
    with open(source_path) as f:
        lines = f.read().split('\n')
    
    # Section header pattern: # ===== # 1. Imports & Environment =====
    section_re = re.compile(r'^#\s*(\d+)\.\s+')
    cut_indices = [0]  # first cell starts at line 0
    
    for i, line in enumerate(lines):
        if section_re.match(line.strip()):
            cut_indices.append(i)
    
    cut_indices.append(len(lines))  # last cell ends at EOF
    
    cells = []
    for i in range(len(cut_indices) - 1):
        start = cut_indices[i]
        end = cut_indices[i + 1]
        src = [l + '\n' for l in lines[start:end]]
        src[-1] = src[-1].rstrip('\n')  # last line no trailing \n
        
        # Validate each cell compiles
        try:
            compile(''.join(src), f'<cell_{i}>', 'exec')
        except SyntaxError as e:
            print(f"Cell {i} (lines {start}-{end}) syntax error: {e}")
            # Try to fix: if cell starts with blank lines, trim
            while src and src[0].strip() == '\n':
                src.pop(0)
            compile(''.join(src), f'<cell_{i}>', 'exec')
        
        cells.append({
            "cell_type": "code",
            "id": str(uuid.uuid4())[:8],
            "metadata": {},
            "outputs": [],
            "source": src,
            "execution_count": None,
        })
    
    nb = {
        "nbformat": 4, "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {"display_name": kernel_display_name, "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.10.0"},
        },
        "cells": cells,
    }
    with open(output_path, 'w') as f:
        json.dump(nb, f, indent=1, ensure_ascii=False)

py_to_ipynb('grpo_v4_unified.py', 'grpo_v4_unified.ipynb')
```

## 已知陷阱

1. **行號前綴污染**：read_file 輸出含 ` 37|` 前綴，若被寫回 .py 文件會導致 IndentationError。必須清理：`lines = [re.sub(r'^\s*\d+\|', '', l) for l in raw_lines]`
2. **Cell 切割不可切斷 class/function**：若 section header 落在 class body 中間，該 cell 會 SyntaxError。解法：調整 section header 位置到 class 外部。
3. **空行前導空格**：patch 工具會把 0sp 空行插入縮排塊中，Python 語法不報錯但影響可讀性。清理：`line.rstrip()` 後按周圍行補縮排。
4. **jupytext 缺 kernelspec**：不建議用 jupytext，直接用 json 構建 notebook 並注入 kernelspec metadata。
5. **Cell 數量建議**：5-15 cells。過多 (>30) 增加解析風險，過少 (<3) 出錯時難定位。

## v4.1 實戰驗證

- 8 cells：imports/env → StackVM → constants → trainer → GRPO → evaluate → main v4.1 → training loop
- Cell 切割按 `# N.` section number 正則匹配
- 每個 cell 用 `compile()` 驗證
- Kaggle push → 版本 6 → COMPLETE（CPU fallback on P100, ~18.5 min）
