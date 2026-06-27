# Kaggle v6.4 Kernel Path Fix (2026-06-13)

## 問題
v6.3 kernel 執行失敗：`adapt_finmind_data` 找不到 CSV 檔案，報錯 `[FATAL] 找不到真實數據！`

## 根因
Kaggle dataset 掛載路徑不是預期的 `/kaggle/input/twstock-v6-0-real-data-20stocks-5y/`，而是：
```
/kaggle/input/datasets/mhhuang14/twstock-v6-0-real-data-20stocks-5y/
```

Log 確認的掛載結構：
```
/kaggle/input/
  datasets/
    mhhuang14/
      twstock-v6-0-real-data-20stocks-5y/
        price_ohlcv.csv
        margin.csv
        us_indices.csv
        futures_oi.csv
        inst_flow.csv
```

## 修復
修改 `adapt_finmind_data(data_path: str)` → **完全不再依賴 `data_path` 參數**，改為：
1. 自動掃描 `/kaggle/input/` 下所有 `.csv` 檔案（`os.walk`）
2. 依檔案名關鍵字分類：`price_ohlcv`/`ohlcv`/`twstock_daily`、`inst_flow`/`inst`、`margin`、`futures_oi`、`us_indices`/`us_index`/`nasdaq`/`sp500`/`dowjones`
3. 若 `/kaggle/input/` 掃不到，fallback 掃描傳入的 `data_path`

程式碼關鍵段（notebook cell 1, 行 ~18382）：
```python
def adapt_finmind_data(data_path: str):
    import os, glob
    csv_files = {}
    kaggle_input = "/kaggle/input"
    if os.path.exists(kaggle_input):
        for root, dirs, files in os.walk(kaggle_input):
            for f in files:
                if f.endswith('.csv'):
                    # 依檔名關鍵字分類
                    ...
    # fallback to data_path
    if len(csv_files) == 0 and os.path.exists(data_path):
        ...
```

`main()` 中：
```python
data_path = "/kaggle/input"  # 改成根目錄，adapt_finmind_data 會自動掃描
result = adapt_finmind_data(data_path)
```

## Kernel 版本
- **v6.4**: `mhhuang14/twstock-grpo-regime-aware-factor-training-v6-4`
- **Status**: RUNNING (CPU fallback on Tesla P100, sm_60 < sm_70)
- **Dataset source**: `mhhuang14/twstock-v6-0-real-data-20stocks-5y` (已正確掛載)

## 驗證點
- [x] 自動掃描 `/kaggle/input/` 所有 CSV
- [x] 不再硬編碼 dataset slug
- [x] Dataset 掛載正確（log 確認 5 個 CSV 存在）
- [ ] 訓練完成並輸出 `training_report.json`

## 相關檔案
- Notebook: `/home/appuser/twstock_kernel/grpo-regime-aware-factor-training-v6-1.ipynb`
- Metadata: `/home/appuser/twstock_kernel/kernel-metadata.json` (slug v6.4)
- Kernel URL: https://www.kaggle.com/code/mhhuang14/twstock-grpo-regime-aware-factor-training-v6-4