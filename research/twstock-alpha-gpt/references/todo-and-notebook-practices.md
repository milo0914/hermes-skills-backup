# AI Dig Money 系統 - TODO 與 Notebook 實務慣例

## TODO 結構結構

用戶使用結構化的 TODO 系統來追蹤 AI Dig Money 專案進度，組織為四個主要管道：

### 1. data_pipe (資料管線)
- 資料抓取與預處理
- 包含 OHLCV, 期貨, 美股指數, 法人, 融資融券等
- 典型任務：TX futures retail_net_oi 修復、擴展股票數據期間、us_indices 日期對齊、驗證機構資料完整性

### 2. filter_pipe (篩選管線)
- Marcus 三重過濾 + Wenty 量價 篩選
- 實施 Marcus 三重過濾 (流動性、資金面、基本面)
- 實施 Wenty 量價策略

### 3. grpo_training_pipe (GRPO 訓練管線)
- GRPO 訓練流程，包括特徵工程、獎勵計算、策略更新
- 典型任務：RegimeConfig.feature_weights 更新、訓練參數修改 (GPU 支援)、深度思考提高 best reward

### 4. report_pipe (報告管線)
- 報告生成與發布，包括 Kaggle Dataset 推送、Notebook 更新、績效報告
- 典型任務：推送 Kaggle Dataset、更新 Kaggle Notebook 引用、生成訓練結果摘報告

每個管道包含：
- description: 管線描述
- status: in_progress/pending/completed
- tasks: 任務列表，每個任務有 id, description, status, files (如果適用)

## Notebook 更新慣例

### 版本號管理
1. 檔名中版本號： twstock-grpo-regime-aware-factor-training-v6-10.ipynb
2. notebook metadata 中 title: "TWStock GRPO Regime-Aware Factor Training v6.10 (Fix stock_id type + Multi-Obj)"
3.  notebook 開頭的 markdown 標題: "# GRPO Regime-Aware Factor Training v6.10"
4.  版本修復說明區塊: "**v6.10 關鍵修復:**"
5.  所有印訊中版本號: 例如 "台股 GRPO Regime-Aware 因子訓練 (Kaggle GPU) - v6.10 Rank-Based Advantage + Multi-Objective Reward + Regime Fix"

### GPU 相容性檢查
為了支援較舊的 GPU (如 T4, P100)，將 CUDA capability 檢查從 sm_70 調整為 sm_60：
```python
if cc[0] >= 6:  # 而不是原本的 >= 7
    gpu_compatible = True
    print(f"  GPU 相容: sm_{cc[0]}{cc[1]} >= sm_60 ✓")
else:
    print(f"  GPU 不相容: sm_{cc[0]}{cc[1]} < sm_60，將使用 CPU fallback")
```

### 訓練模式說明
- GPU 模式：訓練所有 regime
- CPU 模式：訓練所有 4 個 regime (縮小規模，不再只訓練 MID_CAP_TECH)
- 所有印訊中應反映當前版本號 (v6.10)

## TODO 維護與看板管理

為了有效追蹤專案進度，維護 `references/ai_dig_money_todo.json` 檔案時應遵循以下最佳實踒：

### 定期更新流程
1. **時間戳**：每次修改後更新 `last_updated` 欄位為當前時間（ISO 8601 格式）
2. **任務狀態**：完成任務時將 `status` 從 `pending` 改為 `completed`
3. **進度重算**：修改後重新計算：
   - `completed_tasks`：所有管道中 status 為 completed 的任務總數
   - `total_tasks`：所有任務總數
   - `percentage`：`(completed_tasks / total_tasks) * 100`，四捨五入至整數
4. **下一步調整**：根據目前狀態更新 `next_steps` 陣列：
   - 優先處理被阻礙的 pending 任務（如待前置任務完成）
   - 就緒時啟動下一個管道的初始任務
   - 為即將開始的工作準備相應事項

### 技術改進追蹤
在 `grpo_training_pipe` 中，可依實作難度與影響劃分任務：
- **短期 (1-2週)**：可快速驗證的改進，如：
  * 在 GRPORewardCalculator 中添勝orized IC 計算選項（限制第5-95百分位）
  * 實施 Sortino ratio 作為 Sharpe 的替代選項（關注下偏風險）
  * 調整多樣性懲罰參數（如將閾值從 0.9 降至 0.85 並增加係數）
  * 在訓練日誌中顯示各 reward 組件的具體貢獻度
- **中期 (3-4週)**：需要較多測試和調整的改進
- **長期 (2月+)**：結構性變更或需要重大架構改動的改進

### Kaggle 推送驗證
在推送 notebook 至 Kaggle 之前，應該：
1. 確認 `kernel-metadata.json` 中的 `dataset_sources` 完全匹配用戶實際擁有的 dataset slug
2. 透過 `kaggle datasets list --user <username>` 驗證 dataset 存在且可存取
3. 檢查 notebook 是否包含必要的 GPU 相容性檢查（如 `torch.cuda.is_available()` 與實際 tensor 創建測試）
4. 確認所有必要的檔案（notebook + metadata）都在推送目錄中

## 續接 (Continuation) 期望

當收到已完成任務時，用戶期望「續接」：
1. 讀取看板已完成任務
2. 增加新目標
3. 接續執行（下載+推送Kaggle+重新執行+差異分析）

這意味著：
- 完成的任務應該明確標記為 completed
- 新目標應該被加入適當的管道和任務列表
- 系統應該支援從上次中斷點恢復執行
- 應該能夠比較修改前後的差異