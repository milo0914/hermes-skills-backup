# v6.15 Plan E 深度策略審查 (Strategy Review)

---

## 第一部分：Plan E 程式碼實現的正確性審查

### 1. Warmup Operator Seed (v6.15A) — L1192-L1220

**實作正確性: 通過**

程式碼確實：
- 在 warmup 期間（step < warmup_steps=500）對 `n_operator_seeds = G * operator_seed_ratio` 個 sample 使用預填公式模板
- 3 種模板（二元 ADD/SUB/MUL、一元 NEG/ABS/SIGN、二元 MUL 變體）循環使用
- 使用 top-k feature（依 FeatureWeight 排序）
- 用 autoregressive log_prob 計算（L1219 L1225-1232）

**但存在 2 個設計缺陷:**
(1) Warmup 僅 500 steps，但 operator_seed_ratio=0.5 只在 is_warmup=True 時生效
(2) step >= 500 後 n_operator_seeds=0，**無持續性**

### 2. Epsilon-Greedy Operator Injection (v6.15C) — L1301-L1316

**實作正確性: 通過**

程式碼確實：
- position 0 且 stack_depth=0 時檢查 epsilon
- 從 valid operator tokens 中隨機選擇
- 強制 action 後仍用 `dist.log_prob(action)` 保留梯度
- 使用 `continue` 跳到下一個 t_pos（正確）

**但設計存在致命缺陷:**
(1) **epsilon 衰減太快**: decay=0.9 每 500 steps → step 500 時 eps=0.3*0.9=0.27，step 1000 時 eps=0.3*0.81=0.243，step 2000 時 eps=0.3*0.66=0.197，step 5000 時 eps=0.3*0.35=0.105
(2) **無下限保護**: L1302 `current_epsilon > 0.01` 雖然有 threshold，但公式在 step 5000 後仍有約 10% 概率，但 log 顯示 step 600 後 with_ops=0 — 這說明 epsilon 衰減不是唯一問題
(3) **關鍵問題**: epsilon decay 的周期步長是 500 steps，但 step 600 的 eps=0.27 理論上仍有 27% 概率強制選 operator，**但 log 顯示 with_ops=0/32** — 這說明 valid_ops 可能為空！

### 3. Feature Logit Bias Decay (v6.15D) — L1275-L1279

**實作正確性: 通過**

程式碼確實：
- position 0 時對 `feature_bias[:N_FEATURES]` 加上負 bias
- bias 值線性歸零（2000 steps）
- 只作用在 position 0

**但有一個微妙的隱患:**
- Feature logit bias 是加到 logits（softmax 前），不是直接 mask
- 但它的效果等同於對 feature 做 -2.0 的偏移（softmax 後概率大幅下降）
- 問題是：operator 也有 12 個，feature 有 22 個，即使 bias 為 -2，22 個 feature 的總概率仍然顯著高於 12 個 operator

### 4. Complexity Reward — L856-L869

**實作正確性: 通過**

計算公式：
```
complexity_comp = reward_weights["complexity"] * (n_operators * operator_bonus)
```

數值驗證（v6.15 設定）:
- weight=0.25, operator_bonus=1.0
- 1-operator (3-token) → complexity_comp = 0.25 * (1 * 1.0) = 0.25
- 對比 log step 0: cplx=0.250 ✓

**但這個獎勵力度其實很小！**
- Base reward（IC+Sharpe+MDD+Turnover）約 -0.15 ~ -0.30（看 log 的 mean_r）
- Complexity +0.25 只能稍微緩解，不足以讓 policy 大規模轉向 operator
- 且 complexity 分項只有 +0.25，對比 short_penalty 對 1-token 的 -0.30：
  - 如果 1-token：penalty=0.05*3.0*(3-1)=0.30 → 被扣 0.30
  - 如果 3-token with operator：獲 +0.25 → 淨效應：1-token (-0.30) vs 3-token (+0.25) = **差距 0.55**
  - 理論上足夠，實務上政策從未穩定到達 3-token 區域

---

## 第二部分：Log 數據深度解讀

### 關鍵時間序列分析

```
traditional regime (G=32):
  step    0: eps=0.300 fbias=-2.00 with_ops=16/32 avg_ops=0.50 avg_len=1.8  best_ops=1 best_len=3
  step  200: eps=0.300 fbias=-1.80 with_ops=16/32 avg_ops=0.50 avg_len=1.8  best_ops=1 best_len=3
  step  400: eps=0.300 fbias=-1.60 with_ops=16/32 avg_ops=0.50 avg_len=1.8  best_ops=1 best_len=3
  step  600: eps=0.270 fbias=-1.40 with_ops=0/32  avg_ops=0.00 avg_len=1.0  best_ops=0 best_len=1  ← 崩潰
  step  800+: eps<0.27 fbias→0     with_ops=0/32  avg_ops=0.00 avg_len=1.0  best_ops=0 best_len=1  ← 無法恢復
```

**重點: step 600 時 eps=0.27 仍有效，但 with_ops=0/32**

這說明 epsilon 本身並不是失效點。問題在於：
1. **Epsilon 只在 position 0 生效**（L1302: `t_pos == 0`）
2. 即使 position 0 選了 operator，後續 token 仍由 policy 自由選擇
3. 如果 policy 在後續 position 壓倒性地選 feature，最終公式只有 1 token（無後續 token）
4. **position 0 選 operator 但公式後續無 feature → VM 可能直接拋棄**

### 關鍵問題: guided decoding 可能阻擋了 operator

L1255-1256:
```python
valid_tokens = (vm_state.get_valid_tokens(t_pos, remaining)
                if self.config.guided_decoding else None)
```

L1305-1307:
```python
if valid_tokens is not None:
    valid_ops = [t for t in valid_tokens if t >= N_FEATURES]
    if valid_ops:
```

**核心猜測: guided decoding 在 position 0 時，valid_ops 可能為空！**
- position 0 且 stack_depth=0 → VM 需要的是 feature token（因為 RPN 需要 operand 先）
- 如果 guided decoding 在 position 0 只允許 feature tokens → valid_ops = []
- 那麼 L1307 `if valid_ops:` 失敗 → **epsilon-greedy 跳到正常採樣路徑**
- 這就解釋了為什麼 eps=0.27 時 with_ops=0！

### Complexity Reward 與 exploration 的數學關係

```
3-token formula with operator:
  ic_comp: 0.35 * 0.059 = 0.021
  cplx:    0.25 * 1.0 = 0.250
  simp:    0.0 (f_len=3 >= min=3)
  len_b:   0.08 * max(0, 3-1) * 0.5 = 0.080
  total:   ~0.351

1-token feature-only:
  ic_comp: 0.35 * 0.168 = 0.059
  cplx:    0.0
  simp:    0.05 * 3.0 * (3-1) = 0.300 → -0.300
  len_b:   0.0
  total:   ~(-0.241)
```

差距 ~0.592，理論上足夠。**但這是事後（backtest 後）才知道的 reward 差距**。
- Policy 在生成時看不到這個差距
- Policy 通過「選 feature token → 獲得 1-token formula → 收到低 reward → gradient update → 下次更傾向選 operator」來學習
- 這個過程需要多次 iteration（on-policy 每步更新）
- **問題在於: step 600 時 policy 停止探索，gradient 也無法挽救**

---

## 第三部分：根本原因重新評估

### 根因 1 (P0): Guided Decoding 與 Epsilon-Greedy 衝突

**可能性極高**。如果 guided decoding 在 position 0 只允許 feature tokens，那麼：
- v6.15C 的 epsilon-greedy **永遠不會在 position 0 選到 operator**（因為 valid_ops 為空）
- v6.15D 的 feature logit bias **雖然壓低了 feature logits，但 guided mask 直接將 operator 設為 -inf**
- 兩者同時失效！

**這才是真正的 root cause！**

### 根因 2 (P1): 探索機制無閉迴路監控

即使根因 1 不存在，當探索意外停止時，系統無法恢復。
- Epsilon 只會單調遞減
- Feature logit bias 只會單調歸零
- Warmup seed 一次性

### 根因 3 (P2): Complexity Reward 不足以單獨驅動探索

- 0.25 的 weight 在探索初期提供 +0.25 的獎勵
- 但 base reward 約 -0.15 ~ -0.30
- 如果 generation 根本採樣不到 operator → reward 信號永遠無法傳遞到 policy 的 operator tokens

### 根因 4 (P3): CPU 訓練效率太低

- P100 無法使用 → CPU fallback
- 5000 steps 在 CPU 上相當於 ~140 分鐘
- 有效探索窗口 < 600 steps（佔 ~17 分鐘）

---

## 第四部分：v6.16 策略修正方案

### 修正 1 (P0): 允許 Guided Decoding 在 position 0 包含 operator

**核心問題**: position 0 的 guided decoding 是否只允許 feature?

解決方案:
```python
# 在 epsilon-greedy 注入前，臨時修改 guided mask 允許 operator
if t_pos == 0 and current_epsilon > np.random.random():
    # Create a special mask that allows both features AND operators
    exploration_mask = torch.zeros(VOCAB_SIZE, device=self.config.device)
    exploration_mask[:N_FEATURES] = 0.0  # features
    exploration_mask[N_FEATURES:] = 0.0  # operators too
    logits_last = logits_last + exploration_mask  # override guided mask
```

或者更簡單: 在 epsilon-greedy 觸發時，跳過 guided mask 的直接取樣

### 修正 2 (P0): 驗證 Guided Decoding 行為

在 notebook 開頭加入:
```python
# Debug: 驗證 VM state 在 position 0 的行為
vm = VRPNStackVM()
valid_at_pos0 = vm.get_valid_tokens(pos=0, remaining=5)
print(f"position 0 valid tokens: {valid_at_pos0}")
n_feat = sum(1 for t in valid_at_pos0 if t < N_FEATURES)
n_ops = sum(1 for t in valid_at_pos0 if t >= N_FEATURES)
print(f"  features: {n_feat}, operators: {n_ops}")
```

### 修正 3 (P1): 閉迴路自適應探索監控

```python
# 每 200 step 檢查探索狀態
if step % 200 == 0 and step > 0:
    avg_ops_in_group = np.mean([sum(1 for tok in t if tok >= N_FEATURES) for t in all_tokens])
    if avg_ops_in_group < 0.5:
        # 探索崩潰 → 強制恢復
        current_epsilon = max(current_epsilon * 1.5, 0.5)
        feat_logit_bias = min(feat_logit_bias - 0.5, -2.0)
        # 強制重新注入 operator seed（不分 warmup）
        n_reseed = int(G * 0.3)
        for g in range(min(n_reseed, G)):
            all_tokens[g] = seed_operator_formula(...)
```

### 修正 4 (P1): 週期性 Operator Re-seed

```python
# 每 500 steps 重新注入 operator seed（不限 warmup）
if step > 0 and step % 500 == 0:
    n_reseed = int(G * 0.3)  # 30% 重填
    for g in range(n_reseed):
        seed_tokens = generate_seed_formula(...)
        all_tokens[g] = seed_tokens
```

### 修正 5 (P2): 加強 Complexity Reward

- complexity weight: 0.25 → 0.45
- operator_bonus: 1.0 → 2.0
- short_formula_penalty: 3.0 → 5.0
- min_formula_len: 3 → 4

### 修正 6: GPU 相容性

```python
# 安裝 cu118 PyTorch 以支援 sm_60 (P100)
!pip install torch==2.1.0+cu118 -f https://download.pytorch.org/whl/torch_stable.html --quiet
import torch
print(f"CUDA available: {torch.cuda.is_available()}")
print(f"Device: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU'}")
```

---

## 第五部分：策略層面的反思教訓

### 教訓 1: Hypthosis Validation 不足

Plan E 設計時假設「reward landscape 已正確（3-token=+0.374 vs 1-token=-0.256）」，但未驗證 **guided decoding 是否允許 operator 在 position 0 被選中**。這是一個典型的「錯誤假設導致整體設計無效」案例。

### 教訓 2: 探索機制應設計為閉迴路，而非開環時間衰減

Plan E 的所有三個機制都是時間驅動的（decay schedule），而非狀態驅動的（monitor + react）。在複雜非平穩環境中，時間驅動的探索策略極易崩潰。

### 教訓 3: Gumbel Noise / Temperature 探索不足

v6.15 的 Plan E 企圖用外部機制強制探索，但根本原因可能是 **Gumbel noise 太弱或 temperature 衰減太快**。更好的做法是同時增強內生探索（Gumbel scale+、temperature higher）和外生探索（eps-greedy、re-seed）。

### 教訓 4: 實驗設計應有驗證步驟

每次迭代應在 notebook 中加入最小驗證測試：
- guided decoding 行為驗證（position 0 是否允許 operator）
- epsilon-greedy 實際命中率驗證
- warmup seed 的 log_prob 是否正確

---

## 總結

| 層級 | 問題 | 嚴重度 | v6.16 修正 |
|------|------|--------|-----------|
| **實現** | Guided decoding 可能阻擋了 position 0 的 operator | P0 | 驗證 + 臨時 override |
| **設計** | 探索機制為開環時間衰減 | P1 | 閉迴路自適應監控 |
| **設計** | 無週期性 re-seed | P1 | 每 500 step 注入 |
| **參數** | Complexity reward 力度不足 | P2 | weight 0.25→0.45, bonus 1.0→2.0 |
| **基礎** | GPU 失效導致 CPU 慢速 | P3 | cu118 PyTorch 安裝 |