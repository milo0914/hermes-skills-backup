# Kaggle Dataset 掛載路徑深度問題

版本：v1.0（2026-06-09）

## 問題描述

Kaggle `kernel-metadata.json` 中的 `dataset_sources` 引用 dataset slug 後，kernel 執行時資料掛載到 `/kaggle/input/`，但**實際路徑為三層巢狀結構**：

```
/kaggle/input/datasets/{owner}/{dataset-slug}/{files}
```

而非文件常載的：

```
/kaggle/input/{dataset-slug}/{files}
```

## 實測結果

使用 diagnostic kernel `mhhuang14/diag-kaggle-input-path` 確認：

```
/kaggle/input/ contents: ['datasets']
/kaggle/input/datasets/ contents: ['mhhuang14']
/kaggle/input/datasets/mhhuang14/ contents: ['twstock-grpo-training-data']
/kaggle/input/datasets/mhhuang14/twstock-grpo-training-data/ contents: ['twstock_daily.csv']
```

完整路徑：`/kaggle/input/datasets/mhhuang14/twstock-grpo-training-data/twstock_daily.csv`

## 根因

舊版 Kaggle 環境（2024 以前）可能使用 `/kaggle/input/{slug}/` 路徑。目前（2026）Kaggle 改為 `/kaggle/input/datasets/{owner}/{slug}/` 三層結構，但官方文件未同步更新。

## 修復方案

### 方案 A：os.walk 遞迴搜尋（推薦，最穩健）

```python
import os

def find_in_kaggle_input(filename, base='/kaggle/input/'):
    """遞迴搜尋 /kaggle/input/ 下的指定檔案"""
    for root, dirs, files in os.walk(base, topdown=True):
        if filename in files:
            return os.path.join(root, filename)
    return None

csv_path = find_in_kaggle_input('twstock_daily.csv')
if csv_path:
    print(f"從 Kaggle Dataset 載入: {csv_path}")
    df = pd.read_csv(csv_path)
else:
    print("未找到真實數據，fallback 到合成數據")
```

優點：不依賴路徑深度，兼容未來 Kaggle 路徑變更。

### 方案 B：glob 搜尋

```python
import glob

matches = glob.glob('/kaggle/input/**/twstock_daily.csv', recursive=True)
if matches:
    csv_path = matches[0]
```

### 方案 C：硬編碼三層路徑（不推薦）

```python
csv_path = '/kaggle/input/datasets/mhhuang14/twstock-grpo-training-data/twstock_daily.csv'
```

缺點：owner/slug 變更時需手動更新，Kaggle 再次改路徑結構時失效。

## 影響範圍

此問題導致 GRPO 訓練 kernel v3.1 至 v5 反覆 fallback 到合成數據（因 `os.listdir` 只看到 `datasets/` 目錄，找不到 CSV），14/22 因子恆為 0。用戶非常沮喪（「為什麼這次的v3.1仍然是使用合成數據！！！？」）。

v3.3 修復：改用 `os.walk` 遞迴搜尋，成功載入真實 FinMind 數據。

## 診斷方式

在 notebook 開頭加入：

```python
import os
for root, dirs, files in os.walk('/kaggle/input/'):
    print(f"  {root}/ → {files}")
```

確認實際掛載路徑和深度。
