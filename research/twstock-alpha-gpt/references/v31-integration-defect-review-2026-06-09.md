# v3.1 整合缺陷清單 — Strategy Review + Eng Review (2026-06-09)

## 摘要

v3.1 擴展（16→22因子, VOCAB 28→34, 期貨OI+美股因子）的簽名更新已完成（17/17 驗證通過），但系統處於「簽名已更新但推論不可用」的半成品狀態。Kaggle kernel v3.2/v3.4/v3.5 全部失敗，無可用訓練權重。

## 🔴 必須修復 (P0/P1)

### D1. grpo_alpha_trainer.py VOCAB_SIZE=28 vs ai_dig_money_core.py VOCAB_SIZE=34
- 位置: grpo_alpha_trainer.py L45, L99-L112
- 影響: Phase2 GRPO 推論維度不匹配，模型 embedding [34,128] 無法載入 [28,128] 架構
- 修復: 同步 trainer FEATURE_NAMES 至 22 個、VOCAB_SIZE=34

### D2. Stage1 市場級評分在 per-stock loop 內重複計算
- 位置: ai_dig_money_core.py L218-237
- 影響: 期貨法人OI和美股動量是全市場訊號，N檔股票=N次冗餘查詢
- 修復: 提取到循環外計算一次

### D3. Phase2 雙重 merge
- 位置: ai_dig_money_core.py L838-860
- 影響: compute_features() 已合併 6 個 v3.1 因子，Phase2 又做一次 merge
- 修復: 移除重複 merge 或檢查欄位是否已存在

### D4. run_daily_scan 缺少 futures_oi_df / us_indices_df 參數
- 位置: ai_dig_money_core.py L1846-1848
- 影響: 外部無法注入預計算資料，單元測試受限
- 修復: 加入參數，內部優先使用傳入值

### D5. TWSEDataFetcher 是空 stub
- 位置: ai_dig_money_core.py L1340-1405
- 影響: 生產環境期貨/美股評分永遠為 0，6 個 v3.1 因子永遠為 0
- 修復: 串接真實資料源

## 🟡 建議修復 (P2)

### D6. 全域 64 處縮排非 4-space 倍數
- 位置: 遍佈 ai_dig_money_core.py
- 主因: patch() tool 腐蝕
- 修復: write_file Python 腳本按行號修正

### D7. feature_df 缺 close 欄位
- 位置: compute_features() 輸出
- 影響: Phase2 GRPO 報酬計算 fallback 到隨機
- 修復: 保留 close 欄位

### D8. Stage1 pass_threshold 鬆弛
- 原因: 新增 30 分空間後 threshold 實際從 41.7% 降至 33.3%
- 修復: 調高 pass_threshold 至 60-65

### D9. Kaggle v3.5 IndentationError
- 位置: notebook L1555, continue not in loop
- 修復: 修正縮排後 re-push

## 🟢 僅供參考 (P3)

### D10. FormulaDecoder 重複定義
- ai_dig_money_core.py 和 grpo_alpha_trainer.py 各有一個

### D11. V2Pipeline.run() docstring 未提及新參數

### D12. compute_features raw→upper 映射邏輯脆弱
- 依賴欄位是否存在，靜默填 0 而非報錯

## 修復優先順序

D1 → D9 → D4/D5 → D2/D3 → D6 → 其餘

## 驗證狀態

- 本地語法: 全部通過 py_compile
- 17 項整合驗證: 17/17 通過
- Kaggle kernel: 全部失敗（v3.2 IndentationError, v3.4/v3.5 無輸出或 IndentationError）
- 端到端測試: 未完成

## 核心風險

D1（VOCAB_SIZE 不匹配）+ D9（Kaggle 訓練失敗）= GRPO Phase2 路徑必然崩潰。Stage1~Stage4 rule-based 路徑可運行（futures_oi/us_indices 皆為 0 fallback），但 GRPO 增強路徑不可用。
