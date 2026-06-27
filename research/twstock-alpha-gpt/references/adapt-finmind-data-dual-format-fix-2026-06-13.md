# adapt_finmind_data 雙格式修復 (2026-06-13)

## 問題
Kaggle Dataset v2 (mhhuang14/twstock-v6-0-real-data-20stocks-5y) 的 5 個 CSV 採用新長格式，但 adapt_finmind_data 的載入邏輯是寫給舊格式的，導致期貨 OI / 法人 / 融資資料無法載入。

## 根因分析

### futures_oi.csv — 最關鍵的 bug
**舊格式** (程式碼期待的): date, oi, mtx_oi, contract_date (寬格式，oi 是總量，需 60/40 近似拆分)
**新格式** (Dataset v2 實際的): date, futures_id, Foreign_Investor_net_oi, ..., inst_net_oi, retail_net_oi (長格式，TX+MTX 各一列，含真實法人/散戶拆分)

程式碼第 2034 行檢查 `if "oi" in raw.columns` — 新格式無 `oi` 欄位 → **條件不成立 → futures_oi_df = None** → 整份期貨資料被靜默丟棄。

### inst_flow.csv
**舊格式**: date, stock_id, name (投資人類型), buy, sell (長格式，需 pivot)
**新格式**: date, stock_id, Foreign_Investor, Dealer_self, ..., total_net (預先 pivot)

程式碼期待 `name` 欄位做 pivot_table → 找不到 → inst_df = None。

### margin.csv
**舊格式**: date, stock_id, MarginPurchaseTodayBalance, MarginPurchaseBuy (FinMind 原始欄位)
**新格式**: date, stock_id, margin_balance, margin_buy, short_balance (已對應)

程式碼期待 FinMind 欄位名 → 找不到 → margin_df = None。

### price_ohlcv.csv — 檔名問題
舊程式碼硬編碼讀取 `twstock_daily.csv`，但 Dataset v2 檔名為 `price_ohlcv.csv`。

## 修復方案 (三處修復 + compute_features 三處修復 + CPU regime fallback)

### 修復 1: adapt_finmind_data futures_oi 載入
```python
# 格式偵測邏輯 (按優先順序):
# 1. 新長格式: "futures_id" in raw.columns and "inst_net_oi" in raw.columns
#    → 直接選取 [date, futures_id, inst_net_oi, retail_net_oi]
# 2. 舊寬格式: "oi" in raw.columns
#    → 原有的 near-month 選取 + 60/40 近似拆分
# 3. Fallback: 第一個數值欄位 * 0.6 近似
```

### 修復 2: adapt_finmind_data inst_flow 載入
```python
# 格式偵測:
# 1. 預先 pivot: 檢查是否有 Foreign_Investor 等欄位且無 name 欄位
#    → 直接 rename: Foreign_Investor→foreign_net, 計算 total_net
# 2. 舊長格式: 有 name 欄位
#    → 原有的 pivot_table 邏輯
# 3. 未知格式: 直接使用
```

### 修復 3: adapt_finmind_data margin 載入
```python
# 格式偵測:
# 1. 已對應: "margin_balance" in raw.columns → 直接使用
# 2. FinMind 原始: "MarginPurchaseTodayBalance" in raw.columns → 欄位映射
# 3. 未知: 直接使用
```

### 修復 4: compute_features 中 merge 真實資料 (最容易被遺忘)
Kaggle notebook v5.9 的 compute_features 接收了 `futures_oi_df` 和 `us_indices_df` 參數，但內部硬編碼設為 0：
```python
for f in ["TX_INST_NET_OI", "MTX_RETAIL_OI", "TX_MTX_SPREAD", ...]:
    g[f] = 0  # ← 忽略傳入的 futures_oi_df 和 us_indices_df！
```

修復後需在 compute_features 的 groupby 迴圈內插入 (注意：是在每個 stock_id 的 group 內，非迴圈外)：
```python
# 期貨 OI: pivot TX/MTX wide 再 merge (避免 2x rows)
tx_oi = foi[foi["futures_id"]=="TX"][["date","inst_net_oi","retail_net_oi"]].rename(...)
mtx_oi = foi[foi["futures_id"]=="MTX"][["date","inst_net_oi","retail_net_oi"]].rename(...)
g = g.merge(tx_oi, on="date", how="left")
g = g.merge(mtx_oi, on="date", how="left")
g["TX_INST_NET_OI"] = g["tx_inst_net_oi"].fillna(0)
g["MTX_RETAIL_OI"] = g["mtx_retail_net_oi"].fillna(0)
g["TX_MTX_SPREAD"] = g["tx_inst_net_oi"].fillna(0) - g["mtx_inst_net_oi"].fillna(0)

### 修復 5: compute_features — inst_flow 真實 merge (v6.1 新增)
取代 groupby 迴圈內的 `g["inst_flow"] = 0`：
```python
# 法人買賣超 — 從 inst_df merge 真實資料
if inst_df is not None and len(inst_df) > 0:
    _inst_merge = inst_df[inst_df["stock_id"] == stock_id][["date", "total_net"]].copy()
    if len(_inst_merge) > 0:
        _inst_merge["date"] = pd.to_datetime(_inst_merge["date"])
        _inst_merge = _inst_merge.rename(columns={"total_net": "inst_flow_raw"})
        g = g.merge(_inst_merge[["date", "inst_flow_raw"]], on="date", how="left")
        g["inst_flow"] = g["inst_flow_raw"].fillna(0)
        g.drop(columns=["inst_flow_raw"], inplace=True)
    else:
        g["inst_flow"] = 0.0
else:
    g["inst_flow"] = 0.0
```

### 修復 6: compute_features — margin_press 真實 merge (v6.1 新增)
取代 groupby 迴圈內的 `g["margin_press"] = 0`：
```python
# 融資融券壓力 — 從 margin_df merge 真實資料
if margin_df is not None and len(margin_df) > 0:
    _mg_merge = margin_df[margin_df["stock_id"] == stock_id][["date", "margin_balance", "margin_change", "short_balance"]].copy()
    if len(_mg_merge) > 0:
        _mg_merge["date"] = pd.to_datetime(_mg_merge["date"])
        # margin_press: 融資餘額變化率 (正值=散戶做多壓力)
        _mg_merge["margin_press_raw"] = _mg_merge["margin_change"].fillna(0) / (_mg_merge["margin_balance"].fillna(1) + 1e-6)
        g = g.merge(_mg_merge[["date", "margin_press_raw"]], on="date", how="left")
        g["margin_press"] = g["margin_press_raw"].fillna(0)
        g.drop(columns=["margin_press_raw"], inplace=True)
    else:
        g["margin_press"] = 0.0
else:
    g["margin_press"] = 0.0
```

### CPU Fallback: GPU 不可用時只訓練 MID_CAP_TECH regime (v6.1 新增)
Kaggle GPU quota 用完或 CPU-only 環境時，4 個 regime 同時訓練耗時過長。在 main() 中、GRPOAlphaTrainer 初始化前執行過濾：
```python
force_regime = os.environ.get("GRPO_FORCE_CPU", "0")
if force_regime == "1":
    try:
        import torch
        gpu_avail = torch.cuda.is_available()
    except ImportError:
        gpu_avail = False
    if not gpu_avail:
        tech_stocks = [sid for sid in stock_data_map 
                       if KNOWN_REGIMES.get(sid, StockRegime.MID_CAP_TECH) == StockRegime.MID_CAP_TECH]
        stock_data_map = {sid: stock_data_map[sid] for sid in tech_stocks}
```

注意：這個過濾邏輯依賴 `KNOWN_REGIMES` 和 `StockRegime` 在 `main()` 的作用域中可存取（它們在模組層級定義，所以可用）。

## 完整修復版本對照

| 版本 | 修復範圍 | 檔案 |
|------|----------|------|
| v6.0 dsfix | adapt_finmind_data 雙格式 + futures OI / US indices merge 修復 | grpo-v33-dsfix.py |
| v6.1 | v6.0 + inst_flow / margin_press 真實 merge + GPU tech-only fallback | grpo-regime-aware-factor-training-v6-1.ipynb |

# 美股: pivot wide per index 再 merge
for idx_name, feat_name in [("Nasdaq","NASDAQ_CLOSE"), ("SP500","SP500_CLOSE"), ("DowJones","DOWJONES_CLOSE")]:
    idx_data = us[us["index_name"]==idx_name][["date","close"]].rename(columns={"close": feat_name})
    g = g.merge(idx_data, on="date", how="left")
    g[feat_name] = g[feat_name].fillna(0).shift(1).fillna(0)  # 美股時差
```

## 驗證方法
```python
# 1. 確認 adapt_finmind_data 回傳 non-None
df, i, m, f, u = adapt_finmind_data(data_path)
assert f is not None, "futures_oi_df is None!"
assert len(f) > 0, "futures_oi_df empty!"
assert i is not None, "inst_df is None!"
assert m is not None, "margin_df is None!"

# 2. 確認 futures 有 TX+MTX
assert f["futures_id"].nunique() == 2

# 3. 確認 compute_features 輸出含非零期貨因子 + inst_flow + margin_press
feat = TWFeatureEngineer.compute_features(df, i, m, f, u)
for c in ["TX_INST_NET_OI", "MTX_RETAIL_OI", "TX_MTX_SPREAD",
          "INST_FLOW", "MARGIN_PRESS",
          "NASDAQ_CLOSE", "SP500_CLOSE", "DOWJONES_CLOSE"]:
    assert c in feat.columns, f"{c} missing!"
    assert (feat[c] != 0).sum() > 0, f"{c} all zeros!"
```

## 相關檔案
- 本地修復版: `/home/appuser/grpo-v33-dsfix.py`
- Kaggle notebook (v6.0 dsfix): `mhhuang14/grpo-regime-aware-factor-training-v6-0-dsfix`
- Kaggle notebook (v6.1 full): `/home/appuser/kaggle_kernel/grpo-regime-aware-factor-training-v6-1.ipynb`
- Dataset: mhhuang14/twstock-v6-0-real-data-20stocks-5y (v2)
- 測試資料: `/home/appuser/twstock_kernel_out/twstock_v6_data/`