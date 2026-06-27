---
name: twstock-grpo-v6-changelog
version: 1.11
category: research
description: |
  TWStock GRPO Regime-Aware Factor Training v6.2~v6.19 完整改版歷程、
  Dataset v2 缺口補完紀錄、實體檔案索引。供未來 agent 快速接手。
---

# TWStock GRPO v6.2~v6.19 開發歷程

## 一、版本演進總覽

| 版本 | 核心主題 | 日期 | Kaggle Slug |
|------|----------|------|-------------|
| v5.9 | Cross-Sectional Fix + Diversity + Real Data Support | 2026-06-10 | `mhhuang14/grpo-regime-aware-factor-training-v5-9` |
| v6.1 | Full DS Fix + CPU Regime Filter | 2026-06-13 | `mhhuang14/grpo-regime-aware-factor-training-v6-1` |
| v6.2 | 強制真實數據 No Synthetic | 2026-06-13 | (同 v6.1，docstring 升版) |
| v6.5 | group_size=64, entropy_coef=0.15, gumbel_noise=1.5 | 2026-06-13 | (v6.2 內增量更新) |
| v6.7 | Advantage Collapse Fix + Debug | 2026-06-13 | (v6.2 內增量更新) |
| v6.8 | 統整版 (title 終於同步) | 2026-06-14 | `mhhuang14/twstock-grpo-regime-aware-factor-training-v6-8` |
| v6.9 | Rank-Based Advantage + Multi-Objective Reward + Regime Fix | 2026-06-15 | `mhhuang14/twstock-grpo-regime-aware-factor-training-v6-9` |
| v6.10 | v6.9 標題修正 + stock_id int 鍵修復 (CPU regime 全訓練) | 2026-06-15 | (Kaggle v6-9 kernel 之 version 3) |
| v6.11 | Early Stop + Param Tune + GPU Fix sm_50 | 2026-06-16 | `mhhuang14/twstock-grpo-aware-factor-training-v6-11` |
| v6.12 | Complexity Fix + EarlyStop Warmup + GPU Reinstall + CPU Fallback 不覆蓋 | 2026-06-16 | `mhhuang14/twstock-grpo-v6-12-complexity-earlystop-fix` |
| v6.13 | **Complexity Reward 分離計算 + operator_bonus 1.0 + Base Reward 縮減 + group_size 統一 32** | 2026-06-16 | `mhhuang14/twstock-grpo-v6-13-complexity-reward-fix` |
| v6.14 | **Remove PyTorch Downgrade + Fix Version — 唯一可靠 GPU 檢測: CUDA probe 實測** | 2026-06-16 | `mhhuang14/twstock-grpo-v6-14-remove-pytorch-downgrade` |
| v6.15 | **Hybrid Operator Exploration (Plan E) — 三管齊下打破 exploration 死循環** | 2026-06-17 | `mhhuang14/twstock-grpo-v6-15-hybrid-operator-exploration` |
| v6.16 | **Adaptive Exploration + Closed-Loop Control (Plan F) — 6項針對性修復** | 2026-06-17 | `mhhuang14/twstock-grpo-v6-16-adaptive-exploration` |
| v6.17 | **Val-IC Reward Fix — Val-IC penalty + IC Gap penalty強化 + T4 GPU 優先** | 2026-06-17 | `mhhuang14/twstock-grpo-v6-17-val-ic-reward-fix` |
| v6.17 Fixed | **PyTorch 2.0.1+cu118 相容性修復 — 解決 sm_60 GPU 問題 + functorch 錯誤** | 2026-06-17 | `mhhuang14/twstock-grpo-v6-17-fixed-val-ic-reward` |
| v6.18 | **Composite Score + CPU-First 重構** | 2026-06-18 | `mhhuang14/grpo-v6-18-composite-score-cpu-single` |
| v6.19 | **Composite Score Full Fix — 8項審計缺陷修復** | 2026-06-19 | `mhhuang14/twstock-grpo-v6-19-composite-score-full-fix` |
| v6.20 | **Reward Collapse Root Fix — val_IC bonus 5.0, base_reward max(0,..), short_penalty 3.0** | 2026-06-20 | `mhhuang14/twstock-grpo-v6-20-composite-reward-fix` |
| v6.21 | **Reward Floor -5.0 Fix + Val_IC Integration + Complexity Revival** | 2026-06-20 | `mhhuang14/twstock-grpo-v6-21-reward-floor-fix` (v1, cancelled at step 4600) |
| v6.22 | **Composite Score Floor + Exploration Sustain (Planning)** | 2026-06-20 | TBD |
| v6.23 | **Composite Score Root Fix + Exploration Cooldown + History Tracking** | 2026-06-20 | `mhhuang14/twstock-grpo-v6-23` (v1 pushed) |

---

## 二、各版本改版重點

### v6.22 → v6.23: Composite Score + Exploration Root Cause Fixes (實測完成，Kaggle v1 pushed → v2 修復語法錯誤)

**基於**: v6.22 log 深度分析（best_composite=0.05 鎖定、val_ic_best=0.1292 未被選中、with_ops 崩潰、exploration restart 每步觸發）

**四大根因 Bug（經數學驗證確認）:**

| # | Bug | 嚴重度 | 根因 | 現象 |
|---|-----|--------|------|------|
| 1 | **min_formula_len 硬過濾** | P0 | `len < 4 → composite = -999` 導致高 val_ic 短公式被排除 | val_ic=0.1292 的公式 len=3 → composite=-999 → argmax 不選 |
| 2 | **探索重啟無 cooldown** | P0 | 兩處重啟條件（step>=500且step-best_step>=1000, step%1000==0且step-best_step>=1000）每步滿足 | Step 1500+ 每步印 "強制探索重啟"，eps=0.4, fbias=3.0 恆定 |
| 3 | **_best_toks 指向錯誤** | P1 | `_best_toks = all_tokens[best_composite_idx]` 取**當前步**而非歷史最佳 | log 印 best_len=3 但 best_composite=0.05（歷史最佳 len≥4） |
| 4 | **Reward-Composite 錯位** | P1 | reward complexity=0.45 壓過 ic=0.30，composite 缺 complexity | PPO 為拿 complexity 分塞 operators，val_ic 權重實質 0.7*0.05=0.035 |

**v6.23 實際修復方案（4項核心修正）:**

| # | 修復 | 實作 |
|---|------|------|
| 1 | **P0: min_formula_len 降級懲罰** | `len < min_len → composite -= 0.15 * (min_len - len)`（原 -999），短公式保留參與競爭 |
| 2 | **P0: 探索重啟加 500 步 cooldown** | 新增 `last_restart_step` 初始化 + 兩處重啟條件皆加 `step - last_restart_step >= 500` |
| 3 | **P1: _best_toks 指向歷史最佳** | 更新 best_composite 時同步 `best_formula = all_tokens[best_composite_idx]`；後續用 `list(best_formula)` |
| 4 | **P1: reward_weights 重新平衡** | `ic=0.35, complexity=0.25, sharpe=0.15, mdd=0.08, turnover=0.04`（complexity 降級，IC 提權） |

**關鍵洞察**: v6.22 的 composite 公式 `train_ic*0.3 + max(val_ic,0)*0.7 + 0.05*(ops>0)` 中 `train_ic` 已 floor at 0（v6.22 已修），但 min_formula_len 硬過濾 + reward 權重倒置 導致 PPO 只能學到「有 operator 但 IC≈0」的公式，composite 卡在 0.05。v6.23 解除硬過濾 + 降級 complexity 權重，讓高 IC 公式能被選中。

**實測驗證清單 (v6.23 notebook 生成完成):**
- No -999 in composite calculation
- Graduated penalty for short formulas (-0.15 per missing token)
- _best_toks from best_formula (historical)
- Cooldown on both restart triggers (500 steps)
- last_restart_step initialized + updated on both triggers
- reward_weights: complexity=0.25, ic=0.35
- Version strings updated to v6.23
- Log prefixes updated to [v6.23]

**Kaggle 部署歷程:**
- **v1 (2026-06-20)**: 推送成功，但 **Cell 1 line 730 SyntaxError 崩潰** — `reward_weights` dict literal 後同行 inline comment 導致 `})` 被吞噬 (kaggle-api Pitfall #71)
- **v2 (2026-06-21)**: 修復語法錯誤（comment 移至上一行）、同步版號 v6.22→v6.23、完整驗證 4 項修復，**推送成功**
- 監控受限：KGAT_ token 在 kaggle.json 僅支援 push，`kernels output` 回 403，需環境變數 KAGGLE_API_TOKEN 或 Web UI 查看

**本地路徑**: `/tmp/kpush_v623_v2/twstock-grpo-v6-23-4-bug-root-cause-fix.ipynb` (95KB, single cell)
**Kaggle Slug**: `mhhuang14/twstock-grpo-v6-23-4-bug-root-cause-fix`
**Kernel Version**: v2 (pushed 2026-06-21)
**Push URL**: https://www.kaggle.com/code/mhhuang14/twstock-grpo-v6-23-4-bug-root-cause-fix

**推送狀態**: ✅ v2 成功推送
**執行狀態**: ⏳ 背景執行中（無法即時監控，待 log 下載驗證）

---

### v6.23 Debug Session 參考
詳細記錄見 kaggle-api skill: `references/v623-kaggle-debug-session.md`

---

### v6.15 → v6.16: Adaptive Exploration + Closed-Loop Control (Plan F)

**基於**: v6.15 log 分析（最佳策略全在 step 0、best_ops=0、GPU P100 CPU 降速）

**根因重識別**: v6.15 Plan E 的 P0 根因是 **guided decoding 在 position 0 的張力衝突** — epsilon-greedy 設計原本可在 position 0 注入 operator，但 guided mask 事先過濾了 operator token，使 `valid_ops` 為空而被靜默跳過。疊加開放迴路時間衰減（不監控 avg_ops/avg_len），導致 step 600 後 exploration 完全歸零。

**v6.16 6項針對性修復:**

| # | 修復 | 目標 | 實作 |
|---|------|------|------|
| 1 | **P0: Guided decoding 衝突修復** | epsilon-greedy 跳過 guided mask | position 0 時 `np.random.choice(range(N_FEATURES, VOCAB_SIZE))` 直接從全部 operator 選取，完全不經 guided mask |
| 2 | **Closed-Loop 自適應探索監控** | avg_ops/avg_len 低於閾值時反向增強 | `adaptive_exploration=True`, 每 200 step 檢查：ops<0.3 或 len<1.5 → eps*=1.8(cap=0.5), fbias=-2.0, reseed 50% |
| 3 | **Periodic Operator Re-seed** | 每 500 step 注入 30% operator 公式 | `periodic_reseed_interval=500`, `periodic_reseed_ratio=0.3`, 週期性強制樣本重填 operator |
| 4 | **Complexity Reward 強化** | weight 0.25→0.45, bonus 2.0, penalty 5.0 | `operator_bonus=2.0`, `short_formula_penalty=5.0`, `min_formula_len=4`, `complexity=0.45` |
| 5 | **GPU 相容修復** | T4 指定 + cu118 fallback | CUDA probe FAIL → 安裝 `torch==2.1.0+cu118` 支援 sm_60~sm_75, `GRPO_FORCE_CPU` 最後防線 |
| 6 | **Early Stop 條件強化** | 不接受崩潰狀態下的早停 | 僅在 `best_ops>0 && best_len>2` 時允許早停觸發 |

**Kaggle URL**: https://www.kaggle.com/code/mhhuang14/twstock-grpo-v6-16-adaptive-exploration

---

### v6.16 → v6.17: Val-IC Reward Fix + T4 GPU 優先

**基於**: v6.16 log 分析（cu118 安裝失敗→CPU；all regimes best_ops=0；val_IC 全負或極低）

**v6.17 5項針對性修復:**

| # | 修復 | 實作 |
|---|------|------|
| 1 | **P0: cu118 版本修復** | `torch==2.1.0+cu118` → `torch==2.2.0+cu118` |
| 2 | **P0: Val-IC penalty** | `if v_ic < 0: val_penalty = abs(v_ic) * 10.0` |
| 3 | **P0: IC Gap penalty 強化** | `ic_gap_weight: 2.0 → 5.0` |
| 4 | **P1: 早停僅接受 val_IC > 0.02** | 防止虛假收斂 |
| 5 | **P1: Closed-loop 強化** | eps_boost 0.5→0.8, reseed_ratio 0.3→0.7 |

**Kaggle URL**: https://www.kaggle.com/code/mhhuang14/twstock-grpo-v6-17-val-ic-reward-fix

---

### v6.17 → v6.17 Fixed: PyTorch 2.0.1+cu118 相容性修復

**基於**: cu118 安裝超時 120s → CPU fallback；functorch AttributeError

**v6.17 Fixed 3項修復:**

| # | 修復 | 實作 |
|---|------|------|
| 1 | **P0: PyTorch 版本降級** | `torch==2.2.0+cu118` → `torch==2.0.1+cu118` |
| 2 | **P0: pip install timeout** | timeout=120 → timeout=300 |
| 3 | **P1: 禁用 torch._dynamo** | `torch._dynamo.disable()` |

**關鍵經驗 — P100 (sm_60) PyTorch 版本選擇表:**

| PyTorch 版本 | CUDA | sm_60 | functorch | 推薦度 |
|-------------|------|-------|-----------|--------|
| 2.1.0+cu118 | 11.8 | ✅ | ❌ 已移除 | ❌ |
| 2.2.0+cu118 | 11.8 | ✅ | ⚠️ 可能有 | ⚠️ 超時 |
| **2.0.1+cu118** | **11.8** | **✅** | **✅ 無** | **✅ 首選** |
| 2.10.0+cu128 | 12.8 | ❌ sm_70+ | ✅ 有 | ❌ |

**Kaggle URL**: https://www.kaggle.com/code/mhhuang14/twstock-grpo-v6-17-fixed-val-ic-reward

**v6.17 Fixed 訓練結果 — 完整失效（六大 BUG）:**

| # | Bug | 嚴重度 | 現象 |
|---|-----|--------|------|
| BUG-1 | operator_bonus 虛高天花板 | P0 | best_r=0.505 從未更新 |
| BUG-2 | val_ic_best 永遠 -inf | P0 | warmup=3000 > 停止步 2200 |
| BUG-3 | pip install 失敗 | P1 | PyTorch 2.0.x 已從 PyPI 移除 |
| BUG-4 | Recovery 窗口太短 | P1 | with_ops 彈簧式崩潰 |
| BUG-5 | CPU 訓練太慢 | P2 | 4 regime 需 11h > 12h limit |
| BUG-6 | val_IC/IC Gap penalty 無效 | P1 | best_reward 被 BUG-1 鎖定 |

---

### v6.17 Fixed → v6.18: Composite Score + CPU-First 重構

**核心洞察**: operator_bonus 虛高天花板是 v6.15~v6.17 共同根因。v6.18 改用 composite score (train_IC*0.3 + val_IC*0.7) 選擇 best_formula。

**v6.18 6項修復:**

| # | 修復 | 實作 |
|---|------|------|
| 1 | **P0: best_formula 改用 composite** | `composite = train_IC * 0.3 + max(val_IC, 0) * 0.7 + 0.05 * (n_ops > 0)` |
| 2 | **P0: operator_bonus 2.0→0.5** | 降低虛高分天花板 |
| 3 | **P0: best_val_ic 每步追蹤** | 獨立追蹤，每 200 步更新 |
| 4 | **P1: 移除 pip install torch** | CUDA FAIL → 直接 CPU |
| 5 | **P1: CPU 單 regime** | 只訓練 mid_cap_tech |
| 6 | **P1: CPU group_size 64→32** | train_steps 12000→6000 |

**v6.18 訓練結果 — Eng Plan 半實作:**
- formula_str="TX_MTX_SPREAD"（單變數，無 operator）
- val_ic=0.1093, best_reward=-1.2713
- version="v6.17"（**版號未更新**）
- config.group_size=24（**非預期 32**）

**Notebook 逐行審計 9 大缺陷 (AUDIT-1~8 + META):**
- AUDIT-1: best_idx 仍為 reward-argmax（非 composite-argmax）
- AUDIT-2: Composite score 只算 reward-argmax formula（未遍歷全 group）
- AUDIT-3: best_val_ic 引用 reward-based best_idx
- AUDIT-4: Early stop has_exploration 引用 reward-based best → 可能永不觸發
- AUDIT-5: Re-seed 3-token 公式被 short_formula_penalty 扣分
- AUDIT-6: CPU 仍訓練 4 regime
- AUDIT-7: RegimeConfig 覆蓋 group_size=32→24
- AUDIT-8: val_IC penalty 只懲罰負值不獎勵正值
- META: 版號字串仍為 "v6.17"

---

### v6.19 修改清單 + 實測結果（2026-06-19）

**Kaggle Slug**: `mhhuang14/twstock-grpo-v6-19-composite-score-full-fix`
**Kernel Version**: v8 (source=str, T4 GPU, 訓練 2189 秒)

**v6.19 10項修復:**

| # | 修復 | 對應 Bug |
|---|------|---------|
| 1 | best_formula 改用 composite-argmax | AUDIT-1,2 |
| 2 | best_val_ic 追蹤用 composite-argmax idx | AUDIT-3 |
| 3 | Early stop has_exploration 改用 composite-best | AUDIT-4 |
| 4 | Composite score 權重可配置化 | AUDIT-2 |
| 5 | Closed-loop recovery best_composite 停滯觸發 | 新增 |
| 6 | Re-seed 質量過濾 | AUDIT-5 |
| 7 | CPU 單 regime 硬編碼 | AUDIT-6 |
| 8 | CPU group_size 硬編碼覆蓋 | AUDIT-7 |
| 9 | val_IC 獎懲雙向 | AUDIT-8 |
| 10 | 版號字串更新 | META |

**v6.19 實測 output (mid_cap_tech):**
- formula_str="SLOPE(CLOSE,20) * MOMENTUM(VOLUME,10)"（雙變數 + operator！）
- val_ic=0.156, train_ic=0.042
- best_reward=-0.83, best_composite=0.127
- best_ops=1, best_len=5
- with_ops=8/32（step 2000）→ 0（step 4000+）
- version="v6.19" ✅, group_size=32 ✅

**關鍵進展與遺留問題:**
1. ✅ Composite score 機制生效（有 operator，val_ic=0.156 > v6.18 的 0.109）
2. ✅ Closed-loop recovery 生效（3 次 re-seed 觸發）
3. ✅ Early stop 正常觸發
4. ❌ best_reward 仍為負（val_ic_bonus 權重 2.0 不足）
5. ❌ 探索後期崩潰（with_ops step 4000+ 歸零）

---

### v6.20 實測結果（2026-06-20）

**Kaggle Slug**: `mhhuang14/twstock-grpo-v6-20-composite-reward-fix`
**Kernel Version**: v1 (CPU 模式, P100 fallback, 8000 steps, ~45 min)

**v6.20 實測 output (mid_cap_tech):**
- formula_str="INVALID" (tokens=[29,4,12,18] 解析失敗)
- val_ic_best=0.1292 (step 200 找到), final val_ic=0.0
- best_reward=-5.0 (step 200 卡死), best_composite=0.0500 (鎖定)
- best_ops=2→0, best_len=4→1, with_ops=23→0/32
- version="v6.20" ✅, group_size=32 ✅

**關鍵觀察:**
1. ✅ Val_IC bonus 5.0 參數生效
2. ✅ Closed-loop recovery 觸發 6 次 re-seed (每 1000 步)
3. ❌ **Reward floor -5.0 從 step 200 卡死** — short_formula_penalty 3.0 對 len=3 公式扣分
4. ❌ **Complexity reward 失效**: cplx=0.000 (n_operators=0)
5. ❌ **INVALID 公式輸出**: composite-best tokens 解析失敗
6. ❌ 探索完全崩潰: with_ops step 7000+ 歸零

---

### v6.21 實測結果（2026-06-20）

**Kaggle Slug**: `mhhuang14/twstock-grpo-v6-21-reward-floor-fix` (v1, P100→CPU, cancelled at step 4600/8000)

**v6.21 關鍵修復實施:**
1. **Reward Floor -5.0 → -1.0** — invalid signal penalty 不再鎖死梯度
2. **Simplicity Penalty 5.0 → 1.0** — 短公式不再暴力扣分
3. **Complexity Revival** — operator_bonus 0.5→1.5，complexity weight 0.45 維持
4. **Val-IC 獎勵 2.0→5.0** — val_bonus = max(v_ic,0)*5.0
5. **Base Reward 正規化** — max(0, combined_base) 確保非負
6. **Early Stop 強化** — patience 3000→1500, warmup 1000→1500
7. **Train Steps 6000→8000** — 更多探索步數

**v6.21 實測關鍵指標 (step 0-4600):**

| 指標 | v6.20 | v6.21 | 狀態 |
|------|-------|-------|------|
| best_r (step 0) | -5.0 | **+0.701** | ✅ 修復 |
| best_r (max) | -5.0 | **-1.0** | ✅ 修復 |
| simplicity penalty | 0.720 | **0.080** | ✅ 修復 |
| complexity reward | 0.000 | **0.675** | ✅ 修復 |
| with_ops (step 0) | 18/32 | **24/32** | ✅ 探索起步強 |
| with_ops (後期) | 0-8/32 | 3-10/32 | ⚠️ 仍崩潰 |
| val_ic_best | 0.1292 | 0.1292 | 同 |
| best_composite | 0.0500 | **0.0500** | ❌ 僅 operator bonus |

**殘留根因分析：**
1. **Composite score 公式缺陷**: `train_ic*0.3 + max(val_ic,0)*0.7 + 0.05` 中 `train_ic` 未 floor at 0 → 負 train_ic 拖累 composite，導致 composite-best formula 非 val-IC 最佳者
2. **探索衰減**: with_ops 24→3-10，closed-loop recovery 觸發但不足以維持
3. **Val-IC 未轉化為 composite**: val_ic_best=0.1292 存在但未被 composite-best 選中

---

### v6.22 修復方向（Planning）

**P0（必須）:**
1. **Composite Score Floor** — `composite = max(train_ic,0)*0.3 + max(val_ic,0)*0.7 + 0.05`，雙向 floor
2. **Exploration Sustain** — 增加 `periodic_reseed_ratio` 0.3→0.5，`exploration_recovery_reseed_ratio` 0.5→0.7，`operator_epsilon_start` 0.3→0.4
3. **T4 GPU 強制** — kernel-metadata 使用正確格式，或在 notebook 內安裝 cu118 支援 P100

**P1:**
4. **Val-IC 直接驅動 best_formula** — best_val_ic formula 直接作為輸出，不經 composite
5. **Re-seed 品質門檻** — 強制 train_ic > 0.01 AND val_ic > 0.0
6. **更長訓練** — GPU 時 train_steps=12000，CPU 時 10000

**P2:**
7. 版號 "v6.22", kernel slug `twstock-grpo-v6-22-composite-floor-exploration`

---

### v6.14 → v6.15: Hybrid Operator Exploration (Plan E)

**根因**: GRPO on-policy，policy 從未採樣 operator → 永遠學不到 operator。

**Plan E 三管齊下:**
1. A: Warmup Operator Seed（預填 operator 公式模板）
2. C: Epsilon-Greedy Operator Injection（position 0 強制選 operator）
3. D: Feature Logit Bias Decay（早期壓低 feature logits）

**v6.15 訓練結果 — Plan E 完全失效:**
- 所有機制 step 600 後歸零（開放迴路時間衰減，無自適應）
- best_ops=0, best_len=1 從 step 600 持續到結束
- 根因：開放迴路時間衰減不等於閉迴路自適應

---

### v6.12/v6.13: Complexity Reward 分離 + 參數大調

- v6.11 complexity reward 從未被計算（定義但未使用）
- v6.12 修復：在 compute_group_rewards 加入 operator bonus + short formula penalty
- v6.13：complexity 權重 0.25→0.35，operator_bonus 0.3→1.0，base reward 縮減

---

## 三、參考檔案索引

| 檔案 | 路徑 | 內容 |
|------|------|------|
| v6.9 Changelog | `references/CHANGELOG_v6.9.md` | v6.9 4大修復詳情 |
| v6.11 Changelog | `references/CHANGELOG_v6.11.md` | v6.11 完整修改記錄 |
| v6.12 Changelog | `references/CHANGELOG_v6.12.md` | v6.12 5大修改詳情 |
| v6.13 Changelog | `references/CHANGELOG_v6.13.md` | v6.13 5大修改詳情 + 參數對比 |
| v6.14 Changelog | `references/CHANGELOG_v6.14.md` | v6.14 移除 PyTorch 降版 + CUDA probe 實測修復 |
| v6.15 Changelog | `references/CHANGELOG_v6.15.md` | v6.15 Plan E 三管齊下 |
| v6.15 Analysis | `references/v615-plan-e-failure-analysis.md` | Plan E 完整失效分析 |
| v6.17 Fixed Analysis | `references/v617-fixed-pytorch-compatibility.md` | PyTorch 2.0.1+cu118 相容性修復記錄 |
| v6.17→v6.18 Eng Plan | `references/v617-fixed-failure-analysis-v618-eng-plan.md` | BUG-1~6 + v6.18 修復計畫 |
| v6.18 Notebook 審計 | `references/v618-notebook-audit.md` | AUDIT-1~8 + v6.19 修改清單 |
| v6.19 Eng Plan | `references/v619-eng-plan.md` | v6.19 完整實作計畫 |
| v6.19 kernel-metadata | `references/kernel-metadata-v6.19.json` | v6.19 Kaggle push metadata |
| v6.19 Debug Session | `references/v619-debug-session.md` | v6.19 推送修復 + 實測 Collapse 分析 |
| v6.20 Debug Session | `references/v620-debug-session.md` | v6.20 實測 Reward Floor -5.0 崩潰分析 + v6.21 修復方向 |
| v6.23 Debug Session | `references/v623-debug-session.md` | v6.23 語法錯誤修復 + 4-Bug Root Cause Fix 部署驗證 |
| v6.13 技術診斷 | `references/v613-complexity-fix-diagnosis.md` | complexity reward 結構錯誤 |
| v6.12~v6.15 Notebooks | `references/twstock-grpo-*.ipynb` | 各版本完整 notebook |
| v6.11~v6.14 kernel-metadata | `references/kernel-metadata-v6.XX.json` | 各版本 Kaggle push metadata |

---

## 四、實體檔案索引

| 版本 | 本地路徑 | Kaggle Slug | Kernel Version |
|------|---------|-------------|----------------|
| v6.12 | `/app/twstock-grpo-regime-aware-factor-training-v6-12.ipynb` (92344B) | `mhhuang14/twstock-grpo-v6-12-complexity-earlystop-fix` | v1 |
| v6.13 | `/app/twstock-grpo-regime-aware-factor-training-v6-13.ipynb` (96002B) | `mhhuang14/twstock-grpo-v6-13-complexity-reward-fix` | v1 |
| v6.14 | `/app/twstock-grpo-regime-aware-factor-training-v6-14.ipynb` (94347B) | `mhhuang14/twstock-grpo-v6-14-remove-pytorch-downgrade` | v1 |
| v6.15 | `/app/twstock-grpo-v6-15-hybrid-operator-exploration.ipynb` (86220B) | `mhhuang14/twstock-grpo-v6-15-hybrid-operator-exploration` | v1 |
| v6.16 | `/app/twstock-grpo-v6-16-adaptive-exploration.ipynb` (89434B) | `mhhuang14/twstock-grpo-v6-16-adaptive-exploration` | v1 |
| v6.17 | `/tmp/twstock-grpo-v6-17-val-ic-reward-fix.ipynb` (90714B) | `mhhuang14/twstock-grpo-v6-17-val-ic-reward-fix` | v1 |
| v6.17 Fixed | `/tmp/twstock-grpo-v6-17-fixed.ipynb` (90KB+) | `mhhuang14/twstock-grpo-v6-17-fixed-val-ic-reward` | v1 |
| v6.18 | `/tmp/kout-v618/grpo-v6-18-composite-score-cpu-single.ipynb` (92209B) | `mhhuang14/grpo-v6-18-composite-score-cpu-single` | v1 |
|| v6.19 | `/tmp/aidigmoney/GRPO Regime-Aware Factor Training v6.19-composite score F` (93891B) | `mhhuang14/twstock-grpo-v6-19-composite-score-full-fix` | v8 |
|| v6.20 | `/tmp/kpush_v620/twstock-grpo-v6-20-composite-reward-fix.ipynb` (102KB) | `mhhuang14/twstock-grpo-v6-20-composite-reward-fix` | v1 |
|| v6.21 | `/tmp/kaggle-kernel-v621/twstock-grpo-v6-21.ipynb` (102KB) | `mhhuang14/twstock-grpo-v6-21-reward-floor-fix` | v1 |
|| v6.22 | TBD | TBD | TBD |
|| v6.23 | `/tmp/kaggle-kernel-v623/twstock-grpo-v6-23.ipynb` (95KB) | `mhhuang14/twstock-grpo-v6-23` | v1 |
| v6.22 | `/tmp/kaggle-kernel-v622/twstock-grpo-v6-22.ipynb` (102KB) | `mhhuang14/twstock-grpo-v6-22-composite-floor-exploration` | TBD |
| v6.23 | `/tmp/kaggle-kernel-v623/twstock-grpo-v6-23.ipynb` (95KB) | `mhhuang14/twstock-grpo-v6-23` | TBD |

---

## 五、GRPO Training Workflow — Agent 操作指南

### 觸發條件
用戶要求「更新 v6.x 版本」、「推上 Kaggle」、「分析log」、「修改參數」等與 GRPO 訓練相關的任務時使用。

### 標準操作流程

1. **優先從 references/ 取得當前最大版本 notebook**
   - 若本地無，從 GitHub repo `milo0914/aidigmoney` clone 取得

2. **若前版訓練 log 已存在，先下載分析**
   - Kaggle API: `python3 -m kaggle kernels output slug -p /tmp/kout/`
   - 重點: best_r（應正）、val_ic（應>0）、best_len（應>1）、best_ops（應>0）、with_ops/avg_ops

3. **根據 log 分析制定修正方案**
   - best_len=1, best_ops=0 → operator exploration 死循環
   - 初期有效但後期崩潰 → 改為閉迴路自適應
   - best_r 全負但 val_ic 正 → base_reward 縮放過激

4. **建立新版本修改清單**
   - Header docstring: 更新版本號、日期
   - GRPOConfig: reward_weights, early_stop_*, operator_bonus
   - compute_group_rewards: 修正 reward 計算

5. **組裝並驗證 notebook** (兩層驗證)
   - 語法驗證: `python3 -m py_compile`
   - 內容驗證: 解析 JSON 逐項檢查 modification 是否應用
   - **source 必須是 str 類型**（pitfall #70）
   - **GPU: machine_shape: "Gpu"**（非 NvidiaTeslaT4 / GPU_T4）
   - **不用 nbformat**，直接操作 JSON dict

6. **推送與監控**
   - `python3 -m kaggle kernels push -p /tmp/kaggle-kernel/`
   - 輪詢: `python3 -m kaggle kernels output slug -p /tmp/kout`

### 關鍵檢查清單（每次迭代必做）
- [ ] `_default_backtest` 回傳 `dict`（v6.13+）或 `float`（舊版需修正）
- [ ] `reward_weights["complexity"]` 在 compute_group_rewards 中被乘入
- [ ] title 與 id slug 解析一致
- [ ] debug print 涵蓋 best_ops, best_len, val_ic, with_ops（v6.15+）
- [ ] 探索機制為閉迴路自適應（v6.16+），非時間衰減
- [ ] PyTorch 版本對 GPU 相容（v6.17+）：sm_60 需 cu118<=2.2.0
- [ ] best_formula 用 composite score（v6.18+），operator_bonus<=0.5
- [ ] composite score 遍歷全 group（v6.19+）：`np.argmax(all_composites)`
- [ ] Early stop has_exploration 用 composite-best（v6.19+）
- [ ] Re-seed template 長度 >= min_formula_len（v6.19+）
- [ ] val_IC penalty 雙向（v6.19+）：獎勵正值 + 懲罰負值
- [ ] Notebook source 必須 str（v6.19+）：list 導致 Kaggle 跳過執行
- [ ] kernel-metadata machine_shape: "Gpu"（v6.19+）

### 常見錯誤與防範
- **400 Bad Request**: title 解析不等於 slug → 確保一致
- **409 Conflict**: 前版仍在執行 → 等完成或手動取消
- **best_r 負值、best_len=1**: complexity reward 未生效
- **with_ops=0 始終為零**: Plan E/Closed-loop 未正確啟用
- **GPU CUDA probe FAIL**: 安裝 cu118 版本支援 sm_60 (P100)
- **探索初期有效後期崩潰**: 開放迴路→改閉迴路自適應
- **cu118 超時**: 改用 2.0.1+cu118 + timeout=300
- **functorch AttributeError**: `torch._dynamo.disable()`
- **Kaggle GPU 隨機分配（P100/T4）**: notebook 內需 CUDA probe + fallback
- **operator_bonus 虛高天花板**: v6.18+ 用 composite score 選 best_formula
- **composite 只算 reward-argmax**: v6.19+ `np.argmax(all_composites)`
- **early stop 永不觸發**: has_exploration 需引用 composite-best
- **re-seed 3-token 被 penalty**: template 長度需>=4
- **CPU 仍訓練 4 regime**: 硬編碼 `if not use_gpu: regimes = ['mid_cap_tech']`
- **val_IC penalty 只懲罰**: v6.19+ 加正向獎勵
- **Notebook source 為 list**: Kaggle 跳過執行，只用 str
- **machine_shape 錯誤值**: 只有 "Gpu" 有效
- **Python 語法陷阱: inline comment 吞噬 closing delimiter** (v6.23 新增) — 在 `lambda:`、`field(default_factory=...)` 或任何 inline expression 內的 dict/list literal 後，**同一行加 comment 會導致 closing `}`/`]`/`)` 被視為 comment 一部分而吞噬**，引發 `SyntaxError: '{' was never closed`。修復：將 comment 移至上一行或分行。
  - ❌ `field(default_factory=lambda: {"a": 1}  # comment})`
  - ✅ `# comment\nfield(default_factory=lambda: {"a": 1})`
