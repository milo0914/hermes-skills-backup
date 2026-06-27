# 22 因子資料架構對應表 (v3.1, 2026-06-11 盤點)

## 概述

GRPO 訓練模型的輸入為 22 維因子向量（zscore normalized），由 StackVM 執行公式後產生信號。此文件追蹤每個因子從原始資料來源到訓練模型輸入的完整路徑，以及識別的缺口。

## 因子 → 資料來源對應表 (2026-06-12 v2 verified)

⚠️ NOTE: This table was compiled by analyzing the dataset and code
separately. A live end-to-end test confirmed dataset format is correct
but code loading may have bugs (see "Critical Bug: adapt_finmind_data
futures_oi loading path" below). ALWAYS verify data flows end-to-end
rather than trusting documentation alone.

| # | 因子名 | 資料來源 CSV (Dataset v2) | CSV 實際欄位名 | compute_features merge 方式 | RegimeConfig 權重 | 狀態 |
|---|--------|--------------------------|---------------|----------------------------|-------------------|------|
| 1 | RET | price_ohlcv.csv | close | g["ret"] = log(close/close.shift(1)) | ✅ per-regime | ✅ |
| 2 | LIQ_SCORE | price_ohlcv.csv | volume | volume / rolling mean | ✅ per-regime | ✅ |
| 3 | PRESSURE | inst_flow.csv | total_net, volume | total_net / volume | ✅ per-regime | ✅ |
| 4 | FOMO | price_ohlcv.csv | volume | volume.pct_change(5) | ✅ per-regime | ✅ |
| 5 | DEV | price_ohlcv.csv | close | (close - MA20) / MA20 | ✅ per-regime | ✅ |
| 6 | LOG_VOL | price_ohlcv.csv | volume | log(volume) | ✅ per-regime | ✅ |
| 7 | INST_FLOW | inst_flow.csv | total_net | rolling sum(total_net) / volume | ✅ per-regime | ✅ |
| 8 | MARGIN_PRESS | margin.csv | margin_balance | pct_change(5) | ✅ per-regime | ✅ |
| 9 | FIVE_DAY_HIGH | price_ohlcv.csv | close, high | close > high.rolling(5).max() | ✅ per-regime | ✅ |
| 10 | VOL_BREAKOUT | price_ohlcv.csv | volume | volume > MA20*1.5 | ✅ per-regime | ✅ |
| 11 | CVD_PROXY | price_ohlcv.csv | close, open, high, low, volume | (c-o)/(h-l+eps)*volume, rolling | ✅ per-regime | ✅ |
| 12 | ABSORPTION | price_ohlcv.csv | close, open, high, low, volume | 買單湧入但價格不漲偵測 | ✅ per-regime | ✅ |
| 13 | SURF_ENTRY | price_ohlcv.csv | close, high, low | 關鍵價位切入信號 | ✅ per-regime | ✅ |
| 14 | ATR | price_ohlcv.csv | high, low, close | True Range 14日均值 | ✅ per-regime | ✅ |
| 15 | CLOSE_POS | price_ohlcv.csv | close, high, low | (close-low)/(high-low+eps) | ✅ per-regime | ✅ |
| 16 | MOM_REV | price_ohlcv.csv | close | 5日動量反轉信號 | ✅ per-regime | ✅ |
| 17 | TX_INST_NET_OI | futures_oi.csv | inst_net_oi (TX) | TX pivot -> merge on date | ❌ fallback=1.0 | ⚠️ CSV ✅ 但載入程式碼有 bug |
| 18 | MTX_RETAIL_OI | futures_oi.csv | retail_net_oi (MTX) | MTX pivot -> merge on date | ❌ fallback=1.0 | ⚠️ CSV ✅ 但載入程式碼有 bug |
| 19 | TX_MTX_SPREAD | futures_oi.csv | inst_net_oi (TX+MTX) | (TX inst - MTX inst) on date | ❌ fallback=1.0 | ⚠️ CSV ✅ 但載入程式碼有 bug |
| 20 | NASDAQ_CLOSE | us_indices.csv | close (index_name="Nasdaq") | pivot wide -> merge + shift(1) | ❌ fallback=1.0 | ✅ CSV + 載入程式碼都正確 |
| 21 | SP500_CLOSE | us_indices.csv | close (index_name="SP500") | pivot wide -> merge + shift(1) | ❌ fallback=1.0 | ✅ |
| 22 | DOWJONES_CLOSE | us_indices.csv | close (index_name="DowJones") | pivot wide -> merge + shift(1) | ❌ fallback=1.0 | ✅ |

## Critical Bug: adapt_finmind_data futures_oi 載入路徑錯誤 (2026-06-12 驗證)

**Bug 描述:**
adapt_finmind_data() 載入 futures_oi.csv 時，檢查 `if "oi" in raw.columns` —
但 Dataset v2 的 futures_oi.csv 已經是長格式，欄位名為 `inst_net_oi`,
`retail_net_oi`, `Foreign_Investor_net_oi` 等，沒有 `oi` 這個欄位。
條件不成立 → futures_oi_df = None → GRPO 訓練用不到任何期貨因子。

**根因:**
adapt_finmind_data 是為舊版寬格式 (oi, mtx_oi, tx_mtx_spread 欄位) 寫的。
Dataset v2 已升級為長格式，但載入程式碼未同步更新。

**驗證:**
- futures_oi.csv 有 inst_net_oi (TX 1337 rows, 全非零) and retail_net_oi (TX 1337 rows, 全非零) ✅
- 但 adapt_finmind_data 找不到 "oi" 欄位，跳過載入 ❌
- compute_features() 中對期貨 OI 的 pivot+merge 邏輯本身是對的（用 foi[futures_id=="TX"] 拆分）

**us_indices 載入沒問題**: adapt_finmind_data 檢查 `if "index_name" in raw.columns: us_indices_df = raw`，Dataset v2 已有 index_name，所以正確載入。

**修復方向**: 在 adapt_finmind_data() 中新增長格式偵測:
if "oi" in raw.columns:
    # 舊版寬格式路徑
    ...
elif "inst_net_oi" in raw.columns:
    # 新版長格式 - 直接用
    futures_oi_df = raw.copy()
else:
    # 未知格式
    pass

## 識別的 5 個缺口 (2026-06-11, updated 2026-06-12)

### 缺口 1: RegimeConfig.feature_weights 僅覆蓋 16/22 因子 [Critical]
*(unchanged)*

### 缺口 2: (RESOLVED 2026-06-12) futures_oi.csv 已有法人持倉分向
Dataset v2 的 futures_oi.csv 已包含 Foreign_Investor_net_oi, Investment_Trust_net_oi,
Dealer_self_net_oi, Dealer_Hedging_net_oi, retail_net_oi, inst_net_oi 共 8 欄。
**真正的問題**是 adapt_finmind_data 的載入邏輯未更新（見上方 Critical Bug）。

### 缺口 3-5: *(unchanged, medium/low priority)*

## 資料流向完整路徑

```
Raw CSV → TWSEDataFetcher / yfinance / FinMind
  ↓
compute_features(stock_id, g, inst_df, margin_df, futures_oi_df, us_indices_df)
  ├─ merge inst_df → INST_FLOW, PRESSURE
  ├─ merge margin_df → MARGIN_PRESS
  ├─ merge futures_oi_df → TX_INST_NET_OI, MTX_RETAIL_OI, TX_MTX_SPREAD
  ├─ merge us_indices_df (shift1) → NASDAQ_CLOSE, SP500_CLOSE, DOWJONES_CLOSE
  ├─ lower→upper rename (pitfall #29)
  ├─ rolling zscore normalization (window=60, expanding fallback)
  └─ keep_cols filter → feature_df (date, stock_id, 22因子)
  ↓
feat_tensor = feature_df[ALL_FEATURE_NAMES].values  → shape (T, 22)
  ↓
StackVM.execute(formula_tokens, feat_tensor[t]) → signal (scalar)
  ↓
Backtest: signal * fwd_returns → reward
  ↓
GRPO: group reward → advantages → REINFORCE loss → Transformer update
```
