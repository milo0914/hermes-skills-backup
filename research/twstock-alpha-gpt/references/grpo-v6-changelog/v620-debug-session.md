# v6.20 Kaggle 實測結果與 Debug Session (2026-06-20)

## 任務背景
v6.19 遺留 reward 負值問題，v6.20 實作 P0 修復：val_IC bonus 5.0、base_reward max(0,)、short_penalty 3.0。

## 執行環境
- **GPU**: P100 (sm_60) → PyTorch 2.10+cu128 不支援 → **CPU fallback** (GRPO_FORCE_CPU=1)
- **數據**: 成功載入 5 CSV，20 檔股票，7 檔 mid_cap_tech
- **Kernel**: `mhhuang14/twstock-grpo-v6-20-composite-reward-fix` v1
- **訓練時間**: ~45 分鐘 (8000 steps, CPU)

## 關鍵參數
```python
group_size=32
train_steps=8000
device=cpu
early_stop_patience=1500
early_stop_warmup=1000
short_formula_penalty=3.0  # v6.19: 5.0
operator_bonus=0.15        # v6.19: 0.05 (composite tiny bonus)
min_formula_len=4
val_ic_bonus=5.0           # v6.19: 2.0
val_penalty=8.0            # v6.19: 10.0
ic_gap_weight=5.0
base_reward_normalization: max(0, train_ic*5 + val_ic*5 - mdd*0.05 - turnover*0.02)
```

## 訓練結果 — **Reward Floor -5.0 崩潰**

| 指標 | 結果 | 問題 |
|------|------|------|
| `best_reward` | **-5.0 (step 200 卡死)** | 全群體觸發 `short_formula_penalty` |
| `val_ic_best` | 0.1292 (step 200 找到) | 但 composite-best formula IC 不確定 |
| `train_ic` / `val_ic` (final) | 0.0 / 0.0 | 無有效信號輸出 |
| `with_ops` | 23/32 → 0/32 | 探索完全崩潰 |
| `best_composite` | 0.0500 (鎖定) | 未更新 |
| 最終公式 | `[29, 4, 12, 18]` → **INVALID** | 解析失敗 |

### 探索崩潰時序
```
Step 0:    best_r=-0.066,  with_ops=23/32, avg_ops=0.72, avg_len=2.2, best_len=3
Step 200:  best_r=-5.000, with_ops=19/32, best_composite=0.0500 ← REWARD FLOOR HIT
Step 400:  with_ops=26/32 (re-seed 暫時恢復), best_len=3
Step 800:  with_ops=21/32, best_len=3
Step 1600: closed-loop boost (eps=0.394), with_ops=5/32, best_ops=2, best_len=4
Step 2000: re-seed #1, with_ops=8/32
Step 3000: re-seed #2, with_ops=8/32
Step 4000: re-seed #3, with_ops=5/32
Step 5000: re-seed #4, with_ops=5/32
Step 6000: re-seed #5, with_ops=2/32
Step 7000: re-seed #6, with_ops=0/32
Step 8000: 完成
```

### Reward 結構分析
- **Simplicity penalty = 0.720** (log: `simp=0.720`) — 公式長度 3 < min_formula_len=4
- **Complexity reward = 0.000** (log: `cplx=0.000`) — operator_bonus=0.15 但無 operator
- **IC component = 0.000** (log: `ic=0.000`) — 無有效 IC 計算
- **Base reward 被 IC gap penalty 吃光**: val_ic=0.1292 但 train_ic≈負值 → gap penalty 5.0×

### 關鍵觀察
1. **Step 0 reward 正常 (-0.066)** → step 200 觸及 -5.0 floor → 後續全部卡在 -5.0
2. **v6.18 強制重種觸發 6 次** (每 1000 步) 但無法恢復探索
3. **Rank-based advantage 正常**: `adv_std ≈ 0.577` 全程穩定
4. **Early stop 未觸發**: patience=1500, warmup=1000，但 has_exploration 間歇性 True/False
5. **INVALID 公式**: composite-best tokens 解析失敗，導致最終 train_ic=0, val_ic=0

## 根因鏈

1. **Reward floor -5.0**: `short_formula_penalty=3.0` 對 len=3 公式扣 3.0，疊加其他懲罰 → reward ≤ -5.0
2. **Warmup 生成 3-token 公式**: step 0 best_len=3 < min_formula_len=4，從一開始就被懲罰
3. **Val_IC bonus 5.0 未生效**: composite-best formula 的 val_ic 無法在 reward 中體現
4. **IC gap penalty 雙重打擊**: train_ic 負值 + val_ic 正值 → gap 懲罰
5. **Complexity reward 失效**: n_operators=0 導致 cplx=0
6. **重種注入公式長度 3**: 仍被 simplicity penalty 扣分 → reward -5.0 → policy 學不到東西

## v6.21 修復方向

### P0 (必須)
1. **移除/降低 reward floor**: `short_formula_penalty` 只在 f_len < 2 時觸發，或移除 floor
2. **Warmup 強制生成長度 ≥4 有效公式**: seed 公式模板長度 4-5
3. **Val_IC 直接加入 base_reward** (非 bonus): `base_reward = val_ic * 5 + ...` 確保正值
4. **IC gap penalty 只懲罰 overfit**: `max(0, train_ic - val_ic - threshold)` → 不懲罰 val_ic > train_ic

### P1
5. **Complexity reward 恢復**: operator_bonus=1.0, 確保 n_operators > 0 時有加成
6. **Re-seed 公式長度 ≥4 + val_ic > 0 過濾**
7. **CPU G=64, batch=128** (當前 G=32 探索不足)

### P2
8. **多 regime CPU 並行** 或 **爭取 T4 GPU**

## 相關檔案
- Kaggle Kernel: https://www.kaggle.com/code/mhhuang14/twstock-grpo-v6-20-composite-reward-fix
- 本地 log: `/tmp/kout_v620/twstock-grpo-v6-20-composite-reward-fix.log`
- 輸出: `best_strategy_per_regime.json`, `training_report.json`