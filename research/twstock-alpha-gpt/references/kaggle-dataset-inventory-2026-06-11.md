# Kaggle Dataset 真實資料清單 (2026-06-11 盤點)

## Dataset: mhhuang14/twstock-grpo-training-data

### 檔案清單

| 檔案 | 大小 | 筆數 | 日期範圍 | 股票/標的 | 欄位 |
|------|------|------|----------|-----------|------|
| twstock_daily.csv | 245KB | 3,372 | 2022-01-03 ~ 2025-06-30 | 2330/2454/1301/2882 | date, stock_id, stock_name, open, high, low, close, change, volume, turnover |
| inst_data.csv | 743KB | 16,860 | 2022-01-03 ~ 2025-06-30 | 4檔 x 5法人身份 = 4,215/檔 | date, stock_id, buy, name, sell |
| margin_data.csv | 244KB | 3,372 | 2022-01-03 ~ 2025-06-30 | 同上4檔 | date, stock_id, MarginPurchaseBuy/Sell/Balance, ShortSaleBuy/Sell/Balance 等16欄 |
| futures_oi.csv | 622KB | 11,813 | 2022-01-03 ~ 2025-06-30 | TX (大台台指期, 多月份合約) | date, futures_id, contract_date, oi, futures_close, futures_volume, mtx_oi, mtx_close, tx_mtx_spread |
| us_indices.csv | 48KB | 874 | 2022-01-03 ~ 2025-06-27 | NASDAQ/SP500/DOWJONES | date, NASDAQ, SP500, DOWJONES, NASDAQ_MOM5, SP500_MOM5, DOWJONES_MOM5 |
| twstock_training_data.csv | 1000 rows | 1,000 | 合成 | 4檔 (2330/2454/1301/2882) | ticker, date, open, high, low, close, volume (可淘汰) |

### inst_data 三大法人分類

| name 值 | 中文名 | 說明 |
|---------|--------|------|
| Foreign_Investor | 外資 | 最大主力 |
| Foreign_Dealer_Self | 外資自營商 | 通常量極小 |
| Investment_Trust | 投信 | 中型主力 |
| Dealer_self | 自營商(自行買賣) | 短線 |
| Dealer_Hedging | 自營商(避險) | 避險部位 |

每檔股票每日有 5 筆記錄（5 種法人身份），buy/sell 為絕對金額（股數）。

### 關鍵缺失

1. **futures_oi.csv 沒有法人持倉分向資料** — 只有 TX 總 OI + 小台 OI + 價差，缺少「大台法人淨多/淨空 OI」和「小台散戶 OI」。v3.1 需要的 `TX_INST_NET_OI` 和 `MTX_RETAIL_OI` 因子無法從此 CSV 直接計算。需要額外抓取期交所三大法人期貨持倉資料（FinMind `taiwan_futures_institutional_investors` API）。

2. **twstock_training_data.csv 是合成資料** — 只有 7 欄 OHLCV，缺少法人/融資/期貨/美股欄位，可淘汰改用真實資料。

### 建議行動

1. 用 FinMind API 抓取期貨法人持倉資料，合併到 futures_oi.csv
2. 淘汰 twstock_training_data.csv，改用 twstock_daily.csv + inst_data.csv + margin_data.csv + futures_oi.csv + us_indices.csv 重製訓練 dataset
3. 重製後用 `kaggle datasets version` 上傳新版 dataset
4. v6.0 kernel 綁定新版 dataset 推送訓練
