# GRPO v3.3 — log_prob Shape Mismatch Fix

## 問題

v3.2-fix kernel 在 `train_torch_regime()` 的 `torch.stack(all_log_probs)` 拋出：

```
RuntimeError: stack expects each tensor to be equal size, but got [1] at entry 0 and [] at entry 2
```

## 根因

Model forward 回傳 logits 形狀 `(B, T, vocab)` 其中 B=1。

| 路徑 | 取 logits 方式 | Categorical logits shape | log_prob shape |
|------|----------------|-------------------------|----------------|
| 主迴圈 | `logits[:, -1, :].squeeze(0)` | `(vocab,)` | scalar `[]` ✓ |
| warmup | `warmup_logits[:, -1, :]` (無 squeeze) | `(1, vocab)` | `[1]` ✗ |
| fallback | `fb_logits[:, -1, :]` (無 squeeze) | `(1, vocab)` | `[1]` ✗ |

PyTorch `Categorical` 若接收 2D logits `(1, vocab)`，視為 batch=1，回傳 1D log_prob `(1,)`。
若接收 1D logits `(vocab,)`，回傳 scalar log_prob `()`。

Warmup 路徑（前 500 步前半 group）和 fallback 路徑（公式不完整時）都缺少 `.squeeze(0)`，
導致 `all_log_probs` 列表中混合 `[1]` 和 `[]` 形狀的 tensor，`torch.stack` 失敗。

## 修復 (v3.3)

### 1. warmup 路徑加 `.squeeze(0)`

```python
# Before (v3.2)
warmup_dist = torch.distributions.Categorical(
    logits=warmup_logits[:, -1, :])

# After (v3.3)
warmup_dist = torch.distributions.Categorical(
    logits=warmup_logits[:, -1, :].squeeze(0))
```

### 2. fallback 路徑加 `.squeeze(0)`

```python
# Before (v3.2)
fb_dist = torch.distributions.Categorical(
    logits=fb_logits[:, -1, :])

# After (v3.3)
fb_dist = torch.distributions.Categorical(
    logits=fb_logits[:, -1, :].squeeze(0))
```

### 3. torch.stack 前強制 reshape 為 0-dim scalar（保險）

```python
# v3.3 safety net — 比 .squeeze() 更可靠
# .squeeze() 對 scalar `[]` 不做任何事（返回原 tensor）
# .reshape(()) 強制將 [1] → [] 和 [] → []，統一為 0-dim
all_log_probs = [lp.reshape(()) for lp in all_log_probs]
log_probs_tensor = torch.stack(all_log_probs)
```

### 4. keep_cols 過濾（附帶修復）

```python
# Before (v3.2) — 保留所有欄位，可能含未正規化的小寫版本
result_frames.append(g)

# After (v3.3) — 只保留 date + stock_id + 22 個大寫特徵
keep_cols = ["date", "stock_id"] + list(FEATURE_NAMES)
result_frames.append(g[keep_cols])
```

此修復解決診斷列印時 ABSORPTION mean=14639 的問題（讀到未正規化小寫 `absorption` 而非正規化大寫 `ABSORPTION`）。

## 驗證

- v3.2-fix kernel log 確認：22 因子計算正確、4 regime 分群正確、模型初始化成功（92,711 params）
- 錯誤僅發生在第一步 train_torch_regime 的 `torch.stack(all_log_probs)`
- v3.3 kernel 已 push: `mhhuang14/grpo-v3-3-regime-alpha-factor-training`

## 相關 Pitfalls

- Pitfall #32: PPO ratio 梯度消亡（不同問題：ratio=1.0+0.0*log_probs 梯度為零）
- Pitfall #6: GRPO 零收斂根因 A（StackVM 隨機生成）、B（大小寫映射）、C（合成數據）
- Pitfall #25: patch 工具縮排腐蝕（本修復過程中也觸發，需 write_file helper 修復）

## 經驗教訓

1. **所有傳給 Categorical 的 logits 都必須 squeeze batch dim** — 這是 PyTorch 的隱式行為，不會報錯但會改變輸出形狀
2. **`reshape(())` 比 `.squeeze()` 更適合保險用途** — squeeze 對已經是 scalar 的 tensor 是 no-op，但 reshape 會強制形狀
3. **`result_frames.append(g)` 應一律用 keep_cols 過濾** — 避免 DataFrame 中同時存在大小寫版本造成混淆
