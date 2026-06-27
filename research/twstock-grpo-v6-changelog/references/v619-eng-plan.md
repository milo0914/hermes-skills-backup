# TWStock GRPO v6.19 Eng Plan — Composite Score Full Fix + Notebook Audit Repairs

## 緣起

v6.18 training output 顯示 val_ic=0.1093 創歷史新高，但 best_formula 仍是單變數 `TX_MTX_SPREAD`（len=1, ops=0），且 best_reward=-1.27。逐行審計 notebook 原始碼後發現 **v6.18 Eng Plan 的 6 項修復中，P0 的 composite score 選擇邏輯僅半實作**，導致核心問題未被解決。

## 審計發現摘要（7 大缺陷）

| Bug ID | 缺陷 | 行號 | 嚴重度 | 衝擊 |
|--------|------|------|--------|------|
| AUDIT-1 | best_idx 仍為 reward-argmax (`np.argmax(rewards)`) | L951 | P0 | Composite score 只算 reward 最高那一個 formula |
| AUDIT-2 | Composite score 未遍歷全 group，只看 best_idx | L1427-1439 | P0 | 錯失真正高 composite 的公式 |
| AUDIT-3 | best_val_ic 追蹤引用 reward-based best_idx | L1499-1504 | P0 | val_IC 追蹤到錯誤的公式 |
| AUDIT-4 | Early stop has_exploration 引用 reward-based best → 永不觸發 | L1449 | P0 | 探索崩潰後仍跑完全程 6000 步 |
| AUDIT-5 | Re-seed 注入 3-token 公式（< min_formula_len=4） | L1470-1497 | P1 | Re-seed 注入即被 penalty 打回，探索無效 |
| AUDIT-6 | CPU 模式仍訓練 4 regime（非 1 個） | L1706-1718 | P1 | 浪費 4x 時間，僅靠 Kaggle timeout 截斷 |
| AUDIT-7 | RegimeConfig 覆蓋 group_size=32 → 實際 24 | L1719+L243 | P1 | group_size 錯配 |
| AUDIT-8 | val_IC penalty 只懲罰負值不獎勵正值 | L869-874 | P1 | val_ic=0 與 0.1 同分 |
| META | 版號字串仍為 v6.17 + title 殘留 v6.16 | JSON+L1 | P2 | 阻礙追蹤 |

## v6.19 修改清單（P0→P1→P2 優先級）

### P0 修復（必須在 v6.19 完成）

#### P0-1: Composite Score 全遍歷選擇

**問題**: `best_idx = np.argmax(rewards)` → composite 只對 reward 最高者計算

**修正**: 在 `train_step` 中（約 L1425-1441），遍歷 group 內**所有** formula：

```python
# === 取代 L1427-1441 的邏輯 ===
composites = []
for j in range(len(all_tokens)):
    if len(all_tokens[j]) < self.config.min_formula_len:
        composites.append(-999.0)  # 不合格，跳過
        continue
    j_tic = float(train_ic[j]) if train_ic is not None and j < len(train_ic) else 0.0
    j_vic = max(float(val_ic[j]), 0.0) if val_ic is not None and j < len(val_ic) else 0.0
    j_ops = sum(1 for t in all_tokens[j] if t >= N_FEATURES)
    c = (
        j_tic * self.config.composite_ic_weight +
        j_vic * self.config.composite_val_ic_weight +
        self.config.composite_operator_tiny_bonus * (j_ops > 0)
    )
    composites.append(c)

best_composite_idx = int(np.argmax(composites))
if composites[best_composite_idx] > best_composite:
    best_composite = composites[best_composite_idx]
    best_formula = all_tokens[best_composite_idx]
    best_reward = result["rewards"][best_composite_idx]  # 僅供報表
    best_step = step
    patience_counter = 0
```

#### P0-2: GRPOConfig 新增 composite score 參數

在 `GRPOConfig` dataclass（L680-735）加入：

```python
# --- v6.19: Composite Score 參數 ---
composite_ic_weight: float = 0.3           # train_IC 權重
composite_val_ic_weight: float = 0.7       # val_IC 權重
composite_operator_tiny_bonus: float = 0.05 # 含 operator 的小獎勵
composite_bypass_min_len: bool = False     # True = 跳過 min_formula_len 檢查（v6.20 grid search 用）
```

#### P0-3: Early Stop has_exploration 改用 composite-best

在 L1449，取代 `result["best_idx"]`：

```python
# === 取代 L1449 ===
best_toks_composite = all_tokens[best_composite_idx] if best_composite_idx < len(all_tokens) else []
best_n_ops_composite = sum(1 for t in best_toks_composite if t >= N_FEATURES)
has_exploration = best_n_ops_composite > 0 and len(best_toks_composite) > 2
```

#### P0-4: Closed-loop recovery 新增 best_composite 停滯觸發

在 L1476-1497 的 periodic re-seed 與 closed-loop 區塊，加入：

```python
# === 在 L1476-1497 加入 ===
# 【v6.19】best_composite 停滯觸發強制降溫重種
if (step > 0 and step > self.config.exploration_stagnation_first_step
    and step - best_step >= self.config.exploration_stagnation_steps
    and best_composite <= self.config.exploration_stagnation_composite_threshold):
    print(f"  [v6.19] best_composite 鎖定 {step - best_step} 步 (val={best_composite:.4f}) → 強制探索重啟")
    current_epsilon = self.config.exploration_stagnation_eps_target
    feat_logit_bias = self.config.feature_logit_bias_start
    reseed_n = int(G * self.config.exploration_stagnation_reseed_ratio)
    reseed_idx = np.random.choice(G, min(reseed_n, G), replace=False)
    for rg in reseed_idx:
        all_tokens[rg] = _make_reseed_formula(feature_weights, min_len=self.config.min_formula_len)
```

**新增 GRPOConfig 參數**:

```python
# --- v6.19: Exploration stagnation recovery ---
exploration_stagnation_steps: int = 1000
exploration_stagnation_first_step: int = 500
exploration_stagnation_composite_threshold: float = 0.01
exploration_stagnation_eps_target: float = 0.3
exploration_stagnation_reseed_ratio: float = 0.7
```

#### P0-5: Re-seed 質量 + 長度過濾

新增函式（放在 GRPOTrainer 中）：

```python
def _make_reseed_formula(self, feature_weights=None, min_len=4, max_attempts=5):
    """v6.19: Re-seed 公式生成 — 品質過濾 + 長度符合 min_formula_len"""
    for attempt in range(max_attempts):
        tf = (np.argsort(-np.array(feature_weights))[:N_FEATURES] if feature_weights is not None 
              else np.arange(N_FEATURES))
        # 確保長度 >= min_len: 2~3 features + 1~2 operators
        n_features_in = np.random.randint(2, min(4, N_FEATURES))
        n_ops_in = min_len - n_features_in
        if n_ops_in <= 0:
            n_ops_in = 1
            n_features_in = min_len - 1
        tokens = [int(tf[i % N_FEATURES]) for i in range(n_features_in)]
        valid_ops = [N_FEATURES + i for i in range(N_OPERATORS)]
        tokens += [int(np.random.choice(valid_ops)) for _ in range(n_ops_in)]
        
        # 品質過濾（可選）
        if self.training and hasattr(self, 'feat_tensor') and hasattr(self, 'returns'):
            signal = self.vm.execute(tokens, self.feat_tensor)
            if signal is not None and np.std(signal) > 1e-4:
                ic = self._compute_ic(signal, self.returns)
                if ic > -0.02:  # 拒絕太爛的 IC
                    return tokens
        else:
            return tokens
    # Fallback: 2 features + 2 operators
    return [0, 1, N_FEATURES, N_FEATURES + 1]
```

**替換所有 re-seed 位置**: L1470-1474, L1481-1485, L1493-1497 全部改成呼叫 `_make_reseed_formula`

### P1 修復

#### P1-1: CPU 模式強制單 regime

在 L1710-1718，取代 v6.12 的 4 regime 全訓邏輯：

```python
if _force_cpu or not _gpu_avail:
    print("  [v6.19] CPU 模式 → 只訓練 MID_CAP_TECH (單 regime)")
    # 只保留 mid_cap_tech regime 的股票
    mid_cap_stocks = {k: v for k, v in stock_data_map.items() 
                      if v.get("regime") == StockRegime.MID_CAP_TECH.value}
    stock_data_map = mid_cap_stocks
```

#### P1-2: CPU group_size=32 硬編碼

在 GRPOConfig auto_detect 之後（L1719 之前）：

```python
if _force_cpu or not _gpu_avail:
    trainer.config.group_size = 32  # 硬編碼覆蓋 RegimeConfig
```

或在 `train_torch_regime` 方法中（L1177-1181）修改：

```python
if regime_plan and "group_size" in regime_plan:
    if os.environ.get("GRPO_FORCE_CPU", "0") == "1":
        self.config.group_size = 32  # CPU 模式固定 32
    else:
        self.config.group_size = regime_plan["group_size"]
```

#### P1-3: Val_IC 獎懲雙向

在 `compute_group_rewards`（L869-874）修改：

```python
# 【v6.19】Val-IC 雙向獎懲 — 不只懲罰負值，還獎勵正值
if self.config.use_overfit_penalty and self.config.use_val_ic_reward:
    t_ic, v_ic = train_ic[i], val_ic[i]
    val_bonus = max(v_ic, 0.0) * 2.0      # 新增：正值獎勵
    val_penalty = abs(v_ic) * 10.0 if v_ic < 0 else 0.0  # 保留
    ic_gap = max(0, abs(t_ic) - abs(v_ic) - self.config.ic_gap_threshold)
    ic_gap_penalty = self.config.ic_gap_weight * ic_gap
    combined += val_bonus
    combined -= (val_penalty + ic_gap_penalty)
```

### P2 修復

#### P2-1: 版號字串 + Notebook 清理

- notebook metadata title: `"TWStock GRPO v6 19 Composite Score Full Fix"`
- output JSON version: `"v6.19"`
- kernel-metadata.json:
  - `id`: `mhhuang14/twstock-grpo-v6-19`
  - `title`: `"TWStock GRPO v6 19 Composite Score Full Fix"`
- 過時的 docstring: 更新 `"""` 中的 `v6.16`/`v6.17` 引用為 `v6.19`

#### P2-2: JSONL 結構化 Logging

在 step 200 的 debug print 區塊（L1500-1527）加入：

```python
if step % 200 == 0:
    log_entry = {
        "step": step,
        "best_composite": round(float(best_composite), 6),
        "best_composite_idx": int(best_composite_idx),
        "best_reward": round(float(best_reward), 6),
        "val_ic_best": round(float(best_val_ic), 6),
        "with_ops": int(n_with_ops),
        "avg_ops": round(float(avg_ops), 4),
        "avg_len": round(float(avg_len), 2),
        "temperature": round(float(temperature), 4),
        "eps": round(float(current_epsilon), 4),
        "fbias": round(float(feat_logit_bias), 4),
        "best_formula_len": len(best_formula) if best_formula else 0,
        "best_ops": int(best_n_ops_composite),
    }
    print(f"[LOG] {json.dumps(log_entry)}")
```

## 驗收標準

| 指標 | 門檻 | v6.18 實際 | 驗證方式 |
|------|------|-----------|----------|
| `val_ic_best` | > 0.02 | 0.1093 ✅ | Output JSON |
| `best_ops` | ≥ 2 | 0 ❌ | Output JSON `formula_str` |
| `best_len` | ≥ 4 | 1 ❌ | Output JSON `formula_tokens` 長度 |
| `best_composite` 更新次數 | step 1000+ ≥ 3 | 未知 | LOG JSONL 中 best_composite 遞增 |
| `with_ops` at step 2000 | > 5/32 | 未知 | LOG JSONL |
| CPU group_size | 32 | 24 ❌ | Config output |
| 訓練 regime 數 | 1 (mid_cap_tech) | 1 ✅ | Output JSON 只含 1 regime |
| 版號字串 | "v6.19" | "v6.17" ❌ | Output JSON metadata.version |

## 檔案變更對照

| 區塊 | v6.18 行號 | 變更類型 | 描述 |
|------|-----------|---------|------|
| GRPOConfig | ~L680-735 | 新增 12 個參數 | composite score + stagnation recovery 參數 |
| generate_and_evaluate | L951 | 不改 | 保留 reward-based best_idx (用於報表) |
| train_step composite 選擇 | L1427-1441 | **重寫** | 替換為全遍歷 composite-argmax |
| train_step early stop | L1449 | **修改** | has_exploration 改引用 composite-best |
| train_step best_val_ic | L1499-1504 | **修改** | 同改為 composite-based |
| re-seed 區塊 (3 處) | L1470-1497 | **重寫** | 全部改用 _make_reseed_formula |
| closed-loop recovery | L1476-1497 | **新增** | best_composite 停滯觸發 |
| val_IC penalty | L869-874 | **修改** | 加入 val_bonus 正值獎勵 |
| CPU regime selection | L1710-1718 | **重寫** | 只留 MID_CAP_TECH |
| CPU group_size | L1719 前 | **新增** | 加入硬編碼覆蓋 |
| compute_group_rewards | L869-874 | **修改** | 雙向獎懲 |
| Debug print | L1500-1527 | **新增** | JSONL structured logging |
| version/title | L1+L1753+L1764 | **修改** | 全面更新為 v6.19 |

## 潛在風險

1. **Composite 計算開銷**: 遍歷 group (size=24-32) 每個 formula 計算 IC → 每次 step 多 24-32 次 IC 計算。v6.18 已計算 train_ic/val_ic 陣列，只需索引取值，開銷極小 (<0.1ms/step)。

2. **Re-seed 品質過濾依賴 vm.execute**: CPU 模式已執行 backtest，無額外開銷。

3. **val_bonus=2.0 可能造成 reward 膨脹**: 若 val_ic>0.5 則 val_bonus=1.0，在 total reward 佔比約 5-10%，處於合理範圍。

4. **單 regime 過擬合**: mid_cap_tech 僅 1 個 regime，val_IC 可能高估。v6.20 恢復 multi-regime 訓練時需重新驗證。