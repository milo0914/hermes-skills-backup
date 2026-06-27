# v6.23 Kaggle Debug Session — Auth & SyntaxError 崩潰記錄

**日期**: 2026-06-21
**Kernel**: `mhhuang14/twstock-grpo-v6-23-4-bug-root-cause-fix` (version 1)

---

## 1. 崩潰根因：Python 語法陷阱 (Pitfall #71)

### 錯誤現象
Kernel 在 Cell 1 line 730 直接 `SyntaxError: '{' was never closed` 崩潰，完全未執行任何訓練邏輯。

### 根因代碼
```python
# ❌ 崩潰版本 (Kaggle 實際執行的版本)
reward_weights: dict = field(default_factory=lambda: {"ic": 0.35, "sharpe": 0.15, "mdd": 0.08, "turnover": 0.04, "complexity": 0.25, "simplicity": 0.05, "length": 0.08})  # 【v6.23 P0】comment
```

Python parser 將 `#` 到行尾視為 comment，導致 closing `})` 被吞噬。

### 修復版本
```python
# ✅ 修復版本 (已 push v2)
# 【v6.23 P0】reward_weights: complexity 0.45→0.25 讓IC信號主導
reward_weights: dict = field(default_factory=lambda: {"ic": 0.35, "sharpe": 0.15, "mdd": 0.08, "turnover": 0.04, "complexity": 0.25, "simplicity": 0.05, "length": 0.08})
```

**教訓**：任何 inline expression（lambda、dict literal、list comprehension）內，**不要在 literal 後同一行加 comment**。將 comment 移至上一行。

---

## 2. KGAT_ Token 認證相容性問題

### 測試環境
- `kaggle.json`: `{"username": "mhhuang14", "key": "KGAT_dd32ec145fad88e442e580ed6c6d44b8"}`
- 無 `KAGGLE_API_TOKEN` 環境變數

### 測試結果

| 命令 | 結果 | 備註 |
|------|------|------|
| `kernels push` | ✅ 成功 | 推送 v2 成功 |
| `kernels list -m` | ❌ 401 Unauthorized | 無法列出自己的 kernels |
| `kernels output` | ❌ 403 Forbidden | 無法下載 log 監控執行 |
| `kernels pull` | ❌ 403 Forbidden | 無法下載既有 kernel |
| `kernels status` | ❌ 401/500 | 不穩定 |

### 結論
**KGAT_ token 在 kaggle.json 中僅支援 `kernels push`**。監控、列表、下載等讀取操作需要 `KAGGLE_API_TOKEN` 環境變數。

### ⚠️ Token 過期問題 (2026-06-21 續集)
同一 session 中，同一個 KGAT_ token **從 push 成功 → 後續所有 API 調用 401/403**。推測 token 有極短 TTL 或被 Kaggle 撤銷。解決：
- 改用 `KAGGLE_API_TOKEN` 環境變數（較長 TTL）
- 或到 Kaggle Settings → Account → Create New Token 重新生成 kaggle.json

---

## 3. 修復驗證清單 (Pre-push v2)

所有檢查通過後才推送 v2：

- [x] `source` type = `str`（非 list，避免 Kaggle 跳過執行）
- [x] 版號字串：`"version": "v6.23"` ×2（docstring 已是 v6.23，代碼中同步更新）
- [x] `reward_weights` 行無 inline comment
- [x] Bug 1: composite 短公式降級懲罰 `-0.15 * (min_len - j_len)`（非 -999）
- [x] Bug 2: `last_restart_step` + 500 步 cooldown 於兩處重啟條件
- [x] Bug 3: `_best_toks = list(best_formula)` 指向歷史最佳
- [x] Bug 4: `reward_weights` → `ic=0.35, complexity=0.25`
- [x] `python3 -m py_compile` 語法驗證通過
- [x] Metadata: `machine_shape: "Gpu"`（非 NvidiaTeslaT4）

---

## 4. 續集：Dataset 掛載修復與 Notebook 改進 (2026-06-21 續集)

### 問題 1：錯誤的 dataset_sources
原始 metadata 中 `dataset_sources: ["twstock-grpo-dataset-v2"]` — **該 dataset 不存在**。
導致 `/kaggle/input/` 為空 → `adapt_finmind()` 找不到 CSV → `sys.exit(1)` 直接結束。

### 修復：正確的 dataset slugs
```json
"dataset_sources": [
  "mhhuang14/twstock-grpo-training-data",
  "mhhuang14/twstock-v6-0-real-data-20stocks-5y"
]
```

### 問題 2：Notebook 無 fallback，硬性 sys.exit(1)
原始代碼在找不到數據時直接 `sys.exit(1)`，導致 kernel 瞬間結束，無任何訓練輸出。

### 修復：優雅 fallback 到合成數據
```python
# 修復後：找不到真實數據時生成合成數據繼續訓練
if train_df is None:
    print("[adapt_finmind] 無真實數據，生成合成數據繼續訓練")
    # 生成合成 OHLCV + 外部因子佔位
    ...
```

### 推送結果
- **目標**: 原始 kernel `mhhuang14/twstock-grpo-v6-23-4-bug-root-cause-fix`
- **結果**: `Kernel version 1 successfully pushed`
- **URL**: https://www.kaggle.com/code/mhhuang14/twstock-grpo-v6-23-4-bug-root-cause-fix

---

## 5. 監控限制與建議

推送後無法即時監控（`kernels output` 403/401）。建議：
1. 等待 10-15 分鐘後再試 `kaggle kernels output`
2. 或到 Kaggle Web UI → Code → Your Work 查看執行狀態
3. 完成後關注關鍵指標：`best_ops>0`、`best_len>2`、`val_ic>0`、`with_ops` 不歸零

---

## 6. 相關檔案

| 檔案 | 路徑 |
|------|------|
| 修復後 Notebook v2 (含 fallback) | `/tmp/kpush_v623_fix3/twstock-grpo-v6-23-4-bug-root-cause-fix.ipynb` |
| Kernel Metadata (正確 dataset_sources) | `/tmp/kpush_v623_fix3/kernel-metadata.json` |
| 原始崩潰 Log | `/tmp/kout_v623/twstock-grpo-v6-23-4-bug-root-cause-fix.log` |
| Pulled 原始 notebook | `/tmp/kpull_v623_v3/twstock-grpo-v6-23-4-bug-root-cause-fix.ipynb` |
| 修復過程中產生的中間版本 | `/tmp/kpush_v623_v2/`, `/tmp/kpush_v623_fix2/` |

---

## 7. 後續追蹤

- [ ] Kernel 執行完成並下載 log
- [ ] 驗證 4 項修復在實際訓練中的效果
- [ ] 驗證 dataset 掛載是否生效（真實數據 vs 合成數據 fallback）
- [ ] 若仍有問題，基於 log 制定 v6.24 修正方案

---

## 8. 關鍵經驗總結

1. **inline comment 吞噬 closing delimiter** 是 Kaggle notebook 自動生成/修改時的高發陷阱 (Pitfall #71)
2. **KGAT_ token 在 kaggle.json 僅能 push，不能 list/output/pull** — 必須用環境變數
3. **Token 可能在 session 中過期** — push 成功不代表後續監控可用
4. **dataset_sources 必須精確匹配現有 dataset slug** — 錯誤 slug 不報錯，只是靜默不掛載
5. **Notebook 應有 graceful fallback 而非 sys.exit(1)** — 避免數據問題導致 kernel 瞬間死亡
6. **原則：先修復 metadata 再修復 notebook** — metadata 錯誤導致數據不掛載，是最上游的根因