# v6.15 Plan E 完整失效分析 + v6.16 修正方案

**日期**: 2026-06-17  
**Kaggle Kernel**: `mhhuang14/twstock-grpo-v6-15-hybrid-operator-exploration`  
**Log**: `/tmp/kaggle-v615-logs/twstock-grpo-v6-15-hybrid-operator-exploration.log`

---

## 1. 訓練環境

| 項目 | 值 |
|------|-----|
| GPU | Tesla P100-PCIE-16GB (sm_60) |
| PyTorch | 2.10.0+cu128 |
| CUDA Probe | **FAIL** (no kernel image for device) |
| 模式 | **CPU Fallback** (GRPO_FORCE_CPU=1) |
| Train Steps | 5000 (CPU 模式) |

**關鍵問題**: P100 (sm_60) 不支援 PyTorch 2.10+cu128 → 全程 CPU 訓練，極慢。

---

## 2. Plan E 三機制運作時間軸

### Epsilon-Greedy (`eps`: 0.30 → 0)
| Step | eps | with_ops | avg_ops | avg_len | 狀態 |
|------|-----|----------|---------|---------|------|
| 0 | 0.300 | 16/32 (50%) | 0.50 | 1.8 | ✅ 有效 |
| 200 | 0.300 | 16/32 (50%) | 0.50 | 1.8 | ✅ 有效 |
| 400 | 0.300 | 16/32 (50%) | 0.50 | 1.8 | ✅ 有效 |
| 600 | 0.270 | **0/32 (0%)** | **0.00** | **1.0** | ❌ **崩潰** |
| 800 | 0.270 | 0/32 | 0.00 | 1.0 | ❌ |
| 1000 | 0.243 | 0/32 | 0.00 | 1.0 | ❌ |
| ... | ... | 0/32 | 0.00 | 1.0 | ❌ |
| 2000 | 0.197 | 0/32 | 0.00 | 1.0 | ❌ (eps 歸零) |

### Feature Logit Bias (`fbias`: -2.0 → 0)
| Step | fbias | 狀態 |
|------|-------|------|
| 0 | -2.00 | ✅ 壓制 feature |
| 400 | -1.60 | ✅ |
| 600 | -1.40 | ⚠️ 已不足 |
| 2000 | 0.00 | ❌ 完全歸零，feature 完全佔優 |

### Warmup Operator Seed
- 僅 step 0 初始化有效 (with_ops=50%)
- **無後續 re-seed**，step 600 後徹底失效

---

## 3. 核心指標崩盤證據

### Best Reward 停在 Step 0
```
traditional:  best_r=0.205 (step 0) → 結束仍 0.205
large_cap:    best_r=0.191 (step 0) → 結束仍 0.191
mid_cap_tech: best_r=0.146 (step 0) → 結束仍 0.146
financial:    best_r=0.206 (step 0) → 結束仍 0.206
```

### Best Formula 全為 1-token
```
traditional:  (VOL_BREAKOUT MUL RET)        → 3 tokens 但 best_len=3 只有初期
large_cap:    (FIVE_DAY_HIGH MUL CVD_PROXY) → 同
mid_cap_tech: (FOMO MUL RET)                → 同
financial:    (DEV SUB LOG_VOL)             → 同
```
**實際上 best_len=1 從 step 600 開始**，最終輸出的公式是早期殘留。

### Validation IC 全負 (除 mid_cap_tech)
| Regime | Train IC | Val IC | IC Gap |
|--------|----------|--------|--------|
| traditional | 0.033 | **-0.084** | 0.118 |
| large_cap | 0.017 | **-0.027** | 0.044 |
| mid_cap_tech | 0.001 | **0.011** | -0.010 |
| financial | 0.028 | **-0.016** | 0.044 |

### Complexity Reward 分量 (step 0 vs step 600+)
```
Step 0:  ic=0.059  cplx=0.250  simp=0.000  len_b=0.080  ← 有 complexity reward
Step 600: ic=0.168  cplx=0.000  simp=0.300  len_b=0.000  ← complexity=0, simplicity=0.3
```
**Complexity reward 在 step 600 後完全歸零**，simplicity reward 反而為正 (懲罰長公式)。

---

## 4. 根因深度剖析

### 4.1 開放迴路 vs 閉迴路
Plan E 三機制皆為**預設時間表衰減**，無視實際探索狀態：
- `eps` 依步數線性衰減，不看 `avg_ops`
- `fbias` 依步數線性歸零，不看 `avg_len`
- `operator_seed` 只在初始化，無週期性注入

**修正**: 需改為**閉迴路自適應** — 監控 `avg_ops`/`avg_len`，探索崩潰時反向增強。

### 4.2 Complexity Reward 權重仍不足
當前 v6.15 設定：
```python
reward_weights = {"complexity": 0.35, ...}
operator_bonus = 1.0
short_formula_penalty = 3.0
min_formula_len = 3
```
但當 `avg_ops=0` 時，**沒有任何公式能獲得 operator_bonus**，complexity reward 結構性歸零。

### 4.3 GPU 不可用 → CPU 訓練步數不足
- CPU 模式 5000 steps 實際有效探索 < 600 steps
- Early stop patience=1200, warmup=2000 → 實際訓練窗口極小

### 4.4 Early Stop 判斷邏輯缺陷
早停只看 `val_ic` 是否改善，**不檢查 `best_ops>0` 和 `best_len>2`**。
當 best_ops=0 時，val_ic 偶然波動改善即觸發「收斂」，實則是崩潰。

---

## 5. v6.16 修正方案總覽

| 類別 | 項目 | v6.15 | v6.16 | 理由 |
|------|------|-------|-------|------|
| **GPU** | PyTorch 版本 | 2.10+cu128 (不支援 sm_60) | **2.1.0+cu118** | P100 唯一相容版本 |
| **探索** | Epsilon 衰減 | 固定 0.9/500步 | **自適應**: avg_ops<0.5 時反向提升 | 閉迴路控制 |
| **探索** | Feature bias | 固定線性歸零 | **自適應**: avg_len<1.5 時重新壓制 | 閉迴路控制 |
| **探索** | Operator seed | 僅初始化 | **每 500 steps 重新注入 30%** | 持續探索壓力 |
| **Reward** | complexity weight | 0.35 | **0.45** | 更強拉力 |
| **Reward** | operator_bonus | 1.0 | **1.5** | 讓 1 operator 足以覆蓋 base 負值 |
| **Reward** | short_penalty | 3.0 | **4.0** | 更強懲罰 1-token |
| **Reward** | min_formula_len | 3 | **4** | 提高門檻 |
| **Reward** | IC weight | 5.0 | **4.0** | 降低避免貪婪短公式 |
| **CPU** | train_steps | 5000 | **8000** | 補足探索時間 |
| **CPU** | early_stop_patience | 1200 | **2000** | 更寬容 |
| **CPU** | early_stop_warmup | 2000 | **3000** | 更長觀察期 |
| **EarlyStop** | 條件 | 只看 val_ic | **需 best_ops>0 且 best_len>2** | 避免偽收斂 |

---

## 6. 實作優先級

| 優先級 | 項目 | 工作量 | 風險 |
|--------|------|--------|------|
| P0 | GPU 相容性 (安裝 torch 2.1+cu118) | 低 | 低 |
| P0 | 自適應探索機制 (核心) | 中 | 中 |
| P0 | 週期性 re-seed | 低 | 低 |
| P1 | Complexity reward 參數調升 | 低 | 低 |
| P1 | CPU 參數調整 | 低 | 低 |
| P1 | Early stop 條件強化 | 低 | 低 |

---

## 7. 驗收標準 (v6.16)

- [ ] **GPU 可用**: CUDA probe PASS，log 顯示 `device=cuda`
- [ ] **with_ops > 0 維持全程**: 至少 50% steps 有 operator 採樣
- [ ] **best_ops ≥ 1 從早期開始**: 不能只停在 step 0
- [ ] **best_len ≥ 2 持續**: 平均長度 > 1.5
- [ ] **val_ic > 0 至少 2 個 regime**: 不能全負
- [ ] **best_r 明顯超越 step 0**: 至少 +0.05 提升
- [ ] **不早停於崩潰狀態**: best_ops=0 時不觸發早停