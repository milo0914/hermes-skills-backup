# Notebook Builder Pattern for GRPO Iterative Development

**用途**: 從現有 notebook 版本衍生新版本，確保所有修改確實生效

---

## 標準流程

### 1. 載入基準版本
```python
import json

with open(BASE_NOTEBOOK, 'r') as f:
    nb = json.load(f)

src = ''.join(nb['cells'][1]['source'])  # 假設 code 在第 2 個 cell
```

### 2. 逐項修改 (單行片段替換，避免縮排問題)
```python
# 好: 單行唯一片段
src = src.replace('train_steps: int = 8000', 'train_steps: int = 12000')

# 好: regex 替換帶註解
import re
src = re.sub(
    r'exploration_recovery_eps_boost: float = 0\.5',
    'exploration_recovery_eps_boost: float = 0.8  # 【v6.17】0.5→0.8',
    src
)

# 壞: 多行硬編碼字面量 (pitfall #52)
# src = src.replace('''    if condition:
#         do_something()''', new_block)  # 縮排極難匹配
```

### 3. 驗證修改確實生效 (關鍵步驟!)
```python
# 寫入後立即重讀驗證
with open(OUTPUT_NOTEBOOK, 'w') as f:
    json.dump(nb, f, indent=2, ensure_ascii=False)

with open(OUTPUT_NOTEBOOK, 'r') as f:
    check = ''.join(json.load(f)['cells'][1]['source'])

checks = [
    ("train_steps 12000", "train_steps: int = 12000" in check),
    ("eps_boost 0.8", "exploration_recovery_eps_boost: float = 0.8" in check),
    ("torch 2.0.1+cu118", "torch==2.0.1+cu118" in check),
]
for name, ok in checks:
    print(f'{"✓" if ok else "✗"} {name}')
```

### 4. 建立 kernel-metadata.json
```python
metadata = {
    "id": "mhhuang14/twstock-grpo-v6-17-fixed-val-ic-reward",
    "title": "TWStock GRPO v6 17 Fixed Val-IC Reward",  # title 去標點、空格改連字符 = slug
    "code_file": "twstock-grpo-v6-17-fixed.ipynb",
    "language": "python",
    "kernel_type": "notebook",
    "is_private": True,
    "enable_gpu": True,
    "enable_internet": True,
    "dataset_sources": ["mhhuang14/twstock-v6-0-real-data-20stocks-5y"],
    "machine_shape": "Gpu"
}
```

### 5. 推送
```bash
mkdir -p /tmp/push_dir
cp notebook.ipynb /tmp/push_dir/
cp kernel-metadata.json /tmp/push_dir/kernel-metadata.json
python3 -m kaggle kernels push -p /tmp/push_dir --accelerator GPU_T4
```

---

## 常見 Pitfalls

| Pitfall | 症狀 | 解法 |
|---------|------|------|
| **多行字面量替換失敗** | 替換不生效、找不到匹配 | 用單行片段 + 前後文 print 確認位置，或用 regex |
| **版本號不一致** | docstring v6.17 但 JSON output 仍是 v6.16 | 統一搜尋替換所有 `"v6.16"` → `"v6.17"` |
| **slug 與 title 不符** | 400 Bad Request | title 去標點、空格→連字符，必須等於 slug 最後一段 |
| **metadata 缺欄位** | push 失敗 | 必填: id, title, code_file, kernel_type, machine_shape |

---

## 本次會話使用的 Builder Scripts

| 腳本 | 用途 | 位置 |
|------|------|------|
| `build_v617.py` | v6.17 初版 (含 reward 修改) | `/tmp/build_v617.py` |
| `build_v617_fixed.py` | v6.17 Fixed (PyTorch 相容性修復) | `/tmp/build_v617_fixed.py` |

---

## 自動化建議

未來可將 builder 封裝為可重用函數：
```python
def build_notebook(base_path, output_path, modifications: dict, metadata: dict):
    """
    modifications = {
        'train_steps: int = 8000': 'train_steps: int = 12000',
        'torch==2.2.0+cu118': 'torch==2.0.1+cu118',
        ...
    }
    """
    # 通用 builder 邏輯
```

---

## 經驗法則

1. **永遠用 write_file 而非 patch** — 用戶強制要求，避免 patch 定位問題
2. **驗證要在寫入後立即執行** — 重讀檔案確認，不要信任 replace 回傳值
3. **保留原始版本** — base notebook 不修改，輸出新檔案
4. **Metadata title/slug 一致性** — 推送前用腳本驗證 `title.lower().replace(' ', '-').replace('.', '') == slug.split('/')[-1]`