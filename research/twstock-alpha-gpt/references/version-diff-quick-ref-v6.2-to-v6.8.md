# v6.2~v6.8 版本差異 Quick Reference

## Hyperparameter 演進

| 參數 | v5.9 | v6.1/v6.2 | v6.5 | v6.7/v6.8 |
|------|------|-----------|------|-----------|
| group_size | 16 (CPU/GPU) | 16 | 64 | 64 (CPU max(,64)) |
| batch_size | 128 | 128 | 256 | 256 |
| train_steps | 8000 | 8000 | 15000 | 15000 |
| entropy_coef | 0.08 | 0.08 | 0.15 | 0.15 |
| gumbel_noise_scale | 1.0 | 1.0 | 1.5 | 1.5 |
| diversity_penalty | 2.0 | 2.0 | 3.0 | 3.0 |
| advantage_clip | - | - | 3.0 | 3.0 |

## 資料載入演進

| 版本 | adapt_finmind_data | 找不到資料時 | 掃描方式 |
|------|-------------------|-------------|----------|
| v5.9 | 雙格式支援 | fallback 合成噪聲 | os.walk |
| v6.1 | 雙格式 + 5表 merge | RuntimeError | os.walk |
| v6.2 | 雙格式 + 5表 merge | RuntimeError | glob recursive + 多路徑 + 診斷 |
| v6.8 | 同 v6.2 (但未合入 fix) | RuntimeError | os.walk (未合入 glob fix!) |

## KNOWN_REGIMES 變化

| 版本 | LARGE_CAP (5) | MID_CAP_TECH (5) | TRADITIONAL (5) | FINANCIAL (5) |
|------|--------------|-------------------|-----------------|---------------|
| v5.9 | 2330,2308,2412,1303,1326 | 2454,2382,2317,3034,3711 | 1301,1101,2002,2105,2207 | 2882,2886,2891,2881,2884 |
| v6.8 | 同上 | 同上 | 同上 | 同上 |

注意: 2311(日月光)在原始 tickers 清單中，但已除牌無數據。v5.9 曾把 3711 歸在 LARGE_CAP 後移至 MID_CAP_TECH。

## Advantage Collapse 處理演進

| 版本 | 做法 |
|------|------|
| v5.8 | 全隨機替換 advantages (太暴力) |
| v6.5/v6.7 | adv_std < 1e-4 時加 noise(randn*0.1) (溫和) |
| v6.8 | 同 v6.7 (根本原因未解) |

## Dataset 演進

| 版本 | Slug | 大小 | 內容 |
|------|------|------|------|
| v1 | twstock-grpo-training-data | 400KB | 舊格式, 欄位不一致 |
| v2 | twstock-v6-0-real-data-20stocks-5y | 1.55MB | 5 CSV, 19 stocks (2311 除牌), 2021-2026 |

## FinMind API 映射 (Data Fetch Kernel v4.4)

| FinMind Dataset | 輸出 CSV | API dataset 參數值 |
|-----------------|----------|-------------------|
| TaiwanStockInstitutionalInvestorsBuySell | inst_flow.csv | TaiwanStockInstitutionalInvestorsBuySell |
| TaiwanStockMarginPurchaseShortSale | margin.csv | TaiwanStockMarginPurchaseShortSale |
| TaiwanFuturesInstitutionalInvestors | futures_oi.csv | TaiwanFuturesInstitutionalInvestors |

API endpoint: `https://api.finmindtrade.com/api/v4/data`
Params: `dataset`, `data_id`, `start_date`

## 关键文件路径

- Notebook v6.8: `references/grpo-regime-aware-factor-training-v6-8.ipynb` (in skill directory)
- Data fetch v4.4: `references/twstock-v6-0-data-fetch-v4.4.py` (in skill directory)
- Fix adapt v6.2: `references/fix-adapt-finmind-v6.2.py` (in skill directory)
- Kernel metadata v6.8: `references/kernel-metadata-v6.8.json` (in skill directory)
