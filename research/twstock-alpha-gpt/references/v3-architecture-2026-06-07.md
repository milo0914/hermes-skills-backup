# v3 分層遞進式架構設計記錄 (2026-06-07)

## 架構決策

### 方案評比 (用戶提出三大問題後觸發)

| 方案 | 描述 | 評分 | 結論 |
|------|------|------|------|
| A-1 串聯式 | GRPO → Rule-based 串接 | 3.5/6 | GRPO 處理全量數據信噪比低 |
| A-2 並聯式 | GRPO ∥ Rule-based 取交集 | 3.2/6 | 兩路獨立無法互相增強 |
| **A-3 分層遞進** | Rule-based 先篩 → GRPO 增強 → 反饋 | **5.15/6** | **勝出** |

### 三大問題與答案

1. **因子訓練模型會因股性不同嗎？** → 會。MegaCap 的 inst_flow 有效，生技股的 margin_press 有效。必須分群訓練。
2. **需要先針對特定標的個別訓練嗎？** → 是。3-5 檔代表性標的 (2330/2454/1301/2882) 驗證流程後再擴展。
3. **系統應先 rule-based 篩選再作因子訓練嗎？** → 是。A-3 方案最優：粗篩降噪 → GRPO 增強 → 反饋閉環。

## 五階段管線設計

### Phase 1: 宏觀粗篩 (Rule-based)
- 全市場 → 50-100 檔候選池
- Stage1 宏觀情緒 + Stage2 技術形態
- 閾值動態：勝率 >60% 放寬 5%，<40% 收緊 5%

### Phase 2: GRPO 因子增強 (Regime-aware)
- StockRegime.detect() → 分群
- 每個 regime 有獨立的 feature_mask / operator_mask / feature_weights
- alpha_score = GRPO因子分數 × 衰減係數 + rule-based分數
- 衰減係數：IC < 0.01 → alpha_score = 0 (降級回純 rule-based)

### Phase 3: 微觀點位 (Wenty)
- CVD 背離 + 吸收現象 + 衝浪手切入
- 未變更，沿用 v2

### Phase 4: 動態風控 (3-7天持倉適配)
- Per-regime 持倉參數 (target_holding_days, trailing_stop_method)
- 三種移動止損：ATR / five_day_high / close_ma

### Phase 5: 反饋閉環
- 回測 per_stock 結果 → 閾值更新 + reward 權重調整 + time_stop 校準
- 需 ≥20 筆交易樣本才可靠

## StockRegime 四股性

| Regime | 偵測條件 | 特徵遮罩重點 | 持倉 | 移動止損 |
|--------|----------|-------------|------|----------|
| MegaCap | 市值 > 5000億 | inst_flow, cvd_proxy, vol_breakout | 5天 | ATR |
| SmallCapHighVol | 波動 > 3% + 市值 < 500億 | margin_press, mom_rev, surf_entry | 3天 | five_day_high |
| FinancialLowVol | 金融股 + 波動 < 1.5% | close_pos, absorption, dev | 7天 | close_ma |
| CyclicalTrend | 營收 YoY > 10% | atr, liq_score, pressure | 5天 | ATR |

## 實作檔案變更

| 檔案 | v3 變更 | 大小 |
|------|---------|------|
| `stock_regime.py` | **新增** StockRegime + RegimeTrainingPlan | 18.8 KB |
| `grpo_alpha_trainer.py` | regime-aware _generate_group / _mutate / _random_formula + train_regime_numpy + train_batch_regime | 36.5 KB |
| `ai_dig_money_core.py` | AIDigMoneyV3Pipeline (5-Phase) + StockSignal 擴展 (regime, alpha_score, target_holding_days, trailing_stop_method) + phase5_feedback() | 55.0 KB |
| `twstock_alpha_engine.py` | TWBacktest v3: 3 種 trailing_stop_method + per-signal 持倉參數 + per_stock 反饋明細 | 24.4 KB |

## 保留的 AlphaGPT 設計核心

- StackVM 因子公式執行 (evaluate_formula_vm)
- 16 維特徵 + 12 算子 (vocab_size=28)
- GRPO 策略梯度 (Group Relative Policy Optimization)
- Looped Transformer 架構 (d_model=64, nhead=4, num_loops=3)
- 過擬合五層防護

v3 僅在 GRPO 的「生成層」加入 regime 約束（mask/weights），不改變 StackVM 執行邏輯和 reward 機制。

## 待後續

- 3-5 檔標的個別訓練驗證
- DELAY1 → DELAY_N 因子延遲適配 (依 regime holding_window)
- Walk-forward 校準 [UNCALIBRATED] 閾值
- Phase 5 反饋持久化 (閾值版本管理)
