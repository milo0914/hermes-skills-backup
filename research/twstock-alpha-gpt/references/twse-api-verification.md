# TWSE 官方 API 驗證記錄 (2026-06-07)

## 驗證結果摘要

| API | 端點路徑 | 狀態 | 每日筆數 | 欄位 |
|-----|---------|------|---------|------|
| T86 三大法人 | `/rwd/zh/fund/T86` | ✅ 可用 | ~11,638 (selectType=ALL) | stock_id, foreign_net, trust_net, dealer_self_net, dealer_hedge_net, total_net |
| MI_MARGN 融資融券 | `/rwd/zh/marginTrading/MI_MARGN` | ✅ 可用 | ~1,018 (selectType=STOCK) | stock_id, margin_buy, margin_sell, margin_balance, short_buy, short_sell, short_balance |
| TWT38U 三大法人(舊) | `/rwd/zh/fund/TWT38U` | ✅ 可用 | ~1,210 | 9 欄位但欄位名稱不直觀（3組買/賣/超） |

## 詳細端點

### T86 三大法人買賣超日報

```
GET https://www.twse.com.tw/rwd/zh/fund/T86?date=YYYYMMDD&response=json&selectType=ALL
```

- `date`: 交易日期 (YYYYMMDD)
- `response`: json 或 csv
- `selectType`: ALL=全部個股 (預設僅回傳 8 筆)
- 回傳 JSON 結構: `{"stat": "OK", "data": [[row1], [row2], ...], "fields": [...]}`
- fields 順序: 證券代號, 證券名稱, 外資買進, 外資賣出, 外資買賣超, 投信買進, 投信賣出, 投信買賣超, 自營商買賣超(自行), 自營商買賣超(避險), 三大法人買賣超合計
- 數值含逗號 (如 "1,234,567")，需去除後轉 int
- 2330 (台積電) 實測資料: foreign_net=-9860, trust_net=1555, dealer_self_net=-92, dealer_hedge_net=4, total_net=-8393 (2025-05-23)

### MI_MARGN 融資融券餘額

```
GET https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?date=YYYYMMDD&response=json&selectType=STOCK
```

- `selectType=STOCK`: 個股層級 (預設為彙總)
- fields: 證券代號, 譯券名稱, 融資買進, 融資賣出, 融資餘額, 融資限額, 融券買進, 融券賣出, 融券餘額, 融券限額
- 2330 實測: margin_balance=46633, short_balance=3743 (2025-05-23)

### 不適用端點

- `/exchangeReport/BWTB4` — 404 (舊版已下線)
- `/rwd/zh/fund/TWT4U` — 僅回傳 8 筆 (同 T86 不加 selectType)
- `/rwd/zh/fund/STOCKDAY` — 日收盤行情（非法人資料）

## 速率與穩定性

- 連續 8 個交易日抓取 (2025-05-14~05-23) 全部成功，零失敗
- 建議間隔 ≥ 3 秒 (twse_data_fetcher.py 內建 sleep=3)
- 單日 T86 ALL 資料量 ~2MB (JSON)
- TWSE 有可能因流量限制返回非 JSON，fetcher 內建自動重試 3 次

## 欄位名稱對照 (v2 → v3)

| v2 欄位 | v3 欄位 (TWSEDataFetcher) | 說明 |
|---------|--------------------------|------|
| `foreign_buy` | `foreign_net` | 外資買賷超 (net = 買進-賣出) |
| `trust_buy` | `trust_net` | 投信買賷超 |
| `dealer_buy` | `dealer_self_net` + `dealer_hedge_net` | 自營商分為自行+避險 |
| N/A | `total_net` | 三大法人合計 |
| N/A | `margin_balance` | 融資餘額 (v3 新增) |
| N/A | `short_balance` | 融券餘額 (v3 新增) |

## 實作腳本

所有邏輯封裝在 `scripts/twse_data_fetcher.py`，提供：
- `fetch_inst_daily(date)` / `fetch_inst_range(start, end)` — 法人資料
- `fetch_margin_daily(date)` / `fetch_margin_range(start, end)` — 融資融券
- `fetch_full_history(stocks, start, end)` — 一次下載 + 合併
- `generate_kaggle_dataset(stocks, start, end, output_dir)` — 生成 Kaggle 訓練集
