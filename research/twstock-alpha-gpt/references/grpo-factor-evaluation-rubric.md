# GRPO 因子評估 Rubric (v6.10, 2026-06-15)

## IC（Information Coefficient）水準分級

Spearman Rank IC = corr(rank(signal), rank(forward_returns))

| IC 範圍 | 品質等級 | 用途 |
|---------|----------|------|
| |IC| < 0.02 | 噪聲 | 不可用 |
| 0.02 ~ 0.05 | 微弱 | 邊際，不可單獨使用 |
| 0.05 ~ 0.10 | 偏低但可使用 | 可作組合因子之一，不可獨立 |
| 0.10 ~ 0.15 | 中等 | 可用作組合核心因子 |
| 0.15 ~ 0.30 | 良好 | 單因子可直接使用 |
| > 0.30 | 優秀 | 極少見，需驗證非 overfit |

## IC Gap（Overfit 衡量）

ic_gap = train_IC - val_IC

| ic_gap | 意涵 |
|--------|------|
| < 0 | val 比 train 好，最佳泛化 |
| 0 ~ 0.03 | 輕微 overfit，可接受 |
| 0.03 ~ 0.05 | 中度 overfit，需留意 |
| > 0.05 | 嚴重 overfit（程式內 ic_gap_threshold=0.05 觸發 penalty） |

## Multi-Objective Reward 分解

```
reward = 0.5 * (IC * 10) + 0.25 * (Sharpe * 5) + 0.15 * (MDD_penalty) + 0.1 * (Turnover_penalty)
```

| 維度 | 權重 | 縮放 | 公式 | 意涵 |
|------|------|------|------|------|
| IC | 0.5 | *10 | spearman_corr(signal, returns) | 預測排序能力 |
| Sharpe | 0.25 | *5 | mean(sig*ret) / std(sig*ret) | 風險調整後收益 |
| MDD penalty | 0.15 | -mdd*2 | max_drawdown of cumprod(1+sig*ret) | 最大回撤懲罰 |
| Turnover penalty | 0.1 | -turnover*0.5 | mean(|diff(sig)|) / mean(|sig|) | 高周轉率懲罰 |

**反推方法：** 若知 IC 和 reward，可估計 Sharpe+MDD+Turnover 合計 = reward - 0.5*(IC*10)。
若此值為負且絕對值大 → 信號雖有預測力但執行成本（回撤+周轉）吃光超額。

## v6.10 各 Regime 訓練結果摘要

| Regime | Best Formula | Train IC | Val IC | IC Gap | Reward | 評語 |
|--------|-------------|----------|--------|--------|--------|------|
| traditional | TX_INST_NET_OI | 0.096 | **0.113** | -0.017 | 0.320 | 最優，val>train 無 overfit |
| large_cap | ATR | 0.051 | -0.006 | 0.057 | 0.028 | 最差，val_IC 負，overfit 嚴重 |
| mid_cap_tech | ABSORPTION | 0.063 | 0.026 | 0.037 | 0.047 | 中度 overfit，IC 偏低 |
| financial | SP500_CLOSE | 0.086 | 0.052 | 0.034 | 0.249 | 次優，美股連動明確 |

## 22 因子定義速查

| 因子 | 計算公式 | 做多信號方向 |
|------|----------|-------------|
| RET | log(close/close.shift(1)) | 正=動量，負=反轉 |
| LIQ_SCORE | volume / rolling_mean(volume,20) | 高=流動性異常增加 |
| PRESSURE | total_net / volume | 正=法人買超壓力 |
| FOMO | volume.pct_change(5) | 高=量能暴增（追漲） |
| DEV | (close - MA20) / MA20 | 正=偏離均線上方 |
| LOG_VOL | log(volume) | 高=活躍度大 |
| INST_FLOW | rolling_sum(total_net) / volume | 正=法人持續買超 |
| MARGIN_PRESS | margin_balance.pct_change(5) | 高=融資增加（多頭） |
| FIVE_DAY_HIGH | close > high.rolling(5).max() | 1=突破5日高點 |
| VOL_BREAKOUT | volume > MA20*1.5 | 1=量能突破 |
| CVD_PROXY | (c-o)/(h-l+eps)*vol, rolling(20) | 正=買方主導累積 |
| ABSORPTION | (high-close)/(high-low+eps)*volume | 高=大量買盤被吸收（低位承接） |
| SURF_ENTRY | 關鍵價位切入信號 | 1=切入關鍵區 |
| ATR | True Range 14日均值 | 高=波動大 |
| CLOSE_POS | (close-low)/(high-low+eps) | 高=收在高位 |
| MOM_REV | 5日動量反轉信號 | 負→正=反轉做多 |
| TX_INST_NET_OI | 大台法人淨未平倉量 (zscore) | 正=法人偏多 |
| MTX_RETAIL_OI | 小台散戶淨未平倉量 (zscore) | 正=散戶偏多（反向指標） |
| TX_MTX_SPREAD | TX inst - MTX inst | 正=法人與散戶分歧大 |
| NASDAQ_CLOSE | Nasdaq 收盤 (zscore, shift1) | 正=美股偏強 |
| SP500_CLOSE | S&P 500 收盤 (zscore, shift1) | 正=美股偏強 |
| DOWJONES_CLOSE | DowJones 收盤 (zscore, shift1) | 正=美股偏強 |

## 常見問題診斷

| 症狀 | 可能原因 | 改善方向 |
|------|----------|----------|
| 單一 token 公式 | CPU 5000 steps 不足以探索運算子空間 | 增加 steps 或降低 entropy_coef |
| val_IC < 0 | overfit 或因子在此 regime 無效 | 換 regime 專屬權重或加更多數據 |
| reward ≈ 0 | IC 貢獻被 MDD+Turnover 懲罰吃光 | 降低倉位換手率或加 stop-loss |
| adv_std ≈ 0 | Advantage collapse（v6.8 Bug） | 升級至 v6.9+ Rank-Based Advantage |
| 所有 regime 公式雷同 | GRPO exploration 不足 | 提高 gumbel_noise_scale 或 diversity_penalty |
