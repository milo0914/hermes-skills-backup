# compute_features v3.2 merge 修復 + FormulaDecoder token 映射修正

日期：2026-06-08

## 問題 1：pandas level_0 衝突

### 症狀
Kaggle kernel v3-1 (script 模式) 執行失敗：
```
ValueError: cannot insert level_0, already exists
```
出現在 compute_features 中 groupby("stock_id") 迴圈內。

### 根因
groupby 後 g 的 index 含 group key (stock_id)。舊模式：
```python
inst_df = inst_df.set_index('date').reindex(g.index).reset_index()
```
第一次 reset_index 把 stock_id 放回 columns，第二次 reset_index 發現欄位已存在，嘗試用 level_0 命名 → 衝突。

### 修復
4 處 set_index/reindex/reset_index 全部改為 merge 模式：
```python
# 舊 (會觸發 level_0 衝突)
inst_df = inst_df.set_index('date').reindex(g.index).reset_index()

# 新 (merge 模式，安全)
inst_cols = ['date', 'foreign_net', 'trust_net', 'dealer_self_net', 'total_net']
g = pd.merge(g, inst_df[inst_cols], on='date', how='left')
```

4 處修正位置：
1. 法人買超 (inst_df) — ~行 1450
2. 融資融券 (margin_df) — ~行 1480
3. 期貨OI (futures_oi_df) — ~行 1530
4. 美股指數 (us_indices_df) — ~行 1570

groupby 迴圈開頭加 `g = g.reset_index(drop=True)` 清理 index。

### 修復腳本
```python
# /tmp/fix_level0_bug.py — 自動修復前 3 處
# /tmp/fix_us_indices.py — 手動修復第 4 處（美股指數段，正則未匹配因空白差異）
```

### 驗證
```bash
python3 -c "import py_compile; py_compile.compile('ai_dig_money_core.py', doraise=True); print('SYNTAX OK')"
# 也用 grep 確認無殘留 set_index：
grep '\.set_index(' ai_dig_money_core.py  # 應返回 0 matches
```

---

## 問題 2：FormulaDecoder token 映射錯誤

### 症狀
反編譯 GRPO 生成的公式時，v3.1 新增的 6 個因子 (token 16-21) 被誤判為 operator。

### 根因
```python
# ai_dig_money_core.py 行 1814 (修復前)
n_features = len(TW_FEATURE_NAMES)  # 16，而非 22
# 行 1819
parts.append(TW_FEATURE_NAMES[t])   # token 16-21 超出索引 → 被當成 operator
```

TW_FEATURE_NAMES 只有 16 個元素，ALL_FEATURE_NAMES 有 22 個。Token 16-21 應映射到 V3_1_EXTRA_FEATURES (TX_INST_NET_OI, MTX_RETAIL_OI, TX_MTX_SPREAD, NASDAQ_CLOSE, SP500_CLOSE, DOWJONES_CLOSE)，但被誤映射到 operator 區間 (ADD=22, SUB=23, ...)。

### 修復
```python
n_features = len(ALL_FEATURE_NAMES)  # 22
parts.append(ALL_FEATURE_NAMES[t])   # 正確映射 token 0-21 → feature, 22-33 → operator
```

### 教訓
**每次修改 FEATURE_NAMES 列表後，必須 grep 檢查所有引用處**：
```bash
grep -n 'TW_FEATURE_NAMES\|ALL_FEATURE_NAMES' ai_dig_money_core.py
```
此 BUG 不會產生語法錯誤或執行錯誤，只能靠人工審查或比對反編譯輸出發現。

---

## Kaggle kernel 版本歷史

| 版本 | 模式 | 狀態 | 失敗原因 |
|------|------|------|----------|
| v3-1 (script) | GPU P100 | ❌ 失敗 | sm_60 不相容 + level_0 衝突 |
| v14 (notebook) | GPU T4 | ❌ 未執行 | GPU session 上限 2/2 已滿 |
| v16 (notebook) | CPU-only | 🔄 監控中 | 佇列中，cron 每 10 分鐘檢查 |

CPU-only metadata (無 enable_gpu/machine_shape) 可繞過 GPU session 限制，但訓練較慢。
