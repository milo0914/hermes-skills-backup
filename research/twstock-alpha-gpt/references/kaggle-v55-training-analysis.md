# Kaggle V5.5 GRPO 訓練結果分析 (2026-06-10)

## 環境
- GPU: Tesla T4 (15.6GB), CUDA sm_75
- PyTorch 2.10.0+cu128, NumPy 2.4.6
- 訓練耗時: 2370 秒 (39.5 分鐘)

## 數據
- OHLCV: 3372 筆, 4 檔 (2330/2454/1301/2882)
- 期貨OI: 1686 筆, 美股指數: 2622 筆
- 日期範圍: 2022-01-03 ~ 2025-06-30 (3.5年)
- 特徵計算後: 843 筆 (rolling window + forward-fill 截斷)

## 訓練結果

### Regime 分群 — 只有 1 個 regime 進入訓練
日誌: `[Multi-Regime] 分群結果: mid_cap_tech: [2882]`
但 KNOWN_REGIMES 定義 2882 → FINANCIAL (不是 mid_cap_tech!)
2330/2454/1301 完全消失，可能因 feat_tensor NaN 被跳過。

### Loss 恆為 0 — P0 根因
Step 0~19500: loss=-0.0000 (全部!)

根因: V5.5 仍使用 PPO clipped surrogate `ratio = exp(log_pi - log_pi.detach())`
- ratio 恆等於 1.0 (自減自身)
- clip(1.0, 1-0.2, 1+0.2) = 1.0
- surr1 = surr2 = 1.0 * advantages
- loss = -min(surr1, surr2).mean() = -advantages.mean() ≈ 0 (advantages 標準化後均值=0)

**v3.5 REINFORCE 修復未進入 V5.5!** V5.5 仍用 PPO clipped surrogate。

### Reward 停滯
- Step 0: mean_r=-0.159, best_r=0.007
- Step 500: mean_r=1.296, best_r=1.296
- Step 500~19500: 完全停滯 (loss=0 → 梯度=0 → 參數不更新)
- 模型靠 entropy 在前 500 步找到 SP500_CLOSE 後凍結

### 最佳公式 — 退化為單因子
- Decoded: SP500_CLOSE (token [20])
- 預期應為複合公式如 SP500_CLOSE * TX_INST_NET_OI
- 模型停在 1 token 因為 loss=0 無動力探索更長公式

### Walk-Forward 驗證
- 2882: Mean IC=0.071, t-stat=0.54, Positive folds=80%
- t-stat < 2.0，統計不顯著

### Training History 空記錄
- `{"2882": []}` — trainer.history 寫入邏輯問題

## 缺陷清單

| ID | 嚴重度 | 描述 | 修復方案 |
|----|--------|------|----------|
| V55-P0 | 致命 | PPO ratio≡1 → loss≡0 → 梯度消失 | 套用 v3.5 REINFORCE: loss=-(log_prob*advantage).mean() |
| V55-P1 | 高 | 4檔只1檔進入訓練, regime映射錯誤 | 檢查 feat_tensor NaN + regime_key 映射 |
| V55-P2 | 中 | training_history.json 空記錄 | 修復 history.append() 位置 |
| V55-P3 | 低 | 公式退化為單因子 | 修復 P0 後自然解決 + 加長度 reward |

## 關鍵教訓
1. **版本回退檢查**: V5.5 建構時未合併 v3.5 REINFORCE 修復，導致 PPO loss≡0 問題重現。每次建構新版本必須確認所有已修復 pitfall 的對應代碼是否在源文件中。
2. **Regime 分群診斷**: 日誌中 regime key 與 KNOWN_REGIMES 不一致時，需檢查 `train_all_regimes` 的 regime_key 處理邏輯（`regime.value` vs `str(regime)`）。
3. **Loss=0 快速診斷法**: 若 loss 連續 >1000 步為 -0.0000，必是 ratio≡1 或 advantage 均值=0 問題。
