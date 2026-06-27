# 實體檔案快速索引 (2026-06-14)

## 核心 Notebook / Kernel 原始碼

| 版本 | 檔案路徑 | 大小 | 用途 |
|------|----------|------|------|
| **v5.9** | `/home/appuser/kaggle_kernel/grpo-regime-aware-factor-training-v5-9.ipynb` | 81 KB | 基準版本，4 regime × 5 股結構 |
| **v6.1** (檔名) / **v6.2** (docstring) | `/home/appuser/twstock_kernel/grpo-regime-aware-factor-training-v6-1.ipynb` | 331 KB | "No Synthetic" 政策，auto-scan 掛載 |
| **v6.8** (Kaggle 最新) | `/home/appuser/twstock_v68_kernel/twstock-grpo-regime-aware-factor-training-v6-8.ipynb` | 70 KB | **目前最新**，完整 RegimeTrainingPlan + Advantage Fix |
| v6.1 副本 | `/home/appuser/kaggle_kernel/grpo-regime-aware-factor-training-v6-1.ipynb` | 84 KB | 同 v6.1 內容 |

## Kernel Metadata

| 檔案 | 對應 kernel | 關鍵欄位 |
|------|-------------|----------|
| `/home/appuser/twstock_kernel/kernel-metadata.json` | v6.8 | `id: mhhuang14/grpo-regime-aware-factor-training-v6-8` |
| `/home/appuser/twstock_kernel/kernel-metadata-v6.1.json` | v6.1 | `id: mhhuang14/grpo-regime-aware-factor-training-v6-1` |
| `/home/appuser/twstock_v68_kernel/kernel-metadata.json` | v6.8 | 同上 (Kaggle pull 下來的) |
| `/home/appuser/kaggle_kernel/kernel-metadata.json` | v5.9/v6.1 共用 | 需確認對應版本 |

## Data Fetch Kernel (資料取得)

| 檔案 | 版本 | 關鍵技術 |
|------|------|----------|
| `/home/appuser/twstock_kernel/twstock-v6-0-data-fetch-20-stocks-5y-v2.py` | v4.4 | **FinMind REST API** (避免 pydantic 衝突)，Kaggle 成功跑完 |

## 修復腳本 / 工具

| 檔案 | 用途 |
|------|------|
| `/home/appuser/twstock_kernel/fix_adapt_finmind.py` | 將 adapt_finmind_data 的 os.walk 改為 glob 遞迴掃描 + 診斷輸出，**未合入 notebook** |
| `/home/appuser/twstock_kernel/fix_meta_title.py` | 修改 kernel-metadata.json title |
| `/home/appuser/twstock_kernel/change_slug.py` | 修改 kernel slug |
| `/home/appuser/fix_inst_margin_loading.py` | inst/margin 載入修復 (舊版) |
| `/home/appuser/fix_compute_features_oi.py` | compute_features 期貨 OI merge 修復 |

## 資料檔案 (5 CSV) - 多份副本

| 位置 | 狀態 | 用途 |
|------|------|------|
| `/home/appuser/twstock_kernel_out/twstock_v6_data/` | **Kernel output 原始下載** | 從 v4.4 kernel 下載，最原始 |
| `/home/appuser/twstock_v6_data/` | **Dataset 推送用副本** | 已推送至 Kaggle Dataset |
| `/home/appuser/twstock_v6_data_backup/` | **備份** | 推送前備份 |

### CSV 詳細資訊

```bash
# 所有位置檔案大小一致
price_ohlcv.csv:  2,264,129 bytes (23,066 rows, 19 stocks)
inst_flow.csv:    1,777,055 bytes (25,042 rows)
margin.csv:         857,402 bytes (25,042 rows)
futures_oi.csv:     118,565 bytes (2,674 rows)
us_indices.csv:     126,121 bytes (3,765 rows)
```

## Dataset Metadata

| 檔案 | 內容 |
|------|------|
| `/home/appuser/twstock_v6_data/dataset-metadata.json` | 推送用 metadata，id 指向 `mhhuang14/twstock-v6-0-real-data-20stocks-5y` |

## 獨立 Python 模組 (可直接 import)

| 檔案 | 版本 | 說明 |
|------|------|------|
| `/home/appuser/grpo-v33-dsfix.py` | v3.3 + dsfix | 含完整 adapt_finmind_data 雙格式修復、compute_features 真實 merge |
| `/home/appuser/grpo_v33_ref.py` | v3.3 參考版 | 參考實作 |
| `/home/appuser/grpo-regime-aware-factor-training-v3-2.py` | v3.2 | 較早版本 |
| `/home/appuser/ai_dig_money_core.py` | core | P0 defects E1/E2/E3 fixed (v3.2) |

## Kaggle CLI 相關

```bash
# Kaggle CLI 路徑
/home/appuser/.local/bin/kaggle

# 常用指令
kaggle kernels pull mhhuang14/twstock-grpo-regime-aware-factor-training-v6-8 -p /home/appuser/twstock_v68_kernel --metadata
kaggle kernels output mhhuang14/twstock-v6-0-data-fetch-20-stocks-5y-v2 -p /home/appuser/twstock_kernel_out/
kaggle datasets version -p /home/appuser/twstock_v6_data -m "Update message"
kaggle datasets list -u mhhuang14 | grep twstock
```

## 關鍵 Kaggle 資源 slug

| 類型 | slug | 狀態 |
|------|------|------|
| Data Fetch Kernel | `mhhuang14/twstock-v6-0-data-fetch-20-stocks-5y-v2` | v4.4, COMPLETE |
| Training Kernel (最新) | `mhhuang14/twstock-grpo-regime-aware-factor-training-v6-8` | **v6.8, private, GPU enabled** |
| Training Kernel (舊) | `mhhuang14/grpo-regime-aware-factor-training-v5-9` | v5.9 |
| Dataset (最新) | `mhhuang14/twstock-v6-0-real-data-20stocks-5y` | **2026-06-14 更新, 1.55 MB** |
| Dataset (舊) | `mhhuang14/twstock-grpo-training-data` | 400 KB |

## 下一步動作清單

- [ ] 將 `fix_adapt_finmind.py` 的 glob 掃描邏輯合入 v6.8 notebook
- [ ] 建立 v6.9 修復 regime-aware reward + advantage normalization
- [ ] 將修復版推送至 Kaggle kernel v6.9
- [ ] 在 Kaggle 上跑 v6.9 完整訓練驗證