# GRPO v6.10 訓練結果分析

## 資料來源
- Kaggle kernel: `mhhuang14/twstock-grpo-regime-aware-factor-training-v6-9` version 8
- 下載時間: 2026-06-16
- 下載指令: `python3 -m kaggle kernels pull mhhuang14/twstock-grpo-regime-aware-factor-training-v6-9`

## 4-Regime 訓練結果

| Regime | Best Formula | Train IC | Val IC | IC Gap | 問題診斷 |
|--------|-------------|----------|--------|--------|----------|
| TRADITIONAL | LIQ_SCORE | 0.045 | 0.024 | 0.021 | IC 弱，但有泛化 |
| LARGE_CAP | LIQ_SCORE | 0.051 | -0.012 | 0.063 | val_IC 負值! 嚴重 overfit |
| MID_CAP_TECH | SP500_CLOSE | 0.035 | 0.019 | 0.016 | IC 弱 + 退化趨勢 |
| FINANCIAL | CLOSE_POS | 0.028 | 0.015 | 0.013 | IC 全體最弱 |

## IC 評級
- TRADITIONAL: 0.024 → 弱信號 (0.05~0.10)
- LARGE_CAP: -0.012 → 無效因子 (< 0.05)
- MID_CAP_TECH: 0.019 → 弱信號 (0.05~0.10)
- FINANCIAL: 0.015 → 弱信號 (0.05~0.10)

## 核心問題診斷

### P0: IC 停滯 (Critical)
- IC 在 step 1000 後幾乎無改善
- 後續 14000 steps 浪費 GPU 時間
- v6.11 對策: train_steps 15000→8000 + early_stop_patience=500

### P1: 因子過度簡化 (Critical)
- 全部 4 個 regime 的 best formula 都是單一特徵
- LIQ_SCORE / SP500_CLOSE / CLOSE_POS = 1-2 tokens
- 缺乏運算符組合 (+, -, *, /)
- v6.11 對策: min_formula_len=3, operator_bonus=0.1, complexity weight=0.05

### P2: LARGE_CAP val_IC 負值 (Critical)
- Train IC=0.051 vs Val IC=-0.012，IC Gap=0.063
- 完全沒有泛化能力
- v6.11 對策: group_size 維持 64（v6.10 已設），增加 temperature_end=0.8

### P3: MID_CAP_TECH IC 退化 (Medium)
- group_size=12 太小，探索不足
- v6.11 對策: group_size 12→24

### P4: Temperature 衰減過快 (Medium)
- temperature_decay_steps=5000，step 5000 後只剩 low-temperature exploitation
- v6.11 對策: decay_steps 5000→8000, temperature_end 0.5→0.8

### P5: 無 Early Stopping (Low)
- 即使 IC 不再改善，仍跑完 15000 steps
- v6.11 對策: early_stop_patience=500, early_stop_min_delta=1e-4

## v6.10 → v6.11 修改決策映射

| 問題 | v6.10 值 | v6.11 值 | 預期效果 |
|------|---------|---------|----------|
| P0 停滯 | train_steps=15000 | 8000 | 節省 GPU 時間 |
| P0 停滯 | 無 early stop | patience=500 | 自動停止無效訓練 |
| P1 簡化 | 無複雜度獎勵 | min_formula_len=3, operator_bonus=0.1 | 生成更長公式 |
| P2 負值 | temperature_end=0.5 | 0.8 | 保留探索動力 |
| P3 退化 | MID_CAP_TECH gs=12 | 24 | 更大範圍探索 |
| P4 衰減快 | decay_steps=5000 | 8000 | 延長探索期 |
| P5 浪費 | 無 | early_stop | 自動偵測停止 |
