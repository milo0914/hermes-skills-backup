# Strategy + Eng Review 結論 (2026-06-07)

## 執行摘要

對 twstock-alpha-gpt 系統進行完整的 strategy review (CEO 模式) 和 eng review，識別出 5 項架構問題 + 6 項技術問題 + 5 項過擬合問題，已完成修正。

## Strategy Review 問題清單

| # | 問題 | 嚴重度 | 修正方案 | 狀態 |
|---|------|--------|----------|------|
| S1 | AlphaGPT Transformer 模型 vs rule-based 四階段管線架構衝突 | HIGH | 方案 A: GRPO 優先，rule-based 管線作為 reward signal | ✅ |
| S2 | 16維因子詞彙表與 Stage1-3 打分機制重疊（同一指標算兩次） | HIGH | 因子計算結果與篩選管線統一入口 | ✅ |
| S3 | 無過擬合防護（無 OOS 分割、無 walk-forward） | CRITICAL | 新增 anti_overfit.py 五層防護 | ✅ |
| S4 | magic number 閾值未經 out-of-sample 驗證 | HIGH | 所有閾值標注 [UNCALIBRATED] + 可配置化 | ✅ |
| S5 | 回測邏輯過於簡化（無止損出場、無移動止損） | HIGH | TWBacktest v2 加入 ATR 止損/移動止損/時間止損 | ✅ |

## Eng Review 問題清單

| # | 問題 | 修正 | 狀態 |
|---|------|------|------|
| E1 | 因子正規化使用全局 median/MAD = 前視偏差 | rolling window 60天 + expanding fallback | ✅ |
| E2 | TWBacktest 持倉邏輯不符設計（無動態出場） | ATR 止損 + 移動止損 + 時間止損 | ✅ |
| E3 | 所有閾值 hardcoded、無法校準 | DEFAULT_CONFIG 可配置 + [UNCALIBRATED] 標注 | ✅ |
| E4 | Stage3 負分 clip 到 0 掩蓋差異 | 保留原始 score + score_clamped 雙軌 | ✅ |
| E5 | 因子計算與篩選管線獨立運行、數據流不統一 | integrate_with_alpha() 統一入口 | ✅ |
| E6 | composite_score 權重無依據 | 改為可配置 + 標注 [UNCALIBRATED] | ✅ |

## 過擬合問題清單

| # | 問題 | 修正 | 狀態 |
|---|------|------|------|
| O1 | 無 train/val/test 樣本外分割 | anti_overfit.py TimeSeriesSplitter | ✅ |
| O2 | 無 walk-forward 驗證 | anti_overfit.py WalkForwardValidator | ✅ |
| O3 | 無交叉驗證 | anti_overfit.py PurgedKFoldCV (embargo=7d) | ✅ |
| O4 | 夏普比率年化因子錯誤 | sqrt(252/avg_holding_days) | ✅ |
| O5 | 無多重比較校正 | anti_overfit.py OverfitPenalty (IC gap + turnover) | ✅ |

## 邊界情況修正

| 問題 | 修正 | 狀態 |
|------|------|------|
| Stage1-3 min_rows 未檢查 | 各 Stage 增加 min_rows 門檻 | ✅ |
| margin_chg 空序列 IndexError | len(margin_buy) >= 2 保護 | ✅ |
| detect_absorption 無 min_rows 保護 | len(group) < 20 return False | ✅ |
| detect_surf_entry len<2 崩潰 | len(group) < 2 return (False, 0.0) | ✅ |
| TWDataLoader 月份偏移計算錯誤 | total_month 算法修正 | ✅ |
| TWModelConfig 類別變數全局污染 | 改為實例屬性 | ✅ |
| 0050 ETF 不適用個股篩選 | 從 DEFAULT_STOCKS 移除 | ✅ |

## 新增模組

| 模組 | 檔案 | 行數 | 說明 |
|------|------|------|------|
| anti_overfit.py | scripts/anti_overfit.py | ~600 | 五層過擬合防護 |
| grpo_alpha_trainer.py | scripts/grpo_alpha_trainer.py | ~550 | GRPO 因子訓練框架 |

## 選擇方案: A (GRPO 優先)

- GRPO 替代 REINFORCE 作為因子訓練核心
- rule-based 四階段管線保留作為 reward signal 和 baseline
- 過擬合防護嵌入 GRPO 訓練迴圈 (OverfitPenalty 嵌入 reward)
- 所有閾值標注 [UNCALIBRATED]，需經 walk-forward 驗證後才能移除

## 待辦 (post-review)

1. walk-forward 校準所有 [UNCALIBRATED] 閾值
2. 真實營收/事件驅動資料接入 (Stage1 基本面)
3. Kaggle Notebook 部署 GRPO 訓練
4. 端到端回測驗證 (需歷史信號序列)
5. 建立自動化 CI pipeline (anti_overfit audit)
