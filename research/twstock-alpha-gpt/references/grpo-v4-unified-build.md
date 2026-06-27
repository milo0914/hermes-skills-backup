# GRPO v4 Unified Build Session (2026-06-09)

## 摘要
將三版（用戶版 883行 / Kaggle v3.5 2207行 / 本地版 1913行）統合為單一 `grpo_v4_unified.py`，推送至 Kaggle 訓練。

## 三版統合策略
- **基底**：用戶版（精簡架構 + Data Leakage 修復 + MTPHead 啟用 + Entropy 梯度連接）
- **修入 v3.5**：REINFORCE policy gradient + NaN Guard（step-level skip + param-level reinit）
- **補全**：TWFeatureEngineer 4 因子（TX_MTX_SPREAD + 美股 3 因子）
- **整合**：`fetch_real_data.py` v4.2 真實數據拉取模組

## 關鍵檔案
| 檔案 | 版本 | 說明 |
|------|------|------|
| `scripts/grpo_v4_unified.py` | v4.1+ | 三合一統合版，63,664 bytes，22 因子，REINFORCE + NaN Guard |
| `scripts/fetch_real_data.py` | v4.2 | 真實數據拉取模組，359 行，期貨 OI 中文映射修復 |
| `/tmp/twstock_real_data/` | — | 本地真實數據快取（4 檔 × 250 天 × 5 表） |

## Kaggle Kernel 執行歷史

### Kernel v1 (grpo-regime-aware-factor-training-v4)
- **失敗原因**：ipynb cell 切割在 L100 處切斷 `StackVMState.execute()` 方法定義
- **錯誤**：`KeyError: 'inst_flow'`（Cell 1 syntax error 導致後續定義缺失）

### Kernel v2 (grpo-regime-aware-factor-training-v4)
- **失敗原因**：兩個 root cause
  1. **GPU sm_60 不相容**：`AcceleratorError: CUDA error: no kernel image is available for execution on the device`。PyTorch 2.10+ 只支援 sm_70+，Kaggle 分配 P100 (sm_60)
  2. **真實數據未附 dataset**：fallback 合成數據 → 14/22 因子恆為 0

### Kernel 修復方向（待執行）
1. `check_environment()` 中 `cc[0] >= 5` 改為 `cc[0] >= 7`，或用 `try/except torch.zeros(1, device="cuda")` 實際測試
2. 上傳真實數據至 Kaggle Dataset，kernel-metadata.json 引用該 dataset
3. 重新 push kernel v3

## FinMind 期貨 OI 中文映射修復

### 問題
`fetch_real_data.py` v4.1 使用英文機構名稱比對：
```python
df[df["institutional_investors"] == "Foreign Investor"]  # ❌ 找不到
```

### 修復 (v4.2)
改為中文比對：
```python
df_foreign = df[df["institutional_investors"] == "外資"]
df_domestic = df[df["institutional_investors"].isin(["投信", "自營商"])]
inst_net_oi = df_foreign["long_open_interest"].sum() - df_foreign["short_open_interest"].sum()
```

### 驗證
修復後 `futures_oi.csv` 606/606 筆 non-zero，E5 三因子全部非零。

## pandas 2.x 兼容性
- `fillna(method="bfill")` → `.bfill()`
- `fillna(method="ffill")` → `.ffill()`

## yfinance MultiIndex Column 問題
yfinance 下載台股/美股數據時，CSV 欄位為 MultiIndex (Price, Close/High/Low/Open/Volume)。
需 `columns.get_level_values(1)` 處理，或 `header=[0,1]` 讀取後再 flatten。

## 待修復項目
1. GPU sm_60 fallback（check_environment 門檻從 sm_50 改為 sm_70）
2. 真實數據上傳至 Kaggle Dataset
3. Kernel v3 push + 監控
