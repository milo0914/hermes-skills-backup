# FinMind Real Data Workflow for Kaggle GRPO Training (v5.0, 2026-06-09)

## 概要

從 FinMind + yfinance 抓取真實台股數據（3.5年），打包為 Kaggle Dataset，整合到 GRPO 訓練 kernel 替換合成數據。

## 數據源可用性（從 HF Space 測試）

| API | 來源 | 可用 | 備註 |
|-----|------|------|------|
| FinMind StockPrice | `https://api.finmindtrade.com/v4/data` | ✅ | 台股日K OHLCV |
| FinMind InstInvestors | 同上，dataset=taiwan_stock_institutional_investors | ✅ | 三大法人買賷超 |
| FinMind Margin | 同上，dataset=taiwan_stock_margin | ✅ | 融資融券餘額 |
| FinMind Futures | 同上，dataset=taiwan_futures_daily | ✅ | 期貨日K+open_interest |
| FinMind Futures Inst | 同上，dataset=taiwan_futures_institutional_investors | ✅ | 期貨法人OI（**機構名稱是中文**） |
| yfinance 台股 | `2330.TW` 等 | ✅ | 備用 OHLCV |
| yfinance 美股 | `^IXIC`, `^GSPC`, `^DJI` | ✅ | 需個別下載+延遲（限流） |
| TWSE T86 | 證交所官網 | ❌ | HF Space IP 限制 (451/TLS) |
| TAIFEX Open Data | 期交所官網 | ❌ | 404 已廢 |

## fetch_real_data.py 關鍵邏輯

### 1. FinMind API 呼叫模式

```python
import requests
import time

FINMIND_URL = "https://api.finmindtrade.com/v4/data"

def fetch_finmind(dataset, stock_id=None, date_start="2022-01-01", date_end="2025-06-30"):
    params = {"dataset": dataset, "date_start": date_start, "date_end": date_end}
    if stock_id:
        params["stock_id"] = stock_id
    resp = requests.get(FINMIND_URL, params=params, timeout=30)
    data = resp.json().get("data", [])
    return pd.DataFrame(data)
```

### 2. 期貨法人 OI — 中文機構名稱

**最關鍵的陷阱**：`institutional_investors` 欄位是中文（`外資`、`投信`、`自營商`），不是英文。

```python
# ❌ 錯誤 — 找不到任何行，inst_net_oi 全 NaN
df[df["institutional_investors"] == "Foreign Investor"]

# ✅ 正確
df_foreign = df[df["institutional_investors"] == "外資"]
df_domestic = df[df["institutional_investors"].isin(["投信", "自營商"])]

# 計算法人淨 OI（建議自行計算，不依賴 net_open_interest 欄位）
inst_net_oi = (df_foreign["long_open_interest"].sum()
             - df_foreign["short_open_interest"].sum())
```

### 3. 期貨 OI 格式（FinMind 只提供 TX，MTX 嵌入其中）

FinMind 的 `taiwan_futures_daily` 只回傳 TX 商品，不會有獨立的 MTX 行。
散戶 OI = 總 open_interest - 三大法人(long_oi + short_oi)。
MTX 近似：用 60/40 比例拆分法人/散戶（暫時方案，需後續替換為 TAIFEX API 或 Shioaji）。

### 4. yfinance 美股指數 — 限流處理

```python
import yfinance as yf
import time

indices = {"^IXIC": "NASDAQ", "^GSPC": "SP500", "^DJI": "DOWJONES"}
for ticker, name in indices.items():
    for attempt in range(3):
        try:
            df = yf.download(ticker, period="3y", progress=False)
            break
        except Exception:
            time.sleep(5 * (attempt + 1))
```

**注意**：yfinance 回傳美東日期，台股為台北日期。美股收盤影響隔日台股。compute_features 中用 `shift(1)` 處理。假日不對齊時 ffill。

### 5. yfinance MultiIndex 欄位處理

yfinance 下載多標的時回傳 MultiIndex columns：
```python
# 解決方案 1：個別下載（推薦，避免 MultiIndex）
df = yf.download("2330.TW", period="3y")

# 解決方案 2：處理 MultiIndex
df.columns = df.columns.get_level_values(1)  # 取第二層欄位名
```

## adapt_finmind_data() — 數據適配層

在 Kaggle notebook 內將 FinMind CSV 適配為訓練腳本期望的格式：

```python
def adapt_finmind_data(data_dir="/kaggle/input/twstock-grpo-training-data"):
    # inst_data: pivot 個股×日期的法人買超
    inst_df = pd.read_csv(f"{data_dir}/inst_data.csv")
    inst_pivot = inst_df.pivot_table(
        index="date", columns="stock_id",
        values=["foreign_net", "trust_net", "dealer_net", "total_net"]
    )

    # margin_data: 欄位映射
    margin_df = pd.read_csv(f"{data_dir}/margin_data.csv")
    margin_df = margin_df.rename(columns={
        "MarginPurchaseTodayBalance": "margin_balance",
        "ShortSaleTodayBalance": "short_balance"
    })

    # futures_oi: TX 商品含嵌入 mtx_oi / tx_mtx_spread
    futures_oi_df = pd.read_csv(f"{data_dir}/futures_oi.csv")

    # us_indices: 寬表 → 長表（如有需要）
    us_indices_df = pd.read_csv(f"{data_dir}/us_indices.csv")

    return inst_pivot, margin_df, futures_oi_df, us_indices_df
```

## Kaggle Dataset 上傳流程

```bash
# 1. 準備數據目錄
mkdir -p /tmp/real-data-v2
cd /tmp/real-data-v2

# 2. 執行 fetch_real_data.py
python3 fetch_real_data.py --output /tmp/real-data-v2

# 3. 建立 dataset-metadata.json
cat > dataset-metadata.json << 'EOF'
{
  "title": "TWStock GRPO Training Data",
  "id": "mhhuang14/twstock-grpo-training-data",
  "licenses": [{"name": "CC0-1.0"}]
}
EOF

# 4. 首次上傳
KAGGLE_API_TOKEN="***" kaggle datasets create -p /tmp/real-data-v2

# 5. 更新版本（後續修改數據時）
KAGGLE_API_TOKEN="***" kaggle datasets version -p /tmp/real-data-v2 -m "v2: FinMind real data 3.5 years"
```

## kernel-metadata.json Dataset 綁定

**關鍵**：`dataset_sources` 必須正確引用 dataset slug，否則 kernel 無法掛載數據。

```json
{
  "id": "mhhuang14/grpo-regime-aware-factor-training",
  "title": "GRPO Regime-Aware Factor Training v5",
  "code_file": "grpo_regime_training.ipynb",
  "language": "python",
  "kernel_type": "notebook",
  "is_private": "true",
  "enable_gpu": "true",
  "enable_internet": "true",
  "dataset_sources": ["mhhuang14/twstock-grpo-training-data"],
  "machine_shape": "NvidiaTeslaT4"
}
```

數據掛載路徑：`/kaggle/input/twstock-grpo-training-data/`

## 驗證清單

1. 數據涵蓋期間 >= 3 年 ✅（2022-01-03 ~ 2025-06-30 = 3.5年）
2. 零空值（fillna + ffill 處理後）
3. 日期對齊（台股/法人/融資/期貨/美股）
4. 期貨法人 OI 中文映射正確（非英文）
5. 22 因子全部可計算（非 0 值比例 > 50%）

## 已知限制

1. **期貨法人/散戶 OI 拆分**：FinMind 只提供總 OI + 法人 OI，散戶 = 總 - 法人。MTX 無獨立數據，用 60/40 近似。真實拆分需 TAIFEX API（IP 限制）或 Shioaji。
2. **美股時差**：yfinance 回傳美東日期，與台股台北日期差 12-13 小時。已用 shift(1) 處理。
3. **FinMind API 速率限制**：連續請求可能 429，內建 3s 間隔 + 3 次重試。
4. **Kaggle dataset 掛載失敗**：v5 首次執行顯示「無 Kaggle Dataset，使用合成數據」，可能需在 Kaggle UI 手動重新綁定 dataset 到 kernel。

## 訓練結果（v4.1 合成數據，不具參考價值）

| Regime | train_IC | val_IC | gap | top_feature |
|--------|----------|--------|-----|-------------|
| 1301 (traditional) | 0.1975 | 0.3731 | -0.1756 | LIQ_SCORE |
| 2330 (large_cap) | 0.1391 | 0.2533 | -0.1142 | LIQ_SCORE |
| 2454 (mid_cap_tech) | 0.1041 | -0.2679 | 0.3720 | ATR |
| 2882 (financial) | 0.2199 | 0.0000 | 0.2199 | CLOSE_POS |

合成數據僅 7/19 維特徵有值，導致 overfit=True + valid=100%。待真實數據 v5 訓練驗證。
