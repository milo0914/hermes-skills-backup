# twstock 資料來源驗證報告 (2026-06-07)

## 測試環境

- Python 3.11, Hermes sandbox
- twstock==1.3.1 (pip install)

## 歷史股價模組 — 可用

```python
import twstock
stock = twstock.Stock('2330')
data = stock.fetch(2024, 1)  # 2024年1月台積電
# 回傳 Data 物件，欄位：capacity, change, date, high, low, open, price, transaction
# 可逐月抓取，無需 API key
```

驗證日期：2024-01, 2024-06 皆成功。

## 即時報價模組 — 失效

```python
from twstock import realtime
result = realtime.get('2330')
# 回傳: {'success': False, 'info': 'Unknown error'}
```

原因：證交所即時報價端點已變更，twstock 專案未跟進更新。自 2025 年起不可用。

## 三大法人模組 — 不存在

```python
import twstock
twstock.twsbe  # AttributeError: module 'twstock' has no attribute 'twsbe'
```

v1.3.1 不包含任何法人買賣超資料模組。

## 替代方案對照

| 來源 | 歷史 OHLCV | 即時報價 | 三大法人 | 免費 | 需 API key | 穩定性 |
|------|-----------|---------|---------|------|-----------|--------|
| twstock 歷史模組 | ✓ | ✗ | ✗ | ✓ | ✗ | 中（端點偶爾變動） |
| twstock 即時模組 | — | ✗ | — | ✓ | ✗ | 失效 |
| 證交所官網 CSV | ✓(盤後) | ✗ | ✓ | ✓ | ✗ | 高 |
| yfinance (2330.TW) | ✓ | ~15min延遲 | ✗ | ✓ | ✗ | 中 |
| Goodinfo 爬蟲 | ✓ | ✓ | ✓ | ✓ | ✗ | 低（反爬） |

## 證交所官網 CSV 格式

每日收盤資料：
```
https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date=YYYYMMDD&response=csv&_=timestamp
```

三大法人買賣超：
```
https://www.twse.com.tw/rwd/zh/fund/T86?date=YYYYMMDD&response=csv&_=timestamp
```

注意：CSV 含中文欄位，需處理編碼與合併儲存格。

## fetch_close_data() 標準化格式

已整合 twstock 歷史模組，回傳 pd.DataFrame：

```
欄位: ['date', 'open', 'high', 'low', 'close', 'volume']
date: ISO 8601 (YYYY-MM-DD)
volume: 單位「張」
```

參數：stock_id (str), start_date (YYYY-MM-DD), end_date (YYYY-MM-DD)
