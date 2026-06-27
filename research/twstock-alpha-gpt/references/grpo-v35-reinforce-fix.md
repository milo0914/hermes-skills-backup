# GRPO v3.5 REINFORCE 修復 — PPO On-Policy Loss=0 根因 D

## 日期：2026-06-09

## 問題

v3.4 kernel 執行完成後，訓練日誌顯示：
- `loss=-0.0000` 持續全部 steps
- `clip_ratio=0.0%`
- `mean_r` 從 step 500 後停滯不動

已修復根因 A（引導式解碼）、B（大小寫映射）、C（合成數據無信號），仍零收斂。

## 根因 D 數學推導

On-policy GRPO（single epoch）的 PPO clipped surrogate loss：

```
ratio = exp(log_π_new - log_π_new.detach()) = exp(0) = 1.0

advantages = (rewards - mean(rewards)) / std(rewards)
           → 標準化後 sum(advantages) = 0

loss = -min(ratio * advantage, clip(ratio, 1-ε, 1+ε) * advantage).mean()
     = -min(1.0 * A, 1.0 * A).mean()     （因為 ratio=1 在 clip 範圍內）
     = -mean(A)
     = -sum(A) / N
     = -0 / N
     = 0
```

**結論：PPO clipped surrogate 與 single-epoch on-policy GRPO 數學上不兼容。**

PPO 需要新舊策略差異產生非平凡 ratio（ratio ≠ 1），但 on-policy GRPO 每步都是當前策略自己跟自己比。

### 與根因 C (ratio gradient=0) 的區別

| 根因 | 症狀 | ratio 值 | d(ratio)/d(log_pi) | loss 值 |
|------|------|----------|---------------------|---------|
| C (v3.2) | `1.0 + 0.0 * log_pi` | 1.0 | 0.0 | 0（梯度為零） |
| C (v3.3 fix) | `exp(log_pi - log_pi.detach())` | 1.0 | 1.0 | 0（梯度非零但 loss=0） |
| D (v3.4/v3.5) | PPO on-policy | 1.0 | 1.0 | 0（advantages 均值=0） |

v3.3 修復了梯度消亡，但沒修復 loss=0。loss=0 的根因是 advantages 均值=0 + ratio≡1 → min(A,A)≡A → mean(A)=0。

## v3.5 修復

### 改用 REINFORCE Policy Gradient

DeepSeek-R1 的 GRPO 原論文使用的是 REINFORCE-style policy gradient，不是 PPO clipped surrogate：

```python
# v3.4 (PPO, loss≡0)
ratio = torch.exp(log_probs_tensor - log_probs_tensor.detach())
clipped = torch.clamp(ratio, 1 - clip_eps, 1 + clip_eps)
loss = -torch.min(ratio * advantages, clipped * advantages).mean()

# v3.5 (REINFORCE, genuine policy gradient)
loss = -(log_probs_tensor * advantages_tensor.detach()).mean()
```

REINFORCE 不需要 ratio，直接用 log_prob × advantage 作為梯度方向。當 advantage > 0 時增加該動作的機率，advantage < 0 時降低。

### 附加修改

1. **GPU 限制放寬 sm_70 → sm_50**：P100 (sm_60) 也可使用，避免被強制降級為 CPU-only
2. **移除 GradScaler**：REINFORCE 不需要混合精度穩定，CPU 模式下直接 `loss.backward()` 更穩定
3. **刪除 `_old_log_probs` 存儲**：REINFORCE 不需要 importance sampling，v3.3 的 off-policy 路徑 (T1) 同時解決

### 修改的程式碼位置 (grpo_regime_training_kaggle_v35.py)

| 行號 | 修改內容 |
|------|----------|
| ~40-50 | GPU capability check: sm_70 → sm_50 |
| ~1517-1518 | Loss formula: PPO clipped → REINFORCE `-(log_probs * advantages).mean()` |
| ~1549-1552 | 刪除 GradScaler 相關代碼，改為直接 `loss.backward()` + `optimizer.step()` |
| ~1549-1550 | 刪除 `_old_log_probs` 存儲（REINFORCE 不需要） |

## 縮排修復

v3.5 腳本推送後因 IndentationError 執行失敗（行 1549-1555 NaN guard 區塊縮排從 12sp 被壓縮為 4sp/1sp）。根因：write_file helper 腳本替換多行區塊時未保持與周圍代碼一致的縮排級別。

修復方式：用 Python 腳本 `/tmp/fix_v35_indent.py` 按行號精確修正縮排（以周圍正確行為參照），6 行修正（4sp→12sp, 8sp→16sp, 1sp→0sp）。

**注意**：即使 `py_compile` 本地驗證通過，推送後 Kaggle 仍可能因 tab/space 混合或 Unicode 空格等問題報 IndentationError。建議在修復腳本中加入 hex dump 檢查關鍵行。

## 待驗證

- [ ] 修復縮排後重新推送 v3.5 kernel
- [ ] 監控訓練日誌確認 loss 非 0
- [ ] 確認 GPU (T4/sm_75) 正常啟用
- [ ] 下載 best_strategy_per_regime.json

## v3.2 Runtime Observation (2026-06-09)

v3.2 實測確認 `_old_log_probs` off-policy 路徑從未觸發：

- L1527 `ratio = torch.exp(log_probs_tensor - log_probs_tensor.detach())` 是唯一被執行的路徑
- L1522-1526 的 off-policy ratio 計算（`ratio = exp(log_probs - self._old_log_probs[step])`）是死代碼——`_old_log_probs` 在 L1549-1550 存儲但從未在後續 step 被讀取（因每次 step 都重新生成公式，舊 log_prob 不適用於新公式）
- 12500 步全部 loss=-0.0000（4位小數格式），但改用 `.8f` 後可能顯示非零微小值
- 僅 financial regime (2882) 完成訓練，公式=NASDAQ_CLOSE（合成數據無意義）

此觀測確認 pitfall #44 的分析：off-policy importance sampling 在 GRPO 的每次重新生成公式架構下數學無意義。

## 核心教訓

1. **PPO 不是 GRPO 的正確實現** — DeepSeek-R1 的 GRPO 使用 REINFORCE + group-relative advantages，不是 PPO clipped surrogate
2. **On-policy + single-epoch = ratio≡1** — PPO 需要 off-policy 或 multi-epoch 才有非平凡 ratio
3. **修復 A/B/C 只解決了必要條件** — 沒有 A/B/C 的修復，模型連生成合法公式都做不到；但修復後 PPO 仍然 loss=0
4. **IndentationError 可能在本地驗證後仍發生** — 本地 py_compile 只檢查語法，不保證 Kaggle 執行環境的縮排一致
