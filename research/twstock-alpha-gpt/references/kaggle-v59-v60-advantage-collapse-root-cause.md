# Kaggle v5.9 COMPLETE + v6.0 Root Cause Fix

## v5.9 訓練結果 (2026-06-11)

**Kernel**: mhhuang14/grpo-regime-aware-factor-training-v5-9
**Status**: COMPLETE
**Environment**: P100 (sm_60) → CPU fallback (G=16), 合成數據

### 各 Regime 結果

| Regime | Formula | Train IC | Val IC | IC Gap | Verdict |
|--------|---------|----------|--------|--------|---------|
| traditional | MOM_REV | +0.042 | +0.116 | -0.074 | 唯一正常 (val>train) |
| large_cap | SURF_ENTRY | +0.529 | -0.311 | +0.839 | 嚴重過擬合 |
| mid_cap_tech | DEV | +0.024 | -0.087 | +0.111 | 無信號 |
| financial | DEV | +0.042 | +0.002 | +0.040 | 無信號 |

所有 regime 只輸出單一 token (formula_tokens=[4]或[12]或[15])，StackVM 執行1步就停止。

### 三大根因

1. **P100→CPU fallback (致命)**: v5.9 代碼判斷 sm_60 < sm_70 為不相容，強制 CPU。但 PyTorch 2.x 完全支援 P100 (sm_60)，這是錯誤判斷。
2. **合成數據同質性 (致命)**: v5.9 版本1 未載入真實數據。同 regime 5檔合成股票行為完全相同 → G=16 個 sample reward 幾乎一致 → advantage std=0.00e+00 全程。
3. **公式退化**: 只收斂到單 token 公式 (DEV/MOM_REV/SURF_ENTRY)，缺乏長度或新穎性激勵。

### Log 關鍵證據

- `adv_std=0.00e+00` 從 step ~500 開始持續到 step 8000
- `[v5.9] Adv near-zero (std=0.00e+00), adding small noise` 每步觸發
- Gumbel noise 注入到 logits 不影響 reward 計算 → 無法打破 advantage 死循環
- `step 7800: loss=0.6700 mean_r=0.000 best_r=0.418` — 後期 reward 歸零

## v6.0 修復方案 (5 大改動)

### FIX 1: 移除 P100 CUDA 拒絕邏輯 (已實施)

```python
# v5.9 (WRONG):
if cc[0] >= 7:
    gpu_compatible = True  # P100 sm_60 被拒
else:
    os.environ["GRPO_FORCE_CPU"] = "1"

# v6.0 (CORRECT):
if torch.cuda.is_available():
    gpu_compatible = True  # P100 sm_60 可以跑 PyTorch 2.x
# 不再有 sm 版本門檻檢查
```

**重要更正**: Pitfall #35 和 #86 中的 `cc[0] >= 7` 門檻是錯誤的。P100 (sm_60) 完全可以執行 PyTorch 2.x 的 CUDA ops。v5.7 實測的 CUDA error 是因為 Kaggle 預裝的是 `PyTorch+cpu` 版本而非 `+cu128`，不是因為 sm_60 不相容。正確的修復是確保安裝 CUDA 版 PyTorch（`pip install torch --index-url .../cu128`），而非拒絕 P100。

### FIX 2: Rank-based advantage normalization (已實施)

```python
# v5.9: advantages = (r - mean) / std → 當 std≈0 全歸零
# v6.0: 當 std < 0.01 時用排名歸一化
if group_std < 0.01:
    ranks = np.zeros_like(rewards)
    valid_rewards = rewards[valid_mask]
    order = np.argsort(valid_rewards)
    rank_vals = np.zeros(len(valid_rewards))
    rank_vals[order] = np.linspace(-1, 1, len(valid_rewards))
    ranks[valid_mask] = rank_vals
    advantages = np.where(valid_mask, ranks, 0.0)
```

排名歸一化確保即使 reward 差異極小，仍有有效的 advantage 梯度。

### FIX 3: Reward shaping — exploration + length bonus (已實施)

```python
bonus = 0.0
formula_len = len(formula_tokens)
if 3 <= formula_len <= 8:
    bonus += 0.1  # 鼓勵適當長度公式
if formula_tokens != self.best_formula_tokens:
    bonus += 0.05  # 鼓勵新穎公式
rewards.append(np.clip(base_reward + bonus, -clip, clip))
```

防止退化到單 token 公式。

### FIX 4: best_formula_tokens 追蹤 (待完成)

需要在 train_torch_regime 迴圈中追蹤歷史最佳公式 token，供 novelty bonus 使用。

### FIX 5: 真實數據載入優先 (待完成)

v6.0 main() 必須優先使用 Kaggle dataset 的真實 CSV（20檔×725日），而非合成 fallback。

## 已備妥資源

- 真實數據 dataset v2: `mhhuang14/twstock-grpo-training-data`
  - twstock_daily.csv (1.27MB, 20檔×725日, 長格式)
  - us_indices.csv (41KB, NASDAQ/SP500/DJIA 725日)
  - futures_oi.csv (58KB, TWII proxy 725日, 無NaN)
- v6.0 腳本: /tmp/v60_full_script.py (3/5 修復完成, 語法OK)
- GPU 額度: 本週30h已用盡, 需等恢復

## Pitfall 更正

**Pitfall #35 和 #86 需要修正**: 原文說 "P100 (sm_60) 與 PyTorch 2.10 不相容" 是錯誤結論。真正的原因是 Kaggle 預裝 `PyTorch+cpu` 版本。安裝 `+cu128` 後 P100 可以正常執行 CUDA ops。sm_60 門檻拒絕邏輯應完全移除，只保留 `torch.cuda.is_available()` 檢查。
