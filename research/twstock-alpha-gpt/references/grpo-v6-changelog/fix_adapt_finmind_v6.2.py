#!/usr/bin/env python3
"""修復 adapt_finmind_data: 增強路徑探測，不使用 os.walk"""
import json

with open('/home/appuser/twstock_kernel/grpo-regime-aware-factor-training-v6-1.ipynb', 'r') as f:
    nb = json.load(f)

code_cell = nb['cells'][1]
source = list(code_cell['source'])
full = ''.join(source)

# === 修復 1: 替換 adapt_finmind_data 中的 os.walk ===
old_func_start = 'def adapt_finmind_data(data_path: str):'
old_func_body = '''
    """從 Kaggle dataset 載入真實台股數據 (v6.0 dsfix — 支援 Dataset v2 雙格式)"""
    import os

    # 遞迴蒐集所有 CSV 檔案
    csv_files = {}
    for root, dirs, files in os.walk(data_path):
        for f in files:
            if f.endswith('.csv'):
                csv_files[f] = os.path.join(root, f)
    print(f"  [adapt_finmind] 找到 {len(csv_files)} 個 CSV: {list(csv_files.keys())}")
'''

new_func_body = '''
    """從 Kaggle dataset 載入真實台股數據 (v6.2 強制真實數據)"""
    import os, glob
    
    # 【v6.2】多路徑嘗試 + glob 遞迴搜尋 (取代 os.walk, 解決 Kaggle 掛載不確定性)
    search_paths = [data_path]
    # Kaggle 有時會把 dataset 內容放在 slug 同名子目錄下
    slug_name = os.path.basename(data_path.rstrip("/"))
    nested = os.path.join(data_path, slug_name)
    if os.path.isdir(nested):
        search_paths.append(nested)
    
    csv_files = {}
    for sp in search_paths:
        pattern = os.path.join(sp, "**", "*.csv")
        for csv_path in glob.glob(pattern, recursive=True):
            csv_files[os.path.basename(csv_path)] = csv_path
    
    # 若仍未找到，診斷 /kaggle/input/ 目錄結構
    if len(csv_files) == 0:
        print("  [adapt_finmind] WARNING: glob 未找到 CSV，嘗試診斷...")
        kaggle_input = "/kaggle/input"
        if os.path.exists(kaggle_input):
            print(f"  [adapt_finmind] /kaggle/input 內容:")
            for root, dirs, files in os.walk(kaggle_input):
                level = root.replace(kaggle_input, '').count(os.sep)
                indent = ' ' * (level + 2)
                print(f"{indent}{os.path.basename(root)}/")
                subindent = ' ' * (level + 4)
                for f in files[:10]:
                    print(f"{subindent}{f}")
                if len(files) > 10:
                    print(f"{subindent}... ({len(files)} files total)")
                if level > 3:
                    break
        else:
            print(f"  [adapt_finmind] /kaggle/input 不存在！")
            # 嘗試列出 /kaggle/
            for item in os.listdir("/kaggle/"):
                print(f"  [adapt_finmind] /kaggle/{item}")
    
    print(f"  [adapt_finmind] 找到 {len(csv_files)} 個 CSV: {list(csv_files.keys())}")
'''

# 替換函數體
old_marker = '    """從 Kaggle dataset 載入真實台股數據 (v6.0 dsfix — 支援 Dataset v2 雙格式)"""'
new_marker = '    """從 Kaggle dataset 載入真實台股數據 (v6.2 強制真實數據)"""'

# 更精確的替換：從 def 函數定義到 "return df, inst_df, margin_df, futures_oi_df, us_indices_df" 前的 os.walk 段落
# 用 old_string 找到並替換從 """ 開頭到 csv_files 收集結束的段落

old_walk_block = '''    import os

    # 遞迴蒐集所有 CSV 檔案
    csv_files = {}
    for root, dirs, files in os.walk(data_path):
        for f in files:
            if f.endswith('.csv'):
                csv_files[f] = os.path.join(root, f)
    print(f"  [adapt_finmind] 找到 {len(csv_files)} 個 CSV: {list(csv_files.keys())}")'''

new_walk_block = '''    import os, glob
    
    # 【v6.2】多路徑嘗試 + glob 遞迴搜尋 (取代 os.walk, 解決 Kaggle 掛載不確定性)
    search_paths = [data_path]
    # Kaggle 有時會把 dataset 內容放在 slug 同名子目錄下
    slug_name = os.path.basename(data_path.rstrip("/"))
    nested = os.path.join(data_path, slug_name)
    if os.path.isdir(nested):
        search_paths.append(nested)
        print(f"  [adapt_finmind] 找到巢狀子目錄: {nested}")
    
    csv_files = {}
    for sp in search_paths:
        pattern = os.path.join(sp, "**", "*.csv")
        for csv_path in glob.glob(pattern, recursive=True):
            csv_files[os.path.basename(csv_path)] = csv_path
    
    # 若仍未找到，診斷 /kaggle/input/ 目錄結構
    if len(csv_files) == 0:
        print("  [adapt_finmind] WARNING: glob 未找到 CSV，嘗試診斷...")
        kaggle_input = "/kaggle/input"
        if os.path.exists(kaggle_input):
            print(f"  [adapt_finmind] /kaggle/input 內容:")
            for root, dirs, files in os.walk(kaggle_input):
                level = root.replace(kaggle_input, '').count(os.sep)
                indent = ' ' * (level + 2)
                print(f"{indent}{os.path.basename(root)}/")
                subindent = ' ' * (level + 4)
                for f in files[:10]:
                    print(f"{subindent}{f}")
                if len(files) > 10:
                    print(f"{subindent}... ({len(files)} files total)")
                if level > 3:
                    break
        else:
            print(f"  [adapt_finmind] /kaggle/input 不存在！")
            # 嘗試列出 /kaggle/
            if os.path.exists("/kaggle/"):
                for item in os.listdir("/kaggle/"):
                    print(f"  [adapt_finmind] /kaggle/{item}")
    
    print(f"  [adapt_finmind] 找到 {len(csv_files)} 個 CSV: {list(csv_files.keys())}")'''

if old_walk_block in full:
    full = full.replace(old_walk_block, new_walk_block, 1)
    print("REPLACED: os.walk block with glob + diagnostic")
else:
    print("WARNING: old_walk_block NOT FOUND in source!")
    # 嘗試找到匹配的段落
    idx = full.find('import os')
    if idx > 0:
        print(f"  Found 'import os' at index {idx}")
        print(f"  Context: {full[idx:idx+500]}")

# 重建 notebook source 陣列
new_lines = full.split('\n')
code_cell['source'] = [line + '\n' for line in new_lines]

with open('/home/appuser/twstock_kernel/grpo-regime-aware-factor-training-v6-1.ipynb', 'w') as f:
    json.dump(nb, f, ensure_ascii=False, indent=1)

print("Notebook saved successfully")
print(f"Total source lines: {len(new_lines)}")