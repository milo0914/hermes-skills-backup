# GRPO v6.11 核心程式碼片段

從 `/app/twstock-grpo-regime-aware-factor-training-v6-11.ipynb` 提取的關鍵變更程式碼。
完整 notebook 在 Kaggle: `mhhuang14/twstock-grpo-regime-aware-factor-training-v6-11`

---

## 1. GPU 相容性檢查 (check_environment)

```python
def check_environment():
    print("=" * 60)
    print(" 台股 GRPO Regime-Aware 因子訓練 (Kaggle GPU) - v6.11 ...")
    
    import torch
    gpu_compatible = False
    if torch.cuda.is_available():
        gpu_name = torch.cuda.get_device_name(0)
        gpu_mem = torch.cuda.get_device_properties(0).total_memory / 1e9
        cc = torch.cuda.get_device_capability(0)
        print(f"  GPU: {gpu_name} ({gpu_mem:.1f} GB), CUDA capability sm_{cc[0]}{cc[1]}")
        if cc[0] >= 5:                          # v6.11: sm_50+
            gpu_compatible = True
            # 【v6.11】實測 CUDA kernel 是否可執行
            try:
                _test = torch.zeros(1, device="cuda")
                _ = _test + 1.0
                torch.cuda.synchronize()
                print(f"  CUDA kernel 實測: PASS")
            except RuntimeError as e:
                gpu_compatible = False
                print(f"  CUDA kernel 實測: FAIL ({e}), 使用 CPU fallback")
            print(f"  GPU 相容: sm_{cc[0]}{cc[1]} >= sm_50 ✓")
        else:
            print(f"  GPU 不相容: sm_{cc[0]}{cc[1]} < sm_50，將使用 CPU fallback")
    else:
        print("  WARNING: No GPU detected, using CPU (slow)")
```

**v6.9→v6.10→v6.11 GPU 門檻演進:**
- v6.9: `cc[0] >= 7` (sm_70)
- v6.10: `cc[0] >= 6` (sm_60)
- v6.11: `cc[0] >= 5` (sm_50) + CUDA kernel 實測

---

## 2. GRPOConfig (v6.11 新增/修改參數)

```python
@dataclass
class GRPOConfig:
    group_size: int = 64          # v6.5: 從16提升到64
    batch_size: int = 256         # v6.5: 配合group_size=64 增加batch
    train_steps: int = 8000       # v6.11: 15000→8000 (IC 在 step 1000 後停滯)
    entropy_coef: float = 0.25    # v6.11: 0.15→0.25 (更強探索)
    
    # --- v6.11 新增參數 ---
    advantage_method: str = "rank"      # "rank" (v6.11) 或 "zscore" (v6.8 舊法)
    min_group_size: int = 8            # 動態 group_size 下限 (v6.9: 16→8)
    early_stop_patience: int = 500      # 【v6.11】IC 連續 N steps 無改善就停止
    early_stop_min_delta: float = 1e-4   # 【v6.11】最小改善閾值
    min_formula_len: int = 3            # 【v6.11】懲罰 len(tokens) < 3
    operator_bonus: float = 0.1         # 【v6.11】每個 operator 的 reward bonus
    adv_std_threshold: float = 0.05      # 低於此值觸發 group_size 縮小 (v6.9: 0.1→0.05)
    reward_weights: dict = field(default_factory=lambda: 
        {"ic": 0.5, "sharpe": 0.25, "mdd": 0.15, "turnover": 0.1, "complexity": 0.05})
    use_multi_objective: bool = True
    # ... 其餘參數同 v6.9
```

**v6.10→v6.11 參數對照:**

| 參數 | v6.10 | v6.11 | 原因 |
|------|-------|-------|------|
| train_steps | 15000 | 8000 | IC 在 step 1000 後停滯 |
| entropy_coef | 0.15 | 0.25 | 保留探索動力 |
| adv_std_threshold | 0.1 | 0.05 | 更靈敏觸發 |
| min_group_size | 16 | 8 | 允許更小 group |
| early_stop_patience | (無) | 500 | 新增 early stop |
| early_stop_min_delta | (無) | 1e-4 | 新增 early stop |
| min_formula_len | (無) | 3 | 新增複雜度獎勵 |
| operator_bonus | (無) | 0.1 | 新增複雜度獎勵 |
| reward_weights | IC/Sharpe/MDD/Turnover | + complexity:0.05 | 新增維度 |
| temperature_decay_steps | 5000 | 8000 | 溫度衰減延長 |
| temperature_end | 0.5 | 0.8 | 保留探索 |

---

## 3. Regime-specific group_size (RegimeConfig)

```python
REGIME_CONFIGS = {
    StockRegime.TRADITIONAL:  {"group_size": 16, ...},    # 不變
    StockRegime.LARGE_CAP:    {"group_size": 64, ...},   # v6.11: 16→64 (val_IC 負值需探索)
    StockRegime.MID_CAP_TECH: {"group_size": 24, ...},  # v6.11: 12→24 (IC 退化需探索)
    StockRegime.FINANCIAL:    {"group_size": 16, ...},   # 不變
}
```

---

## 4. Early Stopping 邏輯 (train_one_regime 內)

```python
def train_one_regime(self, ...):
    best_formula, best_reward, history = None, -float("inf"), []
    G = self.config.group_size
    # 【v6.11】Early stopping 追蹤
    best_val_ic = -float("inf")
    patience_counter = 0
    best_step = 0
    
    for step in range(self.config.train_steps):
        # ... 訓練邏輯 ...
        
        if result["rewards"][best_idx] > best_reward:
            best_reward = result["rewards"][best_idx]
            best_formula = all_tokens[best_idx]
            best_step = step
            patience_counter = 0  # 【v6.11】重置 patience
        
        # 【v6.11】Early stopping: 檢查 val_IC 是否停滯
        if hasattr(self.config, "early_stop_patience") and step % 200 == 0 and step > 0:
            current_val_ic = result.get("val_ic", best_reward * 0.1)
            if current_val_ic > best_val_ic + self.config.early_stop_min_delta:
                best_val_ic = current_val_ic
                patience_counter = 0
            else:
                patience_counter += 200
            if patience_counter >= self.config.early_stop_patience:
                print(f"  [v6.11] Early stopping at step {step}: val_IC 停滯 {patience_counter} steps")
                break
    
    return {
        "best_formula": best_formula,
        "best_reward": best_reward,
        "regime": regime_name,
        "n_steps": step + 1,  # 【v6.11】實際訓練步數（非 config.train_steps）
        "best_step": best_step,  # 【v6.11】最佳公式的 step
        "history": history,
    }
```

**關鍵設計:**
- 每 200 step 檢查 val_IC（非每 step）
- patience_counter 每次無改善 +200（不是 +1）
- 觸發條件: `patience_counter >= early_stop_patience (500)`
- 最早觸發時機: step 600 (200+200+200=600 ≥ 500)
- n_steps 回報實際步數，不是 config.train_steps
