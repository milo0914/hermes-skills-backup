# v6.19 實測結果 + v6.20 修復方向（2026-06-19）

**Kaggle Slug**: `mhhuang14/twstock-grpo-v6-19-composite-fix-cpu`
**Title**: "GRPO v6 19 Composite Fix CPU Single"
**本地檔案**: `/tmp/kout-v619/grpo-v6-19-composite-fix-cpu.ipynb`

## v6.19 實測 output (mid_cap_tech regime)
- `formula_str="SLOPE(CLOSE,20) * MOMENTUM(VOLUME,10)"`（雙變數 + operator！）
- `val_ic=0.156`, `train_ic=0.042`
- `best_reward=-0.83`, `best_composite=0.127`
- `best_ops=1`, `best_len=5`
- `with_ops=8/32`（step 2000 後），`avg_ops=0.25`
- `version="v6.19"` ✅
- `config.group_size=32` ✅

## 關鍵觀察
1. **Composite score 機制生效**：best_formula 有 operator（1 個）、長度 5，val_ic=0.156 > v6.18 的 0.109
2. **Closed-loop recovery 生效**：step 1200/2200/3200 三次 re-seed 觸發（best_composite 停滯 ≥1000 步）
3. **Early stop 正常觸發**：step 4100 patience=800 觸發（has_exploration 基於 composite-best 判斷為 True）
4. **但**：`best_reward` 仍為負值，`val_ic_bonus` 權重 2.0 仍不足以讓正 IC 公式 reward 為正

## v6.19 遺留問題（v6.20 需修復）

| # | 問題 | 影響 | 優先級 |
|---|------|------|--------|
| 1 | **val_IC reward 權重不足**：正 val_ic=0.156 但 reward=-0.83 | 最佳公式 reward 為負，policy 學習信號混淆 | P0 |
| 2 | **Operator tiny bonus 僅 0.05**：不足以補償 short penalty | 含 operator 公式仍處於劣勢 | P0 |
| 3 | **Re-seed 無品質過濾**：仍注入未驗證公式 | 部分 re-seed 公式 reward 更低 | P1 |
| 4 | **Early stop patience=800 偏短**：可能提早停止探索 | 6000 步未跑完就停 | P1 |
| 5 | **CPU 單 regime 確認**：只跑 mid_cap_tech，其他 3 regime 未驗證 | 設計意圖確認，非 bug | P2 |

## v6.20 修復方向

### P0（必須）
1. **val_IC 獎勵權重 2.0 → 5.0**，val_penalty 10.0 → 8.0（雙向更平衡）
2. **Operator bonus 0.05 → 0.15**（tiny bonus 升級為小額獎勵），short_penalty 5.0 → 3.0（4-len）*2
3. **Base reward 正規化**：`base_reward = max(0, train_ic * 5 + val_ic * 5 - mdd * 0.05 - turnover * 0.02)` — 確保 val_ic > 0 的公式 base_reward ≥ 0

### P1
4. **Re-seed 品質過濾**：僅接受 `val_ic > 0.01 or train_ic > 0.02` 的公式
5. **Early stop patience 800 → 1500**，warmup 1000 → 1500
6. **新增 step 5000+ 檢查**：若 best_composite 仍在更新 → 延長到 8000 步

### P2
7. 版號字串 "v6.20"，kernel slug `twstock-grpo-v6-20-composite-reward-fix`