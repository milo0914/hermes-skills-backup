# V7 vs Bot FinMind 欄位比對 (2026-06-26)

## 結論摘要

三個層面的比對結果：

| 比對項目 | V7 ipynb (訓練) | Bot 腳本 (推論) | 一致? |
|----------|-----------------|-----------------|-------|
| 數據來源 | Kaggle CSV (預處理) | FinMind REST API (即時) | 不同但預期 |
| 投資者名稱欄 | N/A (CSV 已篩好) | `institutional_investors` | — |
| 投資者篩選值 | N/A | `"外資"` (非 `"外資及陸資"`) | — |
| OI 計算欄位 | N/A (CSV 直接有 `inst_net_oi`) | `long_open_interest_balance_volume` - `short_open_interest_balance_volume` | — |
| robust_normalize | window=60, clip=5.0, 1.4826 | window=60, clip=5.0, 1.4826 | ✅ 完全一致 |
| EMA 算子 | 0.8\*a + 0.6\*roll(a,1) | 0.8\*a + 0.6\*roll(a,1) | ✅ 完全一致 |
| compute_features | 22 因子定義 | 22 因子定義 | ✅ 完全一致 |
| **retail_net_oi** | **total_oi - inst_net_oi** | **-inst_net_oi** | ❌ **不一致** |
| **inst_net_oi 來源** | **直接讀 CSV 或 60% fallback 估算** | **精確 API long-short 差值** | ⚠️ 潛在差異 |

## 詳細比對

### 1. FinMind API 實際回傳欄位

`TaiwanFuturesInstitutionalInvestors` dataset:
- `institutional_investors` (而非 `name`): 值為 "外資"、"投信"、"自營商"
- `long_open_interest_balance_volume` (而非 `long_oi`)
- `short_open_interest_balance_volume` (而非 `short_oi`)
- 無 `inst_net_oi`/`retail_net_oi` 欄位 (需自行計算)

### 2. V7 ipynb (訓練端)

數據來源: Kaggle CSV (`/kaggle/input/` → `mhhuang14/twstock-v6-0-real-data-20stocks-5y`)

adapt_finmind_data (L432-446) 有兩條路徑:
- **主路徑** (CSV 有 `inst_net_oi`): 直接使用
- **Fallback** (CSV 只有 `oi`): `inst_net_oi = total_oi * 0.6` (60% 估算)
- `retail_net_oi = total_oi - inst_net_oi` (L439)

### 3. Bot 腳本 v1.1 (推論端)

數據來源: FinMind REST API 即時抓取

L388-406 已做雙重適配:
- 優先查 `institutional_investors` + `"外資"` + `long_open_interest_balance_volume`
- 回退查 `name` + `"外資及陸資"` + `long_oi`
- `inst_net_oi = long - short`
- `retail_net_oi = -inst_net_oi`

### 4. retail_net_oi 定義差異的影響

| | V7 定義 | Bot 定義 |
|---|---------|----------|
| Formula | total_oi - inst_net_oi | -inst_net_oi |
| 含義 | 散戶+投信+自營商 | 外資部位的鏡像 |
| 正負號 | 可能正也可能負 | 與外資部位相反 |
| 量級 | 較大 (含多種投資者) | 較小 (只有外資) |

影響範圍:
- `MTX_RETAIL_OI` 特徵值 → Z-score 分布
- traditional 公式: `GATE(MAX3(MTX_RETAIL_OI)>0 ? TX_INST_NET_OI : ...)`
- 若 GATE 條件因定義不同而選了不同分支，訊號方向可能反轉

### 5. V7 60% Fallback 影響

如果 Kaggle CSV 中的 futures_oi.csv 沒有 `inst_net_oi` 欄:
- 訓練時 inst_net_oi = total_oi * 0.6 (估算值)
- 推論時 inst_net_oi = API 精確值 (long - short)
- 估算值 vs 精確值的數值分布不同
- Z-score 的 median/MAD 基準不同
- → train-inference skew

**檢查方法**: 查看 Kaggle Dataset `futures_oi.csv` 是否含 `inst_net_oi` 欄

## 建議

1. 統一 `retail_net_oi` 定義為 `-inst_net_oi` (散戶≈外資零和)
2. 確認 Kaggle Dataset 版本的 futures_oi.csv 是否走 fallback 路徑
3. 若有 train-inference skew，考慮重新訓練 traditional 公式
