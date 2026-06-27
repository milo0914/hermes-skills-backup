# TWStock GRPO v6.15 Changelog — Hybrid Operator Exploration (Plan E)

**Date**: 2026-06-17
**Kaggle Slug**: `mhhuang14/twstock-grpo-v6-15-hybrid-operator-exploration`
**Based on**: v6.14 (Remove PyTorch Downgrade + CUDA probe)

---

## 根因分析：Operator Exploration 死循環

**現象** (v6.14 log step 3200):
- `best_ops=0`, `best_len=1`, `cplx=0.000`, `len_b=0.000`, `with_ops=0`

**根因**: GRPO 是 **on-policy** 方法
- Policy 從未採樣到 operator token → 永遠學不到 operator 的優勢
- Reward landscape 已正確：3-token reward=+0.374 vs 1-token=-0.256
- 問題在 **generation 端的 exploration 死循環**，非 reward 計算錯誤

**六層結構性缺陷**:
1. Warmup 只引導 feature，不含 operator
2. Fallback 機制強化 1-token 公式（因為只見過 1-token）
3. Credit assignment 粒度太粗（group-level），operator token 無法獲得獨立信用
4. 22 features vs 12 operators → feature 先天概率優勢 ~2:1
5. Gumbel/temperature 探索不足以打破初始分布
6. Diversity penalty 在 operator 稀疏時反效果

---

## v6.15 Plan E：三管齊下

### A: Warmup Operator Seed (v6.15A)
- **參數**: `operator_seed_ratio=0.5` (Warmup 中 50% 使用預填模板)
- **模板**: 二元 `[f1, f2, ADD/MUL/SUB/DIV]`、一元 `[f1, NEG]`、變體 `[f1, f2, MUL]`
- **選擇策略**: 依 FeatureWeight 排序選 top-k feature
- **關鍵**: Autoregressive log_prob 計算保持可微分，不切斷梯度

### C: Epsilon-Greedy Operator Injection (v6.15C)
- **參數**: `operator_epsilon_start=0.3` → position 0 時 30% 強制選 operator
- **參數**: `operator_epsilon_decay=0.9` → 每 500 步衰減 10%
- **關鍵**: 強制 action 仍用 `dist.log_prob(forced_action)` 保留梯度流向

### D: Feature Logit Bias Decay (v6.15D)
- **參數**: `feature_logit_bias_start=-2.0` → 早期壓低 feature logits (約 0.12x 概率)
- **參數**: `feature_logit_bias_decay_steps=2000` → 線性歸零至 0
- **效果**: 早期強制探索 operator 空間，隨訓練恢復自然分布

---

## 新增 GRPOConfig 參數

| 參數 | 預設值 | 說明 |
|------|--------|------|
| `operator_seed_ratio` | 0.5 | Warmup 中預填 operator 公式比例 |
| `operator_epsilon_start` | 0.3 | Position 0 強制選 operator 概率 |
| `operator_epsilon_decay` | 0.9 | 每 500 步 epsilon 衰減因子 |
| `feature_logit_bias_start` | -2.0 | Position 0 feature logit 初始壓制 |
| `feature_logit_bias_decay_steps` | 2000 | Logit bias 線性歸零步數 |

---

## 新增 Logging (每 200 步)
```
eps=0.30, fbias=-2.00, with_ops=12, avg_ops=1.5, avg_len=3.2
```
- `eps`: 當前 epsilon 值
- `fbias`: 當前 feature logit bias
- `with_ops`: 含 operator 的生成樣本數
- `avg_ops`: 平均 operator 數量
- `avg_len`: 平均公式長度

---

## 保留 v6.2~v6.14 全部功能
- Rank-Based Advantage (std≈0.577 保證)
- LORD Diversity (logits penalty + entropy bonus)
- Multi-Objective Reward (IC, Sharpe, MDD, Turnover, Complexity)
- Overfit Penalty (Train-Val IC gap)
- Regime-Aware Training (4 regimes)
- Early Stopping (warmup=2000, patience=1200)
- CUDA Probe GPU 檢測 (無 PyTorch 降版)

---

## 預期驗收標準

| 指標 | v6.14 (step 3200) | v6.15 目標 |
|------|------------------|------------|
| `best_ops` | 0 | > 0 (早期 500 步內) |
| `best_len` | 1 | ≥ 3 |
| `with_ops` (per 200 step) | 0 | > 0 |
| `avg_ops` | 0 | ≥ 1.0 |
| `val_ic` | ~0.01 | > 0.02 |

---

## Kaggle 執行
```bash
python3 -m kaggle kernels push -p /tmp/kaggle-kernel/
```
- Accelerator: GPU_T4
- Dataset: `mhhuang14/twstock-v6-0-real-data-20stocks-5y`
- Docker: `gcr.io/kaggle-private-byod/python@sha256:57e612b484cf3df5026ee4dcc3cb176974b22b2bc0937fb1e16132a8be4cb13c`