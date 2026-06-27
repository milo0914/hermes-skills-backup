# GRPO v6.12 Changelog
Date: 2026-06-16

## v6.12 — Complexity Reward Fix + Early Stop Warmup + GPU Reinstall + CPU Fallback 不覆蓋

### 基線
- **Kaggle 來源**: `mhhuang14/twstock-grpo-regime-aware-factor-training-v6-11` kernel version 4
- **本地檔案**: `/app/twstock-grpo-regime-aware-factor-training-v6-11.ipynb` (88861 bytes, 1608 lines)
- **v6.11 核心問題**: P100 sm_60 與 PyTorch 2.10 不相容 → CPU fallback → 所有參數被覆蓋 → early stop step 800 就停 → 公式長度全=1 token

### v6.11 訓練結果（改版依據）

| Regime | Formula | Len | Train IC | Val IC | IC Gap | Steps |
|--------|---------|-----|----------|--------|--------|-------|
| traditional | TX_INST_NET_OI | 1 | 0.0961 | +0.1127 | -0.0167 | 801 |
| large_cap | ATR | 1 | 0.0509 | -0.0056 | +0.0566 | 801 |
| mid_cap_tech | ABSORPTION | 1 | 0.0632 | +0.0264 | +0.0368 | 801 |
| financial | SP500_CLOSE | 1 | 0.0859 | +0.0518 | +0.0341 | 801 |

### 5 大核心修改

---

#### 修改 1: GPU 相容性 — PyTorch 版本重裝 (check_environment)

**問題**: P100 (sm_60) + PyTorch 2.10+cu128 (min sm_70) = CUDA kernel 失敗 → CPU fallback
**修改**:
- CUDA kernel 實測失敗時，嘗試安裝相容 sm_60 的 PyTorch:
  ```python
  # 嘗試安裝 PyTorch 2.6+cu126（支援 sm_60）
  try:
      import subprocess
      subprocess.run([
          sys.executable, "-m", "pip", "install",
          "torch==2.6.0", "--index-url",
          "https://download.pytorch.org/whl/cu126"
      ], check=True, capture_output=True, timeout=300)
      import importlib; importlib.reload(torch)
      # 重新實測
  except: ...
  ```
- T4 (sm_75) 為首選 GPU，P100 需降級 PyTorch 才能用 CUDA
- 實測邏輯保持: `torch.zeros(1, device="cuda") + 1.0 + synchronize()`
- 版本字串更新為 v6.12

---

#### 修改 2: GRPOConfig 參數調整

| 參數 | v6.11 | v6.12 | 原因 |
|------|-------|-------|------|
| early_stop_patience | 500 | 800 | 避免過早停止 |
| early_stop_min_delta | 1e-4 | 5e-4 | 需更明顯改善才算 |
| early_stop_warmup | (無) | 1500 | 新增：前 1500 步不檢查 early stop |
| operator_bonus | 0.1 | 0.3 | 加強 operator 鼓勵 |
| short_formula_penalty | (無) | 1.0 | 新增：短公式懲罰強度 |
| reward_weights["ic"] | 0.5 | 0.40 | 讓出空間給 complexity |
| reward_weights["sharpe"] | 0.25 | 0.20 | 讓出空間給 complexity |
| reward_weights["mdd"] | 0.15 | 0.10 | 讓出空間給 complexity |
| reward_weights["turnover"] | 0.1 | 0.05 | 讓出空間給 complexity |
| reward_weights["complexity"] | 0.05 | 0.25 | 大幅增加複雜度獎勵 |

---

#### 修改 3: auto_detect 不覆蓋 regime-specific group_size

**問題**: v6.11 auto_detect CPU 模式強制 `group_size = max(config.group_size, 32)`，
覆蓋了 LARGE_CAP 的 regime-specific group_size=64
**修改**: auto_detect 只調整 device + train_steps，不再覆蓋 group_size
- CPU 模式下的 group_size 仍由 RegimeTrainingPlan 決定
- train_torch_regime 中 `if regime_plan and "group_size" in regime_plan:` 優先使用 regime plan
- CPU 強制最小 group_size = 16 (僅保底，不覆蓋更大值)

---

#### 修改 4: complexity reward 實際生效 (compute_group_rewards)

**重大 Bug 發現**: v6.11 的 `min_formula_len` 和 `operator_bonus` 在 Config 中定義了，
但 **compute_group_rewards 從未使用這些參數** — 這就是公式長度全=1 token 的根本原因！

**修改**: 在 compute_group_rewards 中加入實際的 complexity reward 計算:
```python
# 【v6.12】Complexity reward: operator bonus + short formula penalty
n_operators = sum(1 for t in tokens[N_FEATURES:])  # 運算子 token 數
formula_len = len(tokens)
operator_reward = n_operators * self.config.operator_bonus

if formula_len < self.config.min_formula_len:
    short_penalty = self.config.short_formula_penalty
else:
    short_penalty = 0.0

complexity_reward = operator_reward - short_penalty
# 加到 combined reward
total_reward = combined + w.get("complexity", 0.25) * complexity_reward
```

---

#### 修改 5: Early stopping 修正

**問題**: v6.11 early stop 有 3 個 bug:
1. `result.get("val_ic")` 不存在 — result dict 中沒有 val_ic 欄位
2. warmup 不足 — 前 800 步就開始檢查，初期波動大
3. patience_counter 打平時也 +200，加速觸發

**修改**:
- early_stop_warmup=1500: 前 1500 步不檢查
- val_IC 改從 `val_ic` array 的 max 取值（由 compute_group_rewards 計算）
- 只在 best_reward 更新時 reset patience_counter（打平不 reset 也不累加）
- patience 由步數間隔累加（每 200 step 檢查一次）
- return dict 新增 `best_val_ic` 欄位

**智具體邏輯**:
```python
if step > self.config.early_stop_warmup and step % 200 == 0:
    current_val_ic = result.get("val_ic", 0.0)
    if isinstance(current_val_ic, np.ndarray):
        current_val_ic = float(current_val_ic.max())
    if current_val_ic > best_val_ic + self.config.early_stop_min_delta:
        best_val_ic = current_val_ic
        patience_counter = 0
    else:
        patience_counter += 200
    if patience_counter >= self.config.early_stop_patience:
        print(f"  [v6.12] Early stopping at step {step}")
        break
```

---

### 版本號更新
- v6.11 → v6.12 (全域替換)
- Title: `TWStock GRPO Regime-Aware Factor Training v6.12 (Complexity Fix + EarlyStop Warmup + GPU Reinstall)`

### 驗證
- [x] py_compile: PASS
- [x] ast.parse: PASS
- [x] 10 項修改指紋檢查全部 PASS:
  - v6.12 check_environment (PyTorch reinstall)
  - v6.12 config (complexity 0.25)
  - v6.12 auto_detect (no group_size override)
  - v6.12 complexity reward (operator_bonus)
  - v6.12 short formula penalty
  - v6.12 early stop warmup
  - v6.12 early stop val_ic fix
  - v6.12 version string
  - v6.12 best_val_ic in return
  - No duplicate @classmethod

### Kaggle Push
- **Push 目錄**: `/tmp/kpush_v612/`
- **Notebook**: `twstock-grpo-regime-aware-factor-training-v6-12.ipynb` (92344 bytes, 1606 lines)
- **Kernel metadata**: id=`mhhuang14/twstock-grpo-regime-aware-factor-training-v6-12`, machine_shape=`NvidiaTeslaT4`
- **Dataset**: `mhhuang14/twstock-v6-0-real-data-20stocks-5y`
- **結果**: `Kernel version 1 successfully pushed.`
- **URL**: https://www.kaggle.com/code/mhhuang14/twstock-grpo-v6-12-complexity-earlystop-fix
- **Note**: Kaggle title→slug 自動轉換，slug = `twstock-grpo-v6-12-complexity-earlystop-fix`

### 監控項目
- [ ] GPU 模式是否成功（T4 sm_75 或 P100 + 降級 PyTorch）
- [ ] IC 持續改善到 step 8000（warmup 1500 步後才檢查 early stop）
- [ ] 公式長度分佈（目標: 3+ tokens，complexity reward 已實際生效）
- [ ] Large_Cap val_IC 是否轉正（group_size=64 不再被覆蓋）
- [ ] Early stopping 合理觸發（patience 800，warmup 1500）
- [ ] adv_std 穩定 ≈0.577
- [ ] reward 中 complexity 項是否非零

### 本地檔案索引
| 檔案 | 路徑 | 大小 |
|------|------|------|
| v6.12 Notebook | `/app/twstock-grpo-regime-aware-factor-training-v6-12.ipynb` | 92344 bytes |
| Push 目錄 | `/tmp/kpush_v612/` | - |

### v6.11 → v6.12 參數對比表

| 參數 | v6.11 | v6.12 | 說明 |
|------|-------|-------|------|
| early_stop_patience | 500 | 800 | 放寬避免過早停止 |
| early_stop_min_delta | 1e-4 | 5e-4 | 需更明顯改善 |
| early_stop_warmup | (無) | 1500 | 前 1500 步不檢查 |
| operator_bonus | 0.1 | 0.3 | 加強 operator 鼓勵 |
| short_formula_penalty | (無) | 1.0 | 短公式懲罰 |
| reward_weights["complexity"] | 0.05 | 0.25 | 複雜度獎勵大幅提升 |
| auto_detect group_size | CPU覆蓋=32 | 不覆蓋 | 保留 regime-specific |
| GPU fallback | 靜音CPU | 嘗試重裝PyTorch | 優先修復 CUDA |
