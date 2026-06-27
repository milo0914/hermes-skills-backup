# Kaggle Dataset v2 推送記錄 (2026-06-14)

## 背景
TWStock GRPO v6.8 kernel 依賴 `mhhuang14/twstock-v6-0-real-data-20stocks-5y` dataset 作為真實數據來源。本次將最新從 kernel 產出的 5 個 CSV 推送更新 dataset。

## 來源數據
從 Kaggle kernel `mhhuang14/twstock-v6-0-data-fetch-20-stocks-5y-v2` (v4.4) 產出並下載：

| 檔案 | 位置 | 大小 | 筆數 | 說明 |
|------|------|------|------|------|
| price_ohlcv.csv | `/home/appuser/twstock_kernel_out/twstock_v6_data/` | 2.16 MB | 23,066 | 19 檔股票 OHLCV (2311 日月光已除牌無資料) |
| inst_flow.csv | 同上 | 1.69 MB | 25,042 | 法人買賣超 (Foreign_Investor, Dealer_self, Investment_Trust, Dealer_Hedging, Foreign_Dealer_Self, total_net) |
| margin.csv | 同上 | 837 KB | 25,042 | 融資融券 (margin_balance, margin_buy, margin_sell, margin_change, short_balance, short_buy, short_sell, short_change) |
| futures_oi.csv | 同上 | 116 KB | 2,674 | 期貨法人未平倉 (futures_id: TX/MTX, inst_net_oi, retail_net_oi, dealer_self_net_oi, dealer_hedging_net_oi) |
| us_indices.csv | 同上 | 123 KB | 3,765 | 美股指數 (index_name: Nasdaq/SP500/DowJones, close, mom5) |

## 推送流程

```bash
# 1. 建立 dataset 目錄並複製檔案
mkdir -p /home/appuser/twstock_v6_data
cp /home/appuser/twstock_kernel_out/twstock_v6_data/*.csv /home/appuser/twstock_v6_data/

# 2. 建立 dataset-metadata.json
cat > /home/appuser/twstock_v6_data/dataset-metadata.json << 'EOF'
{
  "id": "mhhuang14/twstock-v6-0-real-data-20stocks-5y",
  "title": "twstock-v6-0-real-data-20stocks-5y",
  "subtitle": "TWStock v6.0 Real Data - 20 Stocks 5 Years",
  "description": "5 CSV files: price_ohlcv (OHLCV), inst_flow (institutional), margin (margin trading), futures_oi (futures OI), us_indices (US indices). 20 stocks x 5 years (2021-01-04 to 2026-06-11). Stock 2311 delisted. Updated 2026-06-14.",
  "licenses": [{"name": "CC0-1.0"}],
  "keywords": ["taiwan", "stock", "financial-data", "grpo", "factor-training", "ohlcv", "institutional-investors", "margin-trading", "futures-oi"]
}
EOF

# 3. 推送 (新建失敗因標題重複，改用 version 擴充)
kaggle datasets version -p /home/appuser/twstock_v6_data -m "Update 2026-06-14: complete 5 CSV from v4.4 kernel output, 20 stocks 5 years real data"
```

## 結果
- **Dataset URL**: `mhhuang14/twstock-v6-0-real-data-20stocks-5y`
- **大小**: 1.55 MB (壓縮後)
- **更新時間**: 2026-06-14 10:00:07
- **下載數**: 7
- **狀態**: 公開可用，v6.8 kernel 可直接掛載

## 注意事項
1. **標題衝突**: `kaggle datasets create` 失敗 (標題已存在)，改用 `kaggle datasets version` 更新既有 dataset
2. **Tag 驗證**: 部分自定義 tag 被拒絕 (non-standard tags)，不影響功能
3. **Kernel 相依**: v6.8 kernel metadata 中已宣告 `dataset_sources: ["mhhuang14/twstock-v6-0-real-data-20stocks-5y"]`，掛載後 `adapt_finmind_data()` 會自動掃描載入
4. **備份**: 原資料已備份至 `/home/appuser/twstock_v6_data_backup/`

## 驗證命令
```bash
# 本地驗證 CSV 完整性
python3 -c "
import pandas as pd
files = ['price_ohlcv.csv','inst_flow.csv','margin.csv','futures_oi.csv','us_indices.csv']
for f in files:
    df = pd.read_csv(f'/home/appuser/twstock_v6_data/{f}')
    print(f'{f}: {len(df)} rows, {df.shape[1]} cols, stocks={df[\"stock_id\"].nunique() if \"stock_id\" in df.columns else \"N/A\"}')"

# Kaggle 驗證 dataset 存在
kaggle datasets list -u mhhuang14 | grep twstock-v6-0-real-data
```

## 相關檔案
- Dataset metadata: `/home/appuser/twstock_v6_data/dataset-metadata.json`
- Kernel data fetch: `/home/appuser/twstock_kernel/twstock-v6-0-data-fetch-20-stocks-5y-v2.py` (v4.4, FinMind REST API)
- Kernel training v6.8: `/home/appuser/twstock_v68_kernel/twstock-grpo-regime-aware-factor-training-v6-8.ipynb`