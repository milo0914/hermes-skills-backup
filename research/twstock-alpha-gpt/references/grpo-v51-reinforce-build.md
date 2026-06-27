# GRPO v5.1 REINFORCE Fix Build (2026-06-09)

## 背景

v5 kernel（`mhhuang14/grpo-regime-aware-factor-training`）在 Kaggle T4 執行後，log 顯示兩個獨立 bug：

1. **Dataset 未掛載**：log 印出「無 Kaggle Dataset，使用合成數據」，儘管 `kernel-metadata.json` 的 `dataset_sources` 已指定 `mhhuang14/twstock-grpo-training-data`
2. **PPO loss≡0**：`loss=0.0000, mean_r=0.175→-0.504, clip_ratio=0%` — on-policy GRPO 中 ratio≡1.0 + advantages 均值=0 → PPO clipped surrogate loss 恆為零

## v5.1 三項修復

### Fix 1: Dataset Path — os.walk 遞迴搜尋

**根因**：Kaggle dataset 掛載路徑為三層巢狀 `/kaggle/input/datasets/{owner}/{slug}/{files}`，v5 用 `os.listdir` 只掃一層，找不到 CSV。

**修復**（grpo_regime_training_v51.py L2098）：
```python
# Before (v5):
for item in os.listdir(input_dir):
    ...

# After (v5.1):
for root, dirs, files in os.walk(input_dir):
    for fname in files:
        if fname == target_csv:
            data_path = root
            break
```

### Fix 2: PPO → REINFORCE

**根因**：on-policy single-epoch GRPO 中，`ratio = exp(log_pi - log_pi.detach()) = 1.0`，advantages 標準化後均值=0，`loss = -min(ratio*A, clip*ratio*A).mean() = -mean(A) = 0`。

**修復**（grpo_regime_training_v51.py L1531-1545）：
```python
# Before (v5 — PPO clipped surrogate):
ratio = torch.exp(log_probs_tensor - log_probs_tensor.detach())
clipped = torch.clamp(ratio, 1 - clip_eps, 1 + clip_eps)
loss = -torch.min(ratio * advantages, clipped * advantages).mean()

# After (v5.1 — REINFORCE policy gradient):
loss = -(log_probs_tensor * advantages.detach()).mean()
```

這才是 GRPO 原論文的正確實現。DeepSeek-R1 不使用 PPO clipped surrogate。

### Fix 3: group_size + lr_warmup_steps

- `group_size = 8` → `group_size = 16`（更穩定的 advantage 估計）
- `lr_warmup_steps = 200` → `lr_warmup_steps = 500`（更平滑的學習率預熱）

## 建構方法

使用 `/tmp/build_v51.py` Python 腳本做目標字串替換（非 patch），避免縮排腐蝕：

```python
with open(v5_source) as f:
    code = f.read()

# 3 targeted string substitutions
code = code.replace(old_dataset_scan, new_os_walk_scan)
code = code.replace(old_ppo_loss, new_reinforce_loss)
code = code.replace("group_size = 8", "group_size = 16")
code = code.replace("lr_warmup_steps = 200", "lr_warmup_steps = 500")

with open(v51_output, 'w') as f:
    f.write(code)

py_compile.compile(v51_output, doraise=True)  # SYNTAX OK
```

輸出：`grpo_regime_training_v51.py`（2356 行，v5 為 2358 行 — 刪除了 PPO ratio 計算的行數差）

## Push 細節

- `kernel-metadata.json`：`id = "mhhuang14/grpo-v51-reinforce-fix"`
- title 初版超過 50 字符 → 400 Bad Request
- 縮短為 `"GRPO v51 REINFORCE fix"` → push 成功
- Slug：`mhhuang14/grpo-v51-reinforce-fix`
- `kaggle kernels status` → `KernelWorkerStatus.RUNNING`

## 待驗證

- [ ] os.walk 成功找到真實數據（log 應印出「載入真實數據」而非 fallback 合成）
- [ ] REINFORCE loss 非 0（log 應印出非零 loss 值）
- [ ] reward 逐漸改善（mean_r 上升）
- [ ] 4 regime 全部完成訓練
- [ ] `best_strategy_per_regime.json` 產出

## 相關

- Pitfall #55 (twstock-alpha-gpt): PPO on-policy loss≡0 根因 D
- Pitfall #39/#70 (kaggle-api): Dataset 三層巢狀掛載路徑
- `references/grpo-v35-reinforce-fix.md`: REINFORCE 修復詳情
- `references/grpo-v5-three-bug-fix-build.md`: v5 3-bug fix 建構記錄
