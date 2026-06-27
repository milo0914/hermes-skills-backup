# compute_features v3.1 實作記錄 (2026-06-08)

## 概述

在 `ai_dig_money_core.py` 中新增 `compute_features()` 函數，整合 v3.1 的 6 個新特徵（期貨法人OI + 美股指數），並修復小寫→大寫欄位映射問題。

## compute_features 簽名

```python
def compute_features(
    ohlcv_df: pd.DataFrame,
    futures_oi_df: pd.DataFrame = None,
    margin_df: pd.DataFrame = None,
    us_indices_df: pd.DataFrame = None,
    stock_ids: list = None
) -> pd.DataFrame:
```

## 特徵清單 (22 維)

### 原始 16 維 (v2)
ret, liq_score, pressure, fomo, dev, log_vol,
inst_flow, margin_press, five_day_high, vol_breakout,
cvd_proxy, absorption, surf_entry, atr, close_pos, mom_rev

### v3.1 新增 6 維
1. TX_OI — 大台法人淨OI (foreign_net_oi + trust_net_oi)
2. TX_OI_CHG — 大台法人淨OI 5日變化
3. MTX_OI — 小台法人淨OI
4. MTX_OI_CHG — 小台法人淨OI 5日變化
5. NASDAQ_RET — Nasdaq 5日報酬
6. SP500_RET — S&P500 5日報酬
7. DOWJONES_RET — 道瓊 5日報酬

（注：FEATURE_NAMES 使用 TX_INST_NET_OI, MTX_RETAIL_OI, TX_MTX_SPREAD, NASDAQ_CLOSE, SP500_CLOSE, DOWJONES_CLOSE，compute_features 生成的小寫欄位經 rename 映射為大寫）

## 關鍵設計決策

### 1. 小寫→大寫映射

compute_features 生成小寫欄位（Python 慣例），但 FEATURE_NAMES 使用大寫（AlphaGPT VM 需要）。在 zscore 正規化前統一 rename：

```python
_lower_to_upper = {f.lower(): f for f in FEATURE_NAMES}
rename_map = {k: v for k, v in _lower_to_upper.items() if k in g.columns}
g.rename(columns=rename_map, inplace=True)
```

### 2. 期貨 OI broadcast

期貨數據是全市場共用，按 date merge_asof 到個股 df。需確保期貨 df 按 date 排序。

### 3. 美股指數時差

yfinance 回傳美東日期，台股為台北日期。compute_features 中用 shift(1) 處理時差：
- 台股週一開盤 → 對應美股上週五收盤
- 假日不對齊時 ffill 前值

### 4. run_daily_scan 自動 fallback

當 feature_df 未提供時，run_daily_scan 自動呼叫 compute_features：

```python
if feature_df is None or len(feature_df) == 0:
    feature_df = compute_features(df, futures_oi_df, margin_df, us_indices_df)
```

## TWSEDataFetcher Stub

在 ai_dig_money_core.py 中新增了 TWSEDataFetcher 的 stub 類別，提供空 DataFrame fallback：

```python
class TWSEDataFetcher:
    def fetch_futures_oi(self, days=120):
        return pd.DataFrame()
    def fetch_us_indices(self, period='6mo'):
        return pd.DataFrame()
```

完整實作在 `scripts/twse_data_fetcher.py`（FinMind + yfinance）。

## 大段代碼插入方法

因 patch 工具的縮排腐蝕問題（見 pitfall #25），超過 20 行的代碼插入使用 write_file Python 腳本：

```python
# /tmp/insert_compute_features.py
TARGET = "ai_dig_money_core.py"
with open(TARGET) as f:
    lines = f.readlines()

new_code = """
def compute_features(ohlcv_df, futures_oi_df=None, margin_df=None, us_indices_df=None, stock_ids=None):
    ...
"""

# 在目標行號後插入
insert_after = 688  # generate_synth_data 函數結束後
lines = lines[:insert_after] + [new_code + "\n"] + lines[insert_after:]

with open(TARGET, "w") as f:
    f.writelines(lines)
```

插入後必須：
1. `py_compile.compile(TARGET, doraise=True)` 驗證語法
2. 功能測試確認 22 個特徵全部生成
3. 確認 feat_tensor mean≈0, std≈1（zscore 正規化後）

## 驗證結果

- 22/22 特徵欄位生成
- 20/22 特徵有正常 zscore 值（INST_FLOW/MARGIN_PRESS 需 inst/margin 數據）
- feat_tensor mean=-0.0063, std=0.9366（接近標準常態分佈）
- VM reward 從 -5.0 提升至 0.1477

## 相關檔案

- `scripts/ai_dig_money_core.py` — compute_features() 本體（line ~690-850）
- `scripts/grpo_regime_training_kaggle.py` — Kaggle 版本的 TWFeatureEngineer.compute_features（同步參考）
- `scripts/twse_data_fetcher.py` — 完整 TWSEDataFetcher 實作
- `references/grpo-zero-convergence-fix.md` — 根因 B（大小寫映射）修復記錄
