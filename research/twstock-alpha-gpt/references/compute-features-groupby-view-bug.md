# compute_features groupby 迴圈 DataFrame View Bug

**發現日期**: 2026-06-09
**嚴重度**: P0 — 靜默丟失數據，導致只有最後一檔股票被訓練
**影響檔案**: `grpo_regime_training_kaggle.py` (Kaggle notebook), `ai_dig_money_core.py` (本地版)

## 症狀

`TWFeatureEngineer.compute_features()` 傳入 4 檔股票的 df（3372 rows），但回傳的 feat_df 只有 2882 的 843 rows。其他 3 檔（2330/2454/1301）完全丟失。

## 根因

```python
result_frames = []
for stock_id, g in df.groupby("stock_id"):
    # ... 大量特徵計算 ...
    result_frames.append(g[keep_cols])  # BUG: view, not copy

result = pd.concat(result_frames, ignore_index=True)
```

`g[keep_cols]` 回傳的是 DataFrame view（淺拷貝），不是獨立物件。當下一個 groupby 迭代中 `g` 被重新賦值時，list 中之前 append 的 frame 仍然指向已經被修改的 DataFrame。最終 concat 時，所有 frames 實際指向同一個（最後一個）DataFrame 物件。

## 為什麼每檔單獨呼叫正常？

單獨呼叫只有一個 groupby 迭代，view 不會被後續迭代覆蓋，所以結果正確。只有在多檔全量呼叫時才觸發。

## 修復

```python
result_frames.append(g[keep_cols].copy())  # FIX: explicit copy
```

## 診斷方法

### 方法 1: Monkey-patch pd.concat

```python
_orig_concat = pd.concat
def _tracked_concat(frames, **kw):
    print(f"CONCAT: {len(frames)} frames, stocks={[f['stock_id'].unique() if 'stock_id' in f.columns else '?' for f in frames]}")
    return _orig_concat(frames, **kw)
pd.concat = _tracked_concat
# ... call compute_features ...
pd.concat = _orig_concat
```

結果：`CONCAT: 1 frames: [(843, array([2882]))]` — 只有 1 個 frame 而非 4 個。

### 方法 2: id() 比對

在 append 前後印 `id(g[keep_cols])`，若所有 frame 的 id 相同或指向同一底層資料，即為 view bug。

### 方法 3: 追蹤 list 長度

在 append 前印 `len(result_frames)` 和 `id(result_frames)`。如果 append 被呼叫了 4 次但 concat 只收到 1 個 frame，問題是 frames 被覆蓋而非 list 本身。

## 延伸檢查

此 bug 不只影響 `compute_features`。任何 pandas groupby 迴圈中使用 `result_list.append(g[subset])` 而不加 `.copy()` 的模式都可能觸發。搜尋所有 groupby 迴圈中的 append 呼叫：

```bash
grep -n "groupby" script.py | head -20
grep -n "result_frames.append\|result_list.append\|frames.append" script.py
```

## 已確認需修復的位置

1. `grpo_regime_training_kaggle.py` L606: `result_frames.append(g[keep_cols])` → `.copy()`
2. `ai_dig_money_core.py` 的 compute_features 中同樣位置（需驗證是否也有此問題）

## 2026-06-10 補充：Kaggle notebook 仍存在此 bug

v33 成功執行的 kernel (`mhhuang14/grpo-v33-dsfix`) 也只輸出了 2882 (FINANCIAL regime) 的訓練結果，`best_strategy_per_regime.json` 和 `training_history.json` 中只有 `{"2882": ...}`。其他 3 檔 (2330/2454/1301) 完全缺失。

**診斷過程**：
1. 下載 v33 output → 確認只有 2882
2. 本地生成合成數據 (4 檔, 500 天) → compute_features 只輸出 2882
3. **手動重構 compute_features** (複製邏輯但用獨立變數) → 輸出正確 (4 檔)
4. 用 monkey-patch 追蹤 → 發現 groupby 迴圈只迭代 1 次 (2882)
5. 確認輸入 df 含 4 檔 → 問題在 append view 而非 groupby 本身

**「原始版 vs 重構版對比」診斷模式**：
當 groupby bug 靜默丟失數據時，最有效的診斷方法是寫一個「重構版」——
從原始碼逐行複製 compute_features 的核心邏輯，但用獨立變數名和顯式 .copy()。
如果重構版正常但原始版只輸出最後一檔，差異就是 view vs copy。
此模式比在原始碼中加 debug print 更可靠，因為原始碼的 view 行為可能被 print 本身改變
（某些 pandas 操作在 print 時會觸發 copy-on-write，掩蓋 bug）。

## 診斷腳本

`scripts/diagnose_groupby_view_bug.py` — 自動化診斷工具：
1. 靜態掃描 groupby + append 模式（標記缺少 .copy() 的位置）
2. 生成 4 檔測試數據，實際執行 compute_features
3. 比對輸入/輸出股票數，確認 bug 是否存在

用法：`python3 scripts/diagnose_groupby_view_bug.py grpo_regime_training_kaggle.py compute_features`
