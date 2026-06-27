# Kaggle Dataset Mount Path Auto-Scan Pattern (2026-06-13)

## 問題
Kaggle dataset 掛載路徑不是預期的 `/kaggle/input/{slug}/`，而是：
```
/kaggle/input/datasets/{owner}/{slug}/
```
導致硬編碼 `data_path = "/kaggle/input/twstock-v6-0-real-data-20stocks-5y"` 找不到檔案。

## 根因
Kaggle 在 kernel 執行時，會將 dataset source 掛載在 `/kaggle/input/datasets/{owner}/{slug}/`，slug 本身不直接出現在 `/kaggle/input/` 下。

## 解決方案：自動掃描 `/kaggle/input/` 遞迴尋找所有 CSV

```python
def adapt_finmind_data(data_path: str):
    """
    從 Kaggle dataset 載入真實台股數據 — 自動掃描 /kaggle/input/ 下所有 CSV
    不再依賴硬編碼 slug 路徑
    """
    import os, glob
    
    csv_files = {}
    kaggle_input = "/kaggle/input"
    
    # 1. 優先掃描 /kaggle/input/ 所有子目錄
    if os.path.exists(kaggle_input):
        for root, dirs, files in os.walk(kaggle_input):
            for f in files:
                if f.endswith('.csv'):
                    fname = f.lower()
                    full_path = os.path.join(root, f)
                    # 依檔名關鍵字分類
                    if any(k in fname for k in ['price_ohlcv', 'ohlcv', 'twstock_daily']):
                        csv_files['ohlcv'] = full_path
                    elif any(k in fname for k in ['inst_flow', 'inst']):
                        csv_files['inst'] = full_path
                    elif 'margin' in fname:
                        csv_files['margin'] = full_path
                    elif 'futures_oi' in fname:
                        csv_files['futures'] = full_path
                    elif any(k in fname for k in ['us_indices', 'us_index', 'nasdaq', 'sp500', 'dowjones']):
                        csv_files['us'] = full_path
    
    # 2. Fallback: 掃描傳入的 data_path (兼容舊版)
    if len(csv_files) == 0 and os.path.exists(data_path):
        for root, dirs, files in os.walk(data_path):
            for f in files:
                if f.endswith('.csv'):
                    # 同樣分類邏輯...
                    pass
    
    # 3. 讀取各類別 CSV...
```

## 關鍵點
1. **完全不依賴 `data_path` 參數** — 改為根目錄掃描
2. **檔名關鍵字分類** — 兼容新舊命名慣例 (`price_ohlcv.csv` / `twstock_daily.csv` / `ohlcv.csv`)
3. **診斷輸出** — 找不到時印出 `/kaggle/input/` 完整樹狀結構，便於除錯
4. **向後相容** — 保留 `data_path` fallback

## 驗證 Log (v6.4 成功)
```
[adapt_finmind] 找到 5 個 CSV: ['price_ohlcv.csv', 'margin.csv', 'us_indices.csv', 'futures_oi.csv', 'inst_flow.csv']
[adapt_finmind] 載入 OHLCV: 24385 rows, 20 stocks
[adapt_finmind] inst: pre-mapped (26360 rows)
[adapt_finmind] margin: pre-mapped (26360 rows)
[adapt_finmind] futures: long format (2674 rows, 2 contracts)
[adapt_finmind] us: long format (3765 rows, 3 indices)
```

## 適用場景
- 任何需讀取 Kaggle dataset source 的 kernel
- Dataset slug 或 owner 可能變更時
- 多個 dataset source 混用時