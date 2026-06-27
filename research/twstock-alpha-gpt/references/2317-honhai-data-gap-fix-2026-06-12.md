# 2317 Hon Hai Data Gap — Margin + Inst Flow 補抓記錄

## 問題
2317 (鴻海) 是 20 檔 Dataset 中唯一在 v1 缺少 OHLCV 的股票。
OHLCV 補完後，margin.csv 和 inst_flow.csv 仍然沒有 2317 的資料。

## 根因
原始 kernel (twstock-v6-0-data-fetch-20-stocks-5y-v2) 的資料抓取範圍裡沒有包含 2317，
margin 和 inst_flow 的 CSV 是 kernel 執行時一次性生成的，新股票需額外補抓。

## 補抓步驟（成功經驗）

### Step 1: 確認缺失
```
m = pd.read_csv('margin.csv'); print(2317 in m.stock_id.unique())
i = pd.read_csv('inst_flow.csv'); print(2317 in i.stock_id.unique())
```

### Step 2: 嘗試 TWSE 官方 API（失敗）
- MI_MARGN: 對 2317 回傳「沒有符合條件的資料」
- MI_QFIIS: 同上
- 原因：TWSE 這些 API 只在該股票當月有活動時才回傳資料

### Step 3: 改用 FinMind REST API（成功）
- `TaiwanStockMarginPurchaseShortSale`: 抓到 1318 rows (2021-01-04 ~ 2026-06-11)
- `TaiwanStockInstitutionalInvestorsBuySell`: 抓到 1318 rows (2021-01-04 ~ 2026-06-12)
- 注意 FinMind 免費版每日有調用配額（402 Payment Required）

### Step 4: 欄位映射（最關鍵）
FinMind 回傳的欄位名稱與 CSV 格式不同：

**Margin mapping:**
- MarginPurchaseBuy → margin_buy
- MarginPurchaseSell → margin_sell
- MarginPurchaseCashRepayment → margin_cash_repay
- ShortSaleBuy → short_buy
- ShortSaleSell → short_sell
- ShortSaleCashRepayment → short_cash_repay
- MarginPurchaseTodayBalance - MarginPurchaseYesterdayBalance → margin_change
- MarginPurchaseTodayBalance → margin_balance
- ShortSaleTodayBalance - ShortSaleYesterdayBalance → short_change
- ShortSaleTodayBalance → short_balance

**Inst Flow mapping (pivot by name):**
FinMind 回傳的是 flat format: date, stock_id, buy, name, sell
→ pivot_table(index=['date','stock_id'], columns='name', values='net')
→ net = buy - sell
→ 產生 columns: date, stock_id, Dealer_Hedging, Dealer_self, Foreign_Dealer_Self, Foreign_Investor, Investment_Trust, total_net

### Step 5: 合併與驗證
合併後確認三大 CSV 都有 2317 的行數 > 0：
- price_ohlcv.csv: 1319 rows (TWSE STOCK_DAY)
- margin.csv: 1318 rows (FinMind)
- inst_flow.csv: 1318 rows (FinMind)

## 教訓
1. 每次在 Dataset 新增股票後，必須逐一檢查 margin.csv + inst_flow.csv + price_ohlcv.csv 的 stock_id 完整度
2. FinMind 的每日配額有限（約 80 頁/天），補抓大檔需分批
3. TWSE STOCK_DAY 是最穩定的 OHLCV 源，但 margin/inst 需靠 FinMind
4. Inst flow 的 FinMind raw data 需 pivot，margin raw data 需 rename + calculate derived columns