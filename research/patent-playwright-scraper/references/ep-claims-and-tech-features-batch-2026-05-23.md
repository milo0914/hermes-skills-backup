# EP Claims DOM 提取 + 批次技術要點生成實戰記錄（2026-05-23）

## 背景

contrast_final_list.json 有 19 篇 Merck 負介電液晶專利，需完成結構化段落提取與技術要點摘要生成。

## EP 專利 Claims 提取問題

### 發現過程

1. 初始 sections 提取品質檢查：19 篇中僅 9 篇 GOOD，7 篇 EP 類專利 Claims 提取失敗
2. 嘗試 inline Playwright 腳本探測 EP 頁面 DOM 結構，發現 `<ol class="claims"><li class="claim">` 格式
3. 正則 `r'1\.\s+([\s\S]{10,2000}?)(?:\n2\.|Claims)'` 對 EP 專利完全無效
4. 改用 `page.evaluate()` 從 DOM 提取 → 7/7 EP 專利 Claim1 全部成功

### 提取結果

| 專利 | claim1 (舊) | claim1 (新) |
|------|------------|------------|
| EP4400561A1 | 0 chars | 1511 chars |
| EP4702104A1 | 0 chars | 2000 chars |
| EP4720219A1 | 0 chars | 1685 chars |
| EP4502108A1 | 0 chars | 1584 chars |
| EP4538349A1 | 0 chars | 2000 chars |
| EP4563675 | 0 chars | 935 chars |
| EP4733370A1 | 0 chars | 2000 chars |

## Sections 品質補充策略

### supplement_and_build_prompts.py 邏輯

1. 讀取 sections_*.json（每篇專利一個檔案）
2. 讀取 contrast_final_list.json（已有 claim1/abstract 數據）
3. 按專利號匹配，取較長的 claim1/abstract 值覆蓋
4. 組裝 LLM prompt（5 維度 + 正反範例 + 品質要求）
5. 寫回 sections JSON

### 品質提升

- 補充前：9 GOOD, 7 PARTIAL, 3 POOR
- 補充後：17 GOOD, 2 PARTIAL, 0 POOR

## 批次技術要點生成

### delegate_task 分批策略

19 篇專利分 7 批次（每批最多 3 個並行子代理）：

| 批次 | 專利 | 子代理數 |
|------|------|---------|
| 1 | EP4400561A1, EP4502108A1, US20250136868A1 | 3 |
| 2-1 | US20250101305A1, EP4538349A1, US20250154412A1 | 3 |
| 2-2 | EP4563675, US20250189829A1, US12595417B2 | 3 |
| 3-1 | US12612551B2, US20250197723A1, US20250223496A1 | 3 |
| 3-2 | US20250277152A1, US20250284151A1, US20250297161A1 | 3 |
| 4-1 | US20250361444A1, EP4702104A1, EP4720219A1 | 3 |
| 4-2 | EP4733370A1 | 1 |

### 子代理 prompt 關鍵要素

1. 角色設定：「你是專利分析師」
2. 品質要求：正反範例（流水線式 ❌ vs 判斷性洞見 ✅）
3. 5 維度定義 + 每維度 ≥30 字 + 總長 ≥150 字
4. 繁體中文 + 專利分析師語氣
5. 未提取段落標註 `[未提取到N段落，無法判斷]`
6. 讀取 JSON prompt → 寫入 .txt 檔案路徑

### 結果合併流程

1. 子代理寫入 /home/appuser/{PID}_technical_summary.txt
2. 主 Agent 讀取 .txt → 保存到 reports/tech_features_{PID}.json
3. 合併 19 篇到 contrast_final_list.json，設置 tech_features_status: 'generated'
4. 生成 Markdown 報告 (88KB, 312 行)
5. 推送 GitHub commit a4f12ea

### 技術要點字數統計

- 最短：1,300 chars
- 最長：2,043 chars
- 全部 ≥150 字門檻 ✅

## 腳本清單

| 腳本 | 用途 |
|------|------|
| scripts/_extract_ep_claims.py | 單篇 EP Claims DOM 提取（獨立進程） |
| scripts/extract_ep_claims_batch.py | EP Claims 批次調度 |
| scripts/supplement_and_build_prompts.py | 合併已有數據 + 組裝 LLM prompt |
| scripts/_extract_single_patent.py | 單篇專利通用提取（獨立進程） |
| scripts/reextract_ep_claims.py | EP Claims 重提取（初版，後被 batch 版替代） |

## 教訓

1. **EP 專利必須用 DOM 策略提取 Claims** — 正則對 EP 格式完全無效
2. **supplement 策略大幅提升品質** — 利用已有數據比重新提取更高效
3. **delegate_task 分批是批量 LLM 生成的高效模式** — 每批 3 個並行，7 批處理 19 篇
4. **子代理結果需主動收集** — 寫入 .txt 路徑後主 Agent 需手動讀取合併
5. **PARTIAL 專利仍可生成技術要點** — 缺少 background/summary 時標註並從其他段落推導
