# v6.17 完整失效分析 + v6.18 Eng Plan Review

## 一、v6.17 Fixed 訓練結果摘要

**環境**: Tesla P100-PCIE-16GB, sm_60  
**PyTorch**: 預裝 2.10.0+cu128 (不支援 sm_60)  
**cu118 安裝**: `torch==2.0.1+cu118` 安裝失敗 (exit status 1) → **CPU fallback**  
**訓練模式**: CPU, group_size=64, train_steps=12000  
**手動停止**: step 2200 (traditional regime)

### Step-by-Step Metrics (Traditional Regime)

| Step | loss | mean_r | best_r | temp | with_ops | avg_ops | avg_len | eps | fbias | best_ops | val_ic_best |
|------|------|--------|--------|------|----------|---------|---------|-----|-------|----------|-------------|
| 0 | -0.818 | -0.618 | **0.505** | 2.00 | 22/32 | 0.69 | 2.2 | 0.300 | -2.00 | 1 | -inf |
| 200 | -0.547 | -0.679 | 0.505 | 1.97 | 20/32 | 0.62 | 2.0 | 0.300 | -1.80 | 1 | -inf |
| 400 | -0.535 | -0.758 | 0.505 | 1.95 | 18/32 | 0.56 | 1.9 | 0.300 | -1.60 | 1 | -inf |
| 600 | -0.296 | -1.157 | 0.505 | 1.93 | 8/32 | 0.25 | 1.3 | 0.486 | -2.00 | 0 | -inf |
| 800 | -0.204 | -1.148 | 0.505 | 1.90 | 8/32 | 0.25 | 1.3 | 0.486 | -2.00 | 1 | -inf |
| 1000 | -0.154 | -1.148 | 0.505 | 1.88 | 11/32 | 0.34 | 1.5 | 0.243 | -1.00 | 0 | -inf |
| 1200 | -0.315 | -1.148 | 0.505 | 1.85 | 6/32 | 0.19 | 1.4 | 0.437 | -2.00 | 1 | -inf |
| 1400 | -0.344 | -1.149 | 0.505 | 1.82 | 3/32 | 0.09 | 1.2 | 0.437 | -2.00 | 0 | -inf |
| 1600 | -0.251 | -1.148 | 0.505 | 1.80 | 8/32 | 0.25 | 1.4 | 0.394 | -2.00 | 1 | -inf |
| 1800 | -0.148 | -1.148 | 0.505 | 1.78 | 9/32 | 0.28 | 1.3 | 0.394 | -2.00 | 1 | -inf |
| 2000 | -0.322 | -1.148 | 0.505 | 1.75 | 3/32 | 0.09 | 1.1 | 0.354 | -2.00 | 0 | -inf |
| 2200 | -0.406 | -1.149 | 0.505 | 1.73 | 2/32 | 0.06 | 1.1 | 0.354 | -2.00 | 0 | -inf |

---

## 二、六大失效根因分析

### BUG-1: operator_bonus 造成 best_reward 虛高天花板 [P0 CRITICAL]

**現象**: `best_r=0.505` 從 step 0 到 2200 從未更新

**根因**: `compute_group_rewards` 中 `operator_bonus=2.0` 直接加到 total reward。step 0 隨機生成的公式若恰好包含 1 個 operator，其 reward = base_reward(-0.2) + complexity(0.2) + operator_bonus(2.0) ≈ **2.0**。而後續更長公式即使 IC 更好，base_reward 可能更高，但可能缺少 operator → reward 反而更低。或有 operator 但 val_penalty 扣分 → reward 仍低於虛高的 0.505。

**影響**: 
- `best_formula` 永遠鎖定在 step 0 的隨機公式
- GRPO policy 學習「生成跟 step 0 一樣的公式」
- 探索被壓抑 → with_ops 逐步下降 → 崩潰

**證據**: best_ops 在 0 和 1 之間振盪（不是因為新公式更好，而是因為以前的 best_formula 本身就只有 1 op），best_len 在 1 和 3 之間振盪

### BUG-2: val_ic_best 永遠為 -inf [P0 CRITICAL]

**現象**: 所有 step 的 `val_ic_best=-inf`

**根因**: `best_val_ic` 初始化為 `-float("inf")`（line 1206），更新發生在 early stop block 中（line 1445-1446）。但 early stop 條件包含 `step > self.config.early_stop_warmup`，而 `early_stop_warmup=3000`。因用戶手動停止在 step 2200，early stop block 從未執行。

即使訓練到 step 3000+，問題仍在：
- early stop 僅在 `step % 200 == 0` 時檢查
- 若某 step 不在 200 倍數上，best_val_ic 也不會更新

**進階問題**: `best_val_ic` 只在 early stop block 內被更新，而非在 general tracking 中更新。這意味 `best_val_ic` 並不等於「歷史最佳 val_IC」，而是「early stop 追蹤用的最佳 val_IC」— 其更新邏輯完全被 early stop 步伐控制。

**影響**: 
- 所有依賴 best_val_ic 的機制都失效（早停、診斷）
- 報表中的 val_ic_best 毫無意義

### BUG-3: pip install torch==2.0.1+cu118 失敗 [P1 BLOCKING]

**現象**: `torch==2.0.1+cu118` pip install exit status 1

**根因**: PyTorch 自 2.2.0 起已從官方 wheel index 移除 2.0.x 和 2.1.x 版本。即使指定 `--extra-index-url` 或 `-f`，舊版本可能已被下架。

**驗證嘗試**: PyTorch wheel archive `https://download.pytorch.org/whl/torch_stable.html` 可能不包含 2.0.1+cu118。

**影響**: P100 GPU 永遠無法使用 → CPU fallback → 訓練極慢

**解法**: 
- **策略 A（推薦）**: 不安裝 PyTorch，接受 CPU 訓練但大幅優化 CPU 模式參數
- **策略 B**: 嘗試安裝 `torch==2.2.0+cu118`（較可能在 PyPI 上可用，加上延長 timeout）
  - 但 2.2.0+cu118 已不支援 sm_60 (P100)
- **策略 C**: 從 source build → 不可行（太慢）
- **結論**: P100 上 GPU 訓練已不可行。必須優化 CPU 模式。

### BUG-4: Closed-loop recovery 窗口太短 [P1 HIGH]

**現象**: with_ops 在 step 600 後崩潰到 8/32，recovery 提升到 11/32，然後再崩到 3/32

**根因**: Recovery boost 作用 200 步後 epsilon 開始衰減（`eps *= operator_epsilon_decay=0.9`），此衰減速度快於 recovery 建立的效果。而且 recovery 條件只看 `avg_ops < 0.3`，不看 `best_r` 是否已被鎖定。

**影響**: 探索恢復像彈簧 — 拉回一點又彈出去

### BUG-5: CPU 訓練速度太慢 [P2 MEDIUM]

**現象**: 2200 步花了約 30 分鐘 → 完整 12000 步需 2.7 小時，4 regime = ~11 小時超過 Kaggle 12h limit

**根因**: group_size=64 在 CPU 上計算量過大

**影響**: 訓練不完整或被 Kaggle timeout 終止

### BUG-6: v6.17 的 val_IC penalty / IC Gap penalty 從未生效 [P1 HIGH]

**現象**: v6.17 新增的 `use_val_ic_reward=True` 和 `ic_gap_weight=5.0` 在 log 中無任何痕跡

**根因**: 這些 penalty 確實在 `compute_group_rewards` 中被計算和扣分（line 878-883），但因 BUG-1（best_reward 鎖定在 step 0），這些懲罰只影響了當前 batch 的 reward 排名，但 best_reward 門檻太高（0.505），任何被懲罰的公式 reward 都無法超過 0.505。

**關鍵洞察**: val_IC penalty 和 IC Gap penalty 的設計是「懲罰爛公式」，但問題不在爛公式太多，而在「best_formula」判斷標準錯誤。operability bonus 讓爛公式獲得虛高 best_r → 門檻太高 → 好公式也無法超越 → best_formula 永遠鎖定。

---

## 三、v6.18 Eng Plan

### 設計原則

1. **reward 重構**：分離「探索獎勵」和「評估獎勵」— GRPO reward 保留 operator_bonus 鼓勵探索，但 best_formula 選擇改用 IC-based composite score
2. **CPU-first**：所有參數以 CPU 為基準設計，GPU 為 bonus
3. **減少 regime**：CPU 模式只訓練 1 個最有價值 regime

### 修改清單

| # | 優先級 | 修改 | 目標 | 實作 |
|---|--------|------|------|------|
| 1 | **P0** | `best_formula` 選擇改用 composite score | 打破 operator_bonus 虛高天花板 | `if new_composite > best_composite:` 取代 `if reward > best_reward:`；composite = train_IC * 0.3 + max(val_IC, 0) * 0.7 |
| 2 | **P0** | `operator_bonus` 降為 0.5 | 減少虛高分數的形成 | `operator_bonus: float = 2.0 → 0.5` |
| 3 | **P0** | `best_val_ic` 每步更新 | 修復 -inf bug | 將 `best_val_ic` 更新邏輯從 early stop block 移出到獨立追蹤區塊，每 200 步更新一次（不限 warmup） |
| 4 | **P1** | 移除 pip install torch | 避免安裝失敗浪費時間 | CUDA probe FAIL 直接設 CPU 模式，不再嘗試安裝 |
| 5 | **P1** | CPU 模式只訓練 mid_cap_tech | 減少 CPU 訓練時間 | `auto_detect()` 中 `GRPO_FORCE_CPU=1` → `regimes_to_train = ["mid_cap_tech"]` |
| 6 | **P1** | CPU 模式 group_size=32 | 加速 CPU 訓練 | 原為 64，CPU 下降一半計算量 |
| 7 | **P2** | Composite score 用純 IC | 確保 reward 與 IC 對齊 | 當 use_val_ic_reward=True 時，best_formula 的選擇全憑 IC，不看 operator_bonus |
| 8 | **P2** | 強制重種觸發降溫 | 延長 recovery 窗口 | best_reward 連續 1000 步未更新 → 強制 operator_epsilon 回到 0.3 + fbias 回到 -2.0 |
| 9 | **P2** | `early_stop_warmup` 降為 1000 | 更早啟用 val_ic 追蹤 | 原為 3000，CPU 模式下太晚 |

### 修改 1 詳細設計（P0 — composite score）

```python
# 現有 (BUGGY):
best_formula, best_reward, history = None, -float("inf"), []
# ...
if result["rewards"][best_idx] > best_reward:
    best_reward = result["rewards"][best_idx]
    best_formula = all_tokens[best_idx]

# v6.18 修改:
best_formula, best_composite, history = None, -float("inf"), []
# ...
# composite score: 不含 operator_bonus 的純 IC 評估
composite = train_ic[best_idx] * 0.3 + max(val_ic[best_idx], 0) * 0.7
# 加入 operator 小幅加分（不是 2.0 而是象徵性 0.05）
if best_n_ops > 0:
    composite += 0.05  # 象徵性鼓勵，不會扭曲排名
if composite > best_composite:
    best_composite = composite
    best_formula = all_tokens[best_idx]
    best_reward = result["rewards"][best_idx]  # 仍追蹤 raw reward 供報表
```

### 修改 3 詳細設計（P0 — val_ic 追蹤修復）

```python
# 現有 (BUGGY): best_val_ic 只在 early stop block 更新
# v6.18 修改: 獨立追蹤，每 200 步更新

# 在 step%200==0 的 print block 中加入:
if val_ic is not None and len(val_ic) > 0:
    current_val_ic = float(np.max(val_ic))
    if current_val_ic > best_val_ic:
        best_val_ic = current_val_ic
```

### 修改 5 詳細設計（P1 — CPU 單 regime）

```python
# auto_detect() 中:
if GRPO_FORCE_CPU:
    config.regimes_to_train = ["mid_cap_tech"]  # 最有數據的 regime
    config.train_steps = 6000  # CPU 夠用
    config.group_size = 32      # 加速
```

---

## 四、風險評估

| 風險 | 機率 | 影響 | 緩解 |
|------|------|------|------|
| composite score 完全忽略 operator_bonus → GRPO 梯度信號失真 | 中 | 中 | 保留 operator_bonus 在 reward 中（鼓勵探索），只改 best_formula 選擇邏輯 |
| mid_cap_tech 單 regime 不具代表性 | 低 | 中 | 若成功，v6.19 可一次訓練所有 regime |
| CPU 6000 步仍不夠 | 中 | 高 | 改用 T4 GPU 時可自動調高 train_steps |
| composite score 的 0.3/0.7 權重不是最優 | 中 | 低 | 可在 v6.19 調整，先驗證方向正確 |

---

## 五、驗收標準

v6.18 成功的定義：
1. `best_composite` 在 step 600 後仍有更新（非鎖定在 step 0）
2. `with_ops` 在 step 1000 後仍維持 >5/32
3. `val_ic_best` 不再是 -inf（在任何步都有數值）
4. `best_formula` 的 val_IC > 0（至少一個 regime）
5. CPU 訓練在 6 小時內完成（1 regime）
