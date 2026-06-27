# GRPO 訓練結果分析範本 (v6.11 更新)

## 分析步驟

1. 下載 Kaggle output
   ```bash
   python3 -m kaggle kernels output mhhuang14/twstock-grpo-regime-aware-factor-training-v6-9 -p ./output --force
   ```

2. 讀取 `training_report.json` 和 `best_strategy_per_regime.json`

3. 生成 regime 對比表
   | Regime | Stocks | Best Formula | Formula Len | Train IC | Val IC | IC Gap | Best Reward | Best Step |
   |--------|--------|-------------|-------------|----------|--------|--------|-------------|-----------|
   | ... | ... | ... | ... | ... | ... | ... | ... | ... |

4. 評估每個 regime:
   - IC Gap < 0: val > train (無 overfit，罕見但好)
   - IC Gap 0~0.03: 可接受
   - IC Gap > 0.05: overfit 嚴重
   - Val IC < 0: 無效因子

5. v6.11 新增檢查項目:
   - **Formula Length**: 是否 >= min_formula_len=3 tokens
   - **Best Step**: 是否在 early_stop_patience 前（=有持續改善）
   - **n_steps**: 實際步數是否 < train_steps=8000（=early stop 有觸發）
   - **Temperature at end**: 終端溫度是否接近 0.8（延遲衰減生效）

6. 檢查 log 中的關鍵指標:
   - `adv_std` 是否穩定 (Rank-based 應≈0.577)
   - `loss` 收斂趨勢
   - `temperature` 遞減是否正常（v6.11: 8000步才到 0.8）
   - 是否有 `NaN detected` 或模型重初始化
   - 是否出現 `Early stopping at step N` 訊息
   - `complexity_reward` 是否生效（公式長度是否增加）

## v6.11 特定監控項目

| 項目 | 預期 | 判定標準 |
|------|------|----------|
| IC 持續改善 | 到 step 8000 仍改善 | best_step > 1000 |
| 公式長度 | >= 3 tokens | operator_bonus + complexity weight 生效 |
| Large_Cap val_IC | > 0 | group_size=64 + temperature_end=0.8 |
| Early stopping | 適當觸發 | n_steps < 8000 或 best_step 在合理範圍 |
| adv_std | ≈0.577 | Rank-based 保證 |

## IC 評級標準
- IC > 0.15: 生產級因子
- IC 0.10~0.15: 可用但需改進
- IC 0.05~0.10: 有信號但弱
- IC < 0.05: 無效

## 下一步決策樹 (v6.11 更新)
- 所有 regime val_IC > 0.05 → 可直接匯出到 ai_dig_money_core.py
- 部分 regime val_IC < 0 → 增加該 regime 的 train_steps 或調整 reward weights
- 全部仍為單一特徵因子 → 增加 operator_bonus (0.1→0.2) 或 entropy_coef (0.25→0.35)
- early stop 太早觸發 → 增加 early_stop_patience (500→1000)
- early stop 未觸發且 IC 停滯 → 增加 early_stop_min_delta 精度
- adv_std 不穩定 → 檢查 group_size，可能需動態調整
- 公式長度仍 < 3 → 增加 complexity weight (0.05→0.10) 或 min_formula_len (3→4)
