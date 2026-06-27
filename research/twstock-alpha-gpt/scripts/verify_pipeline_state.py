#!/usr/bin/env python3
"""
Verify TWStock GRPO v6.8 pipeline state:
- Dataset availability on Kaggle
- Local CSV integrity
- Kernel metadata consistency
- Key file existence
"""
import os
import json
import subprocess
import pandas as pd
from pathlib import Path

def run_cmd(cmd, capture=True):
    result = subprocess.run(cmd, shell=True, capture_output=capture, text=True)
    return result.stdout.strip(), result.stderr.strip(), result.returncode

def check_local_files():
    print("=" * 60)
    print("本地檔案檢查")
    print("=" * 60)
    
    files_to_check = {
        "v6.8 Notebook": "/home/appuser/twstock_v68_kernel/twstock-grpo-regime-aware-factor-training-v6-8.ipynb",
        "v6.8 Metadata": "/home/appuser/twstock_v68_kernel/kernel-metadata.json",
        "v6.1 Notebook": "/home/appuser/twstock_kernel/grpo-regime-aware-factor-training-v6-1.ipynb",
        "v6.1 Metadata": "/home/appuser/twstock_kernel/kernel-metadata.json",
        "Data Fetch Kernel": "/home/appuser/twstock_kernel/twstock-v6-0-data-fetch-20-stocks-5y-v2.py",
        "Fix adapt_finmind": "/home/appuser/twstock_kernel/fix_adapt_finmind.py",
        "Dataset CSV dir": "/home/appuser/twstock_v6_data/",
        "Dataset Metadata": "/home/appuser/twstock_v6_data/dataset-metadata.json",
        "Kernel Output": "/home/appuser/twstock_kernel_out/twstock_v6_data/",
        "Backup": "/home/appuser/twstock_v6_data_backup/",
    }
    
    for name, path in files_to_check.items():
        exists = os.path.exists(path)
        size = os.path.getsize(path) if exists and os.path.isfile(path) else "DIR" if exists and os.path.isdir(path) else "N/A"
        status = "✓" if exists else "✗"
        print(f"  {status} {name:25s}: {path} ({size})")
    
    # Check CSV files
    print("\n  CSV 檔案詳細:")
    csv_dir = "/home/appuser/twstock_v6_data"
    for f in ["price_ohlcv.csv", "inst_flow.csv", "margin.csv", "futures_oi.csv", "us_indices.csv"]:
        p = os.path.join(csv_dir, f)
        if os.path.exists(p):
            df = pd.read_csv(p)
            stocks = df["stock_id"].nunique() if "stock_id" in df.columns else "N/A"
            print(f"    ✓ {f:20s}: {len(df):>6} rows, {df.shape[1]} cols, stocks={stocks}")
        else:
            print(f"    ✗ {f:20s}: NOT FOUND")

def check_kaggle_dataset():
    print("\n" + "=" * 60)
    print("Kaggle Dataset 檢查")
    print("=" * 60)
    
    out, err, code = run_cmd("kaggle datasets list -u mhhuang14 | grep twstock-v6-0-real-data")
    if code == 0 and out:
        print(f"  ✓ Dataset 存在: {out}")
    else:
        print(f"  ✗ Dataset 不存在或查詢失敗")
        if err: print(f"    Error: {err}")

def check_kaggle_kernels():
    print("\n" + "=" * 60)
    print("Kaggle Kernels 檢查")
    print("=" * 60)
    
    out, err, code = run_cmd("kaggle kernels list -u mhhuang14 | grep -E '(grpo|twstock-v6-0-data)'")
    if code == 0 and out:
        for line in out.split("\n"):
            print(f"  {line}")
    else:
        print(f"  查詢失敗: {err}")

def check_kernel_metadata():
    print("\n" + "=" * 60)
    print("Kernel Metadata 一致性檢查")
    print("=" * 60)
    
    meta_files = {
        "twstock_kernel (v6.8指向)": "/home/appuser/twstock_kernel/kernel-metadata.json",
        "twstock_v68_kernel (pull下來)": "/home/appuser/twstock_v68_kernel/kernel-metadata.json",
    }
    
    for name, path in meta_files.items():
        if os.path.exists(path):
            with open(path) as f:
                meta = json.load(f)
            print(f"  {name}:")
            print(f"    id: {meta.get('id')}")
            print(f"    title: {meta.get('title')}")
            print(f"    code_file: {meta.get('code_file')}")
            print(f"    dataset_sources: {meta.get('dataset_sources')}")
        else:
            print(f"  {name}: NOT FOUND")

def main():
    print("TWStock GRPO v6.8 Pipeline 狀態驗證")
    print("Timestamp:", pd.Timestamp.now())
    
    check_local_files()
    check_kaggle_dataset()
    check_kaggle_kernels()
    check_kernel_metadata()
    
    print("\n" + "=" * 60)
    print("驗證完成")
    print("=" * 60)

if __name__ == "__main__":
    main()