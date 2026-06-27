# End-to-End Data Pipeline: Kernel Fetch → Dataset Push → Training

**Session**: 2026-06-14  
**Goal**: Push 5 real data CSVs to Kaggle Dataset for GRPO v6.8 training  
**Outcome**: Dataset `mhhuang14/twstock-v6-0-real-data-20stocks-5y` updated (1.55 MB, 5 files)

---

## Complete Flow

### 1. Data Fetch Kernel (v4.4 - FinMind REST API)
- **Kernel**: `mhhuang14/twstock-v6-0-data-fetch-20-stocks-5y-v2` (v4.4)
- **Key fix**: Replaced `pip install FinMind` with direct REST API (`requests` to `https://api.finmindtrade.com/api/v4/data`)
- **Datasets called**:
  - `TaiwanStockInstitutionalInvestorsBuySell` → inst_flow.csv
  - `TaiwanStockMarginPurchaseShortSale` → margin.csv
  - `TaiwanFuturesInstitutionalInvestors` → futures_oi.csv
- **Output**: 5 CSVs downloaded to `/home/appuser/twstock_kernel_out/twstock_v6_data/`
- **Verification**: All 5 files confirmed (price_ohlcv: 23,066 rows, inst_flow: 25,042, margin: 25,042, futures_oi: 2,674, us_indices: 3,765)

### 2. Dataset Push
```bash
# Create dataset-metadata.json in data folder
cat > /home/appuser/twstock_v6_data/dataset-metadata.json << 'EOF'
{
  "id": "mhhuang14/twstock-v6-0-real-data-20stocks-5y",
  "title": "TWStock v6.0 Real Data - 20 Stocks 5 Years",
  "subtitle": "OHLCV, Institutional Flow, Margin, Futures OI, US Indices (2021-2026)",
  "description": "Real Taiwan stock data for GRPO regime-aware factor training...",
  "licenses": [{"name": "CC0-1.0"}],
  "files": [
    {"name": "price_ohlcv.csv", "description": "OHLCV daily data for 19 stocks (2311 delisted)"},
    {"name": "inst_flow.csv", "description": "Institutional investors buy/sell net flow"},
    {"name": "margin.csv", "description": "Margin purchase and short sale balances"},
    {"name": "futures_oi.csv", "description": "TX/MTX futures institutional open interest"},
    {"name": "us_indices.csv", "description": "Nasdaq, S&P500, Dow Jones daily closes"}
  ]
}
EOF

# Update existing dataset (not create - already exists)
/home/appuser/.local/bin/kaggle datasets version \
  -p /home/appuser/twstock_v6_data \
  -m "v1.0.0: Initial release with 5 CSV files (OHLCV, inst_flow, margin, futures_oi, us_indices) from 20 stocks × 5 years"
```

**Result**: Dataset updated at `mhhuang14/twstock-v6-0-real-data-20stocks-5y` (1.55 MB)

### 3. Training Kernel (v6.8) - Key Improvements Over v6.1
| Feature | v6.1 (local) | v6.8 (Kaggle) |
|---------|--------------|---------------|
| KNOWN_REGIMES | 15 stocks, 3 regimes | **20 stocks, 4 regimes × 5 stocks** |
| RegimeTrainingPlan | None | **feature_weights, operator_mask, training_params per regime** |
| Advantage collapse fix | None | **noise injection + group_size=64** |
| data_path | hardcoded | **auto-scan `/kaggle/input/`** |

**v6.8 slug**: `mhhuang14/twstock-grpo-regime-aware-factor-training-v6-8`

### 4. Version Management Lesson
- **Always check Kaggle directly** before assuming local version is latest
- `kaggle kernels list --user MHHUANG14` revealed v6.8 existed while local only had v6.1
- Three-layer versioning must sync: filename / internal title / metadata.id

---

## Commands Reference

```bash
# Pull latest kernel from Kaggle
/home/appuser/.local/bin/kaggle kernels pull mhhuang14/twstock-grpo-regime-aware-factor-training-v6-8 -p /tmp/v68 --metadata

# List all kernels for a user
/home/appuser/.local/bin/kaggle kernels list --user MHHUANG14

# Verify dataset
/home/appuser/.local/bin/kaggle datasets list --user mhhuang14 | grep twstock-v6

# Download dataset for local testing
/home/appuser/.local/bin/kaggle datasets download mhhuang14/twstock-v6-0-real-data-20stocks-5y --unzip -p /tmp/test_data/
```

---

## Next Steps (after user verification)
1. Push v6.8 kernel with dataset_sources pointing to this dataset
2. Monitor training on Kaggle T4 GPU
3. Verify regime distribution, advantage stats, IC metrics