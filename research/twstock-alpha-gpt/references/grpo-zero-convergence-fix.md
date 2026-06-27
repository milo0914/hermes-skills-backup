# GRPO 零收斂 Bug 診斷與修復 (2026-06-08)

## 四個獨立根因

GRPO 訓練零收斂有四個獨立根因，症狀不同但都導致 loss=0：

| 根因 | 症狀 | 機制 |
|------|------|------|
| A. StackVM 隨機生成 | valid=0% | 公式非法 → reward=-5.0 |
| B. 特徵大小寫不匹配 | valid=0% 或 valid=100% 但 reward 全同 | 特徵全零 → signal=常數 |
| C. 合成數據無可學習信號 | valid=100% 但 loss=0 | returns 隨機 → IC 全相同 |
| D. PPO ratio 梯度消亡 | loss 恆為 -0.0000，不報錯 | `1.0+0.0*x` 偏導為零 → 梯度斷鏈 |

---

## 根因 A：StackVM 隨機生成有效率極低

### 問題

StackVM 隨機 token 採樣有效率僅 0.2%（1000 次模擬僅 2 次產生合法公式）。

### 為什麼隨機採樣幾乎必定失敗

StackVM 是後進先出棧機器：
- 操作數 (features, token 0-21) push 到棧
- 運算子 (operators, token 22-33) 從棧 pop 參數並 push 結果
- 合法公式要求：每個位置只能放「棧狀態允許」的 token

均勻採樣時，任意選到運算子的機率 = 12/34 ≈ 35%。若棧空時選到運算子 → INVALID。若棧滿時選到操作數 → 可能溢出。連續多步後合法序列機率指數衰減。

### 連鎖效應

```
隨機採樣 → 99.8% INVALID → reward 全部 = -5.0
→ group advantages = (R - mean) / std = (0 - 0) / 0 = 0
→ loss = -sum(advantages * log_probs) = 0
→ 梯度全零 → 永遠不學習
```

### 診斷腳本

```python
# /tmp/diagnose_grpo.py — 模擬 StackVM 隨機生成
import numpy as np
N_FEATURES, N_OPS, MAX_LEN = 22, 12, 8
VOCAB = N_FEATURES + N_OPS # 34

def random_formula():
 tokens = []
 stack = 0
 for _ in range(MAX_LEN):
  t = np.random.randint(VOCAB)
  if t < N_FEATURES: # feature → push
   stack += 1
   tokens.append(t)
  else: # operator → pop
   if stack >= 1:
    stack -= 1 # simplified: all ops pop 1, push 1
    tokens.append(t)
   else:
    return tokens, False # INVALID
 return tokens, stack == 1

valid = sum(random_formula()[1] for _ in range(1000))
print(f"Valid rate: {valid/1000*100:.1f}%") # Expected: ~0.2%
```

### 修復方案：引導式解碼 (Guided Decoding)

#### StackVMState 類別

追蹤棧深度，推導每個位置可用的合法 token 集合：

```python
class StackVMState:
 def __init__(self, n_features, n_operators, max_stack_depth=3):
  self.n_features = n_features
  self.n_operators = n_operators
  self.max_stack_depth = max_stack_depth
  self.stack_depth = 0
  self.tokens_generated = 0
  self.max_tokens = 8 # MAX_FORMULA_LEN

 def get_valid_mask(self):
  """Return boolean mask of valid token indices."""
  mask = np.zeros(self.n_features + self.n_operators, dtype=bool)
  if self.stack_depth < self.max_stack_depth:
   mask[:self.n_features] = True # features always valid if stack not full
  if self.stack_depth >= 1:
   mask[self.n_features:] = True # operators valid if stack has operands
  return mask

 def advance(self, token):
  """Update stack depth after generating token."""
  if token < self.n_features:
   self.stack_depth += 1
  else:
   self.stack_depth -= 1 # simplified: pop 1
  # For GATE (arity=3): stack_depth -= 2 extra
  self.tokens_generated += 1

 def is_complete(self):
  """Formula is complete when stack_depth == 1."""
  return self.stack_depth == 1 and self.tokens_generated > 0
```

#### 在 GRPO 訓練中應用

```python
# In generation loop (train_torch_regime):
if config.guided_decoding:
 state = StackVMState(N_FEATURES, N_OPS)
 for pos in range(MAX_FORMULA_LEN):
  logits = model(inp) # [1, pos+1, vocab_size]
  pos_logits = logits[0, -1, :] # [vocab_size]

  # Mask invalid tokens
  valid_mask = torch.tensor(state.get_valid_mask(),
   dtype=torch.bool, device=pos_logits.device)
  pos_logits[~valid_mask] = -1e9 # suppress invalid

  dist = torch.distributions.Categorical(logits=pos_logits)
  action = dist.sample()
  log_prob = dist.log_prob(action)

  state.advance(action.item())
  all_tokens.append(action.item())
  all_log_probs.append(log_prob)

  inp = torch.cat([inp, action.view(1, 1)], dim=1) # NOT .unsqueeze(0)

  if state.is_complete():
   break
```

#### Warmup 恆等公式初始化

前 500 步的前半 group 用單特徵公式，確保有正 reward 啟動梯度：

```python
if step < config.warmup_steps and g < config.group_size // 2:
 # Use identity formula: [feat_i]
 feat_idx = np.random.randint(N_FEATURES)
 tokens = [feat_idx] # Single feature, stack_depth=1 → complete
 log_prob = torch.tensor(0.0, device=device, requires_grad=True)
```

#### Advantage 全無效 Fallback

```python
# In compute_group_rewards:
if np.all(rewards == INVALID_REWARD):
 # Return -1 for all (not 0!) → pushes model away from invalid formulas
 return -np.ones(G), rewards
```

### 驗證結果 (根因 A)

| 方法 | 有效率 | 平均 reward |
|------|--------|------------|
| 隨機採樣 | 0.2% | -4.99 |
| 引導式解碼 | 100% | > 0 |
| 引導 + warmup 恆等 | 100% | > 0 (穩定) |
| 引導 + warmup + fallback | 100% | > 0 (最穩定) |

---

## 根因 B：特徵欄位大小寫不匹配 (v3.2 修復)

### 問題

即使根因 A 已修復（引導式解碼 + warmup），訓練仍然零收斂。loss=-0.0000, mean_r=0.000, valid=0.0% 持續 7500+ 步。

### 根因定位過程

1. 下載 Kaggle kernel log → 發現所有 reward = -5.0（IC=NaN 懲罰值）
2. 本地 debug 腳本模擬 `compute_features` → 發現所有特徵的 zscore 值 = 0
3. 追蹤 zscore 邏輯 → 發現遍歷 `FEATURE_NAMES`（大寫）但 DataFrame 只有 `compute_features` 生成的小寫欄位

### 根因細節

`TWFeatureEngineer.compute_features()` 生成的小寫欄位名：

```
ret, liq_score, pressure, fomo, dev, log_vol,
inst_flow, margin_press, five_day_high, vol_breakout,
cvd_proxy, absorption, surf_entry, atr, close_pos, mom_rev,
tx_inst_net_oi, mtx_retail_oi, tx_mtx_spread,
nasdaq_close, sp500_close, dowjones_close
```

`FEATURE_NAMES` 常數使用大寫：

```
RET, LIQ_SCORE, PRESSURE, FOMO, DEV, LOG_VOL,
INST_FLOW, MARGIN_PRESS, FIVE_DAY_HIGH, VOL_BREAKOUT,
CVD_PROXY, ABSORPTION, SURF_ENTRY, ATR, CLOSE_POS, MOM_REV,
TX_INST_NET_OI, MTX_RETAIL_OI, TX_MTX_SPREAD,
NASDAQ_CLOSE, SP500_CLOSE, DOWJONES_CLOSE
```

zscore 正規化區段遍歷大寫名稱：
```python
for feat in FEATURE_NAMES:
    if feat not in g.columns:
        g[feat] = 0  # ← 找不到大寫欄位，全部設為 0！
```

feat_tensor 提取時使用小寫 fallback：
```python
for feat in FEATURE_NAMES:
    if feat in group.columns:         # 大寫不存在
        feat_cols.append(group[feat].values)
    elif feat.lower() in group.columns:  # fallback 到小寫原始值（未 zscore）
        feat_cols.append(group[feat.lower()].values)
```

### 連鎖效應

```
小寫欄位 → zscore 找不到大寫 → g[feat] = 0（22個特徵全部為零）
→ feat_tensor 全零或未正規化
→ VM signal = 常數 / 無意義值
→ spearman_corr = NaN
→ reward = -5.0（全部）
→ 引導式解碼仍生成合法公式，但信號無效
→ advantages = -1 但 log_prob = 0 → loss ≈ 0
```

### 診斷方法

```python
# 關鍵診斷：對比大寫 zscore 值 vs 小寫原始值
for feat in FEATURE_NAMES:
    upper_val = feat_dict.get(feat, 'MISSING')
    lower_val = feat_dict.get(feat.lower(), 'MISSING')
    if upper_val != lower_val:
        print(f"MISMATCH: {feat}(upper)={upper_val}, {feat.lower()}(lower)={lower_val}")
```

預期輸出（修復前）：
```
MISMATCH: RET(upper)=0.0000, ret(lower)=-0.6298
MISMATCH: LIQ_SCORE(upper)=0.0000, liq_score(lower)=1.2345
... (所有 22 個特徵都有 MISMATCH)
```

### 修復方案

#### 修復 1：小寫→大寫欄位映射（在 zscore 之前）

```python
# 在 for stock_id in group_cols 迴圈內，zscore 之前：
_lower_to_upper = {f.lower(): f for f in FEATURE_NAMES}
# 只 rename 存在的欄位
rename_map = {k: v for k, v in _lower_to_upper.items() if k in g.columns}
if rename_map:
    g.rename(columns=rename_map, inplace=True)
```

#### 修復 2：feat_tensor 提取優先使用大寫（zscore 後）欄位

```python
# feat_tensor 提取：
for feat in FEATURE_NAMES:
    if feat in group.columns:           # 優先：大寫（zscore 正規化後）
        feat_cols.append(group[feat].values)
    elif feat.lower() in group.columns: # fallback：小寫原始值
        feat_cols.append(group[feat.lower()].values)
    else:
        feat_cols.append(np.zeros(len(group)))
```

#### 修復 3：合成數據 inst_df/margin_df 不能為空

原始 `generate_synthetic_data()` 的 `inst_df = pd.DataFrame()` 和 `margin_df = pd.DataFrame()` 為空，導致 `INST_FLOW` 和 `MARGIN_PRESS` 恆為零。需加入合成三大法人買賷超和融資融券數據生成。

### 關鍵縮排陷阱

修復時 `_lower_to_upper` 映射和 zscore 塊必須在 `for stock_id in group_cols` 迴圈**內部**（per-group 執行），不是迴圈外。0sp 空行會打斷 Python 縮排塊，雖然 `ast.parse` 不報錯，但語意上程式碼會跳出迴圈。用 `write_file` Python 修復腳本按行號精確修正縮排。

### 驗證結果 (根因 B 修復後)

```
修復前：22/22 特徵 zscore 值 = 0.0000，VM reward = -5.0，valid = False
修復後：20/22 特徵有正常 zscore 值，VM reward = 0.1477，valid = True
        feat_tensor: mean=-0.0063, std=0.9366（接近標準常態分佈）
        （INST_FLOW/MARGIN_PRESS 在加入合成 inst/margin 數據後應恢復正常）
```

---

## 根因 C：合成數據無可學習信號 (v3.2 發現)

### 問題

即使根因 A（引導式解碼）和根因 B（大小寫映射）都已修復，v14 kernel 在 Kaggle P100 上仍零收斂：`loss=-0.0000 valid=100.0% overfit=False` 持續 15500+ 步。

### 診斷證據

- `valid=100.0%` → 所有 G 個公式的 reward > -5.0（公式合法且信號非零）
- `loss=-0.0000` → advantages ≈ 0
- `mean_r≈0` → 所有公式的 reward 幾乎相同
- 合成數據特徵統計：`INST_FLOW: mean=0.0000, std=0.0000`；`MARGIN_PRESS: mean=0.0000, std=0.0000`；`ATR: nan=1513/2000`

### 根因推導

```
合成數據 returns = (close[t+h] - close[t]) / close[t]
close = random walk（純隨機）
→ 任何因子信號與隨機 returns 的 spearman IC ≈ 同一小值
→ 所有 G 個公式的 IC 幾乎相同
→ group_std ≈ 0
→ advantages = (reward_i - group_mean) / group_std ≈ 0
→ loss = -min(ratio * A, clip(ratio) * A).mean() ≈ 0
→ 梯度全零 → 永遠不學習
```

與根因 A/B 的差異：
- 根因 A：公式非法 → reward=-5.0 → valid=0%
- 根因 B：特徵全零 → signal=常數 → reward=-5.0 → valid=0%
- **根因 C：公式合法、特徵非零，但 returns 隨機 → IC 全相同 → valid=100% 但 loss=0**

### 修復方案

#### 方案 1：注入可學習的因子-報酬結構（推薦）

在合成數據中讓 fwd_returns 包含已知因子的線性組合：

```python
# 在 generate_synthetic_data() 中：
# 選定 2-3 個「真實 alpha」特徵
true_alpha_features = ['RET', 'PRESSURE', 'CVD_PROXY']
alpha_weights = np.array([0.3, 0.2, 0.15])

# fwd_returns = alpha 信號 + noise
alpha_signal = sum(w * feat_tensor[i] for i, w in zip(feature_indices, alpha_weights))
fwd_returns = alpha_signal + np.random.normal(0, noise_std, n_samples)
```

這樣 GRPO 能學到真正有預測力的公式，loss 會下降。

#### 方案 2：加入結構性 reward

除了 IC reward，加入因子單調性、信號分布均勻性等結構性獎勵。

#### 方案 3：使用真實數據（最終目標）

用 TWSEDataFetcher 抓取真實台股數據，returns 有可預測結構。

### 驗證方法

修復後應觀察到：
1. `loss` 從 -0.0000 開始下降（負值增大，代表梯度有效）
2. `mean_r` 出現正負分化（某些公式明顯優於其他）
3. `best_r > 0`（至少有一個公式的 IC > 0）
4. `group_std > 0.01`（reward 有區分度）

---

## 三個根因的交互關係

三個根因都會導致 loss=0，但症狀不同：
- 根因 A：公式非法 → valid=0% → reward=-5.0 → advantages 全同
- 根因 B：公式合法但特徵為零 → valid=0% 或 valid=100% 但 reward 全同
- 根因 C：公式合法、特徵非零、但 returns 隨機 → valid=100% 但 reward 全同

診斷順序建議：
1. 先確認有效率 > 0%（若 valid=0% → 根因 A）
2. 再確認 feat_tensor 非全零（若 std≈0 → 根因 B）
3. 最後確認 returns 與特徵有相關性（若所有 reward 相同 → 根因 C）
4. 三者都修復後，loss 應下降且 best_r > 0

## 根因 C 確認過程 (2026-06-08 Kaggle P100 實測)

v14 kernel（含根因 A+B 修復）在 Kaggle P100 上跑 15500+ 步仍零收斂。一開始誤以為是舊版代碼（截圖 log 格式 `valid=100.0%` 看似 `mean_valid=100.0%`），但比對 v14 print 格式 `f"valid={result['valid_mask'].mean():.1%}"` 確認完全一致 — **Kaggle 上跑的確實是 v14**。

關鍵診斷：`valid=100.0%` 意味著根因 A+B 已修復（公式合法、特徵非零），但 loss=0 意味著 advantages≈0，即所有公式的 reward 幾乎相同。這只能用「合成數據 returns 是純隨機」來解釋。

---

## 相關修復

- `action.unsqueeze(0)` → `action.view(1, 1)` — torch.cat 維度修正
- 重複 StackVMState class 定義移除 — 多次 patch 產生的重複 class
- `kaggle kernels push` 409 Conflict — 需等舊 kernel 完成再推送
- 0sp 空行打斷縮排塊 — patch 工具副作用，需手動修正縮排

## 檔案位置

- 訓練腳本：`scripts/grpo_regime_training_kaggle.py`（v3.2 修復後，語法 OK）
- 診斷腳本：`/tmp/diagnose_grpo.py`（根因 A）、`/tmp/debug_grpo.py`（根因 B）
- 修復設計驗證：`/tmp/grpo_fix_design.py`
