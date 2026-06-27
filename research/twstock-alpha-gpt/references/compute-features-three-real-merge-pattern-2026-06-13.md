# compute_features Three Real-Data Merge Pattern (2026-06-13)

## 問題
`adapt_finmind_data` 正確載入了 futures_oi_df / us_indices_df / inst_df / margin_df，但 `compute_features` 內部**硬編碼設為 0**，完全忽略傳入的真實資料：

```python
# v5.9 錯誤寫法
for f in ["TX_INST_NET_OI", "MTX_RETAIL_OI", "TX_MTX_SPREAD",
          "NASDAQ_CLOSE", "SP500_CLOSE", "DOWJONES_CLOSE",
          "INST_FLOW", "MARGIN_PRESS"]:
    g[f] = 0  # ← 忽略傳入的 futures_oi_df, us_indices_df, inst_df, margin_df！
```

導致 GRPO 訓練只能用 OHLCV 衍生因子，期貨/法人/融資/美股因子全為 0。

## 修復原則：在 groupby 迴圈內逐股 merge 真實資料

**關鍵**：merge 必須在 `for stock_id, group in df.groupby("stock_id"):` 迴圈內，不能在迴圈外統一 merge — 因每檔股票的 date 列不同，外層 merge 會錯位或產生笛卡兒積。

---

## 1. 期貨 OI Merge (Futures Pivot Wide)

```python
# 期貨 OI: pivot TX/MTX wide 再 merge (避免每檔股票 rows 翻倍 2x)
if futures_oi_df is not None and len(futures_oi_df) > 0:
    foi = futures_oi_df.copy()
    foi["date"] = pd.to_datetime(foi["date"])
    
    # TX
    tx_oi = foi[foi["futures_id"] == "TX"][["date", "inst_net_oi", "retail_net_oi"]].copy()
    tx_oi = tx_oi.rename(columns={"inst_net_oi": "tx_inst_net_oi", "retail_net_oi": "tx_retail_net_oi"})
    
    # MTX
    mtx_oi = foi[foi["futures_id"] == "MTX"][["date", "inst_net_oi", "retail_net_oi"]].copy()
    mtx_oi = mtx_oi.rename(columns={"inst_net_oi": "mtx_inst_net_oi", "retail_net_oi": "mtx_retail_net_oi"})
    
    g = g.merge(tx_oi, on="date", how="left")
    g = g.merge(mtx_oi, on="date", how="left")
    
    g["TX_INST_NET_OI"] = g["tx_inst_net_oi"].fillna(0)
    g["MTX_RETAIL_OI"] = g["mtx_retail_net_oi"].fillna(0)
    g["TX_MTX_SPREAD"] = (g["tx_inst_net_oi"].fillna(0) - g["mtx_inst_net_oi"].fillna(0))
    
    # 清理暫存欄位
    for c in ["tx_inst_net_oi", "tx_retail_net_oi", "mtx_inst_net_oi", "mtx_retail_net_oi"]:
        if c in g.columns: g.drop(columns=[c], inplace=True)
else:
    for f in ["TX_INST_NET_OI", "MTX_RETAIL_OI", "TX_MTX_SPREAD"]:
        g[f] = 0.0
```

---

## 2. 法人買賣超 Merge (Inst Flow)

```python
# 法人買賣超 — 從 inst_df merge 真實資料 (total_net)
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

---

## 3. 融資融券壓力 Merge (Margin Press)

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

---

## 4. 美股指數 Merge (US Indices Pivot Wide + Shift 1)

```python
# 美股指數: pivot wide per index 再 merge
if us_indices_df is not None and len(us_indices_df) > 0:
    us = us_indices_df.copy()
    us["date"] = pd.to_datetime(us["date"])
    
    for idx_name, feat_name in [("Nasdaq", "NASDAQ_CLOSE"),
                                 ("SP500", "SP500_CLOSE"),
                                 ("DowJones", "DOWJONES_CLOSE")]:
        idx_data = us[us["index_name"] == idx_name][["date", "close"]].copy()
        idx_data = idx_data.rename(columns={"close": feat_name})
        g = g.merge(idx_data, on="date", how="left")
        g[feat_name] = g[feat_name].fillna(0).shift(1).fillna(0)  # 美股時差：T 日用 T-1 收盤
else:
    for f in ["NASDAQ_CLOSE", "SP500_CLOSE", "DOWJONES_CLOSE"]:
        g[f] = 0.0
```

---

## 常見錯誤 (Pitfalls)

| 錯誤 | 後果 | 修正 |
|------|------|------|
| 在迴圈外 merge futures_oi_df | 每檔股票 rows × 2 (TX+MTX)，date 對不齊 | 在迴圈內 pivot wide 後 merge |
| 忘記 `shift(1)` 處理美股時差 | Look-ahead bias，用 T 日美股預測 T 日台股 | 必須 `.shift(1).fillna(0)` |
| merge 後忘記 drop 暫存欄位 | `robust_normalize` 處理到中間欄位 | 用 `inplace=True` 清理 |
| inst_df 欄位名不匹配 (Foreign_Investor vs foreign_net) | merge 失敗，inst_flow 全 0 | 先檢查實際欄位名，正確 rename |

---

## 驗證腳本

```python
# 驗證 22 個因子皆有非零值
feat = TWFeatureEngineer.compute_features(df, i_df, m_df, f_df, u_df)
for c in ["TX_INST_NET_OI", "MTX_RETAIL_OI", "TX_MTX_SPREAD",
          "INST_FLOW", "MARGIN_PRESS",
          "NASDAQ_CLOSE", "SP500_CLOSE", "DOWJONES_CLOSE"]:
    non_zero = (feat[c] != 0).sum()
    print(f"{c:20s}: non-zero={non_zero:>6}, mean={feat[c].mean():+.4f}, std={feat[c].std():.4f}")
    assert non_zero > 0, f"{c} all zeros!"
```

---

## 相關檔案
- 本地完整修復: `/home/appuser/grpo-v33-dsfix.py` (v6.0 dsfix)
- Kaggle notebook v6.1: `grpo-regime-aware-factor-training-v6-1.ipynb` (含此修復)
- Kernel v6.4: 已驗證 compute_features 含完整三大 merge