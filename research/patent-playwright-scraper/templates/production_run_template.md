# v{VERSION} Production Run: {COMPANY} {TECHNOLOGY} Patents ({YEAR_RANGE})

**日期**: {DATE}
**目標**: 搜尋 {COMPANY} {TECHNOLOGY} 專利（{YEAR_RANGE}），至少 {MIN_COUNT} 篇
**工具**: patent-playwright-scraper v{VERSION} (Python Playwright + JS DOM)
**結果**: {FINAL_COUNT}/{MIN_COUNT} 達標，全部驗證通過

---

## 搜索策略演進

### 第一輪搜索（{成功/失敗} — {策略描述}）

```
URL: {GOOGLE_PATENTS_URL}
結果: {RESULT_COUNT} 篇（{相關/不相關}）
提取: {EXTRACTED_COUNT} 篇 → {RELEVANT_COUNT} 篇{技術領域}相關
```

**教訓**: {關鍵教訓}

### 後續搜索輪次

```
第 2 輪: {搜索語法} → {結果}
第 3 輪: {搜索語法} → {結果}
第 N 輪: {搜索語法} → {結果}
```

### Assignee 別名覆蓋

```
ASSIGNEE_ALIASES: [{別名1}, {別名2}, ..., {別名8}]
覆蓋率: {N}/{N} 別名有結果 → {TOTAL_IDS} 個不重複專利號
```

**注意**: 必須使用 `assignee:` 語法搜索（關鍵字搜索返回 90%+ 無關結果）。擴展至 8 個別名以覆蓋子公司（如 Merck Electronics KGaA 等）。

### 搜索 URL 語法

```
after=priority:YYYYMMDD  — 優先權日期過濾（有效）
filing_date=YYYYMMDD    — 申請日期過濾（無效，Google Patents 不嚴格執行）
```

**教訓**: 使用 `after=priority:` 替代 `filing_date=`，但仍需提取後驗證日期。

## 搜索結果頁 DOM 日期提取

```
JS_EXTRACT_SEARCH_DATES 提取: {DOM_DATE_COUNT} 筆
 - 含 filing_date: {N} 筆
 - 含 priority_date: {N} 筆
 - 含 publication_date: {N} 筆
 - 用於日期預過濾: {N} 篇被排除（不在 {YEAR_RANGE}）
 - 日期回寫到提取結果: {N} 篇（date_source=search_page_dom）
```

**日期來源追蹤**:
- `search_page_dom`: 提取頁無日期，從搜索頁 DOM 補充
- `extract_page_primary`: 提取頁有日期，搜索頁日期僅合併補充
- `extract`: 僅從提取頁獲得日期（無搜索頁映射）

**注意**: 搜索頁 DOM 日期不完整，需在詳情頁補充驗證。

## Description 分段策略

```
三層回退:
1. 標題行匹配（行首錨定 + 限前 50K chars）
2. 啟發式分段（過渡段特徵詞如 "invention is based on the object of"）
3. 段落號回退（[0021] 等）

inner_text fallback: 當 querySelector 返回文字 <200 chars 時，改用 page.inner_text('body')
```

**Merck 液晶專利特點**: 常見無標題行格式，需啟發式分段識別 Background/Summary/Prior Art。

## 批次提取統計

```
BATCH_SIZE: {9}（每批 ≤9 篇，避免超時）
批次間暫停: 10 秒
```

| 批次 | 輸入 | 成功 | Claim1 | 申請日 | 公開日 | 實施例 | neg DA | 日期來源 |
|------|------|------|--------|--------|--------|--------|--------|----------|
| 第1批 | {N} | {N}/{N} | {%} | {%} | {%} | {%} | {%} | {search/extract} |
| **合計** | **{N}** | **{N}/{N}** | **{%}** | **{%}** | **{%}** | **{%}** | **{%}** | — |

**neg DA 判定**: neg_count >= 1 且 (neg_count > pos_count 或 pos_count == 0)，VA mode 交叉驗證

## LLM 技術要點生成

### 雙段式架構（v1.2.4+）

**段 1（E2E 腳本自動）**: 生成 prompt → 寫入 `reports/tech_feature_prompts_batch.json`
**段 2（Hermes Agent 接手）**: 讀取 prompt → 生成 5 維度摘要 → 寫入 `reports/tech_features_<PATENT_ID>.json`
**回填**: E2E 再次執行時自動檢測回填檔案，存在則載入 `p['tech_features']`

```
後端: hermes_agent（Hermes Agent 直接生成，無需 API key）
獨立進程提取: {N}/{N} 篇成功（sync_playwright asyncio 衝突時 fallback）
Prompt 生成: {N}/{N} 篇 → 保存至 tech_feature_prompts_batch.json
LLM 生成: {N}/{N} 篇 → 保存至 tech_features_<PATENT_ID>.json
5 維度摘要: {N}/{N} 篇（解決的問題/核心發明/關鍵技術特徵/實施方式/與先前技術差異）
Pending: {N} 篇待 Hermes Agent 接手
```

**分段策略分布**:

| 分段策略 | 適用篇數 | 代表專利 |
|----------|----------|----------|
| 標題行匹配 | {N} | {PATENT_ID} |
| 啟發式分段（過渡段） | {N} | {PATENT_ID} |
| 段落號回退 | {N} | {PATENT_ID} |

**Fallback 機制**: 獨立進程 `extract_patent_sections()` 失敗時，從已有提取數據（abstract/claim1/claim2/tech_summary）組裝 LLM prompt，跳過段落提取步驟。

**注意**: 技術要點由 LLM 綜合判讀多段落生成，未提取到的段落標註 `[未提取到 N 段落，無法判斷]`，嚴禁編造。

## 最終專利清單（{YEAR_RANGE} + {技術領域}相關）

| # | 專利號 | 申請日 | 標題 | Claim1 字元 | DA 類型 | 日期來源 | 技術要點 |
|---|--------|--------|------|-----------|---------|----------|----------|
| 1 | {PATENT_ID} | {DATE} | {TITLE} | {LEN} | {neg/neg_va/unconfirmed} | {search_page_dom/extract_page_primary/extract} | {有/無} |

## 驗證結果

### 原始提取（{TOTAL} 篇）
- 提取成功率: {N}/{N} ({%})
- Claim 1 提取率: {N}/{N} ({%})
- 申請日提取率: {N}/{N} ({%})
- 公開日提取率: {N}/{N} ({%})
- 實施例提取率: {N}/{N} ({%})
- 日期來源分布: search_page_dom={N}, extract_page_primary={N}, extract={N}

### 最終集（{N} 篇，經日期+相關性過濾）
- 日期範圍: {N}/{N} 在 {YEAR_RANGE} 內
- Claim 1: {N}/{N} ({%})
- 實施例: {N}/{N} ({%})
- 技術要點: {N}/{N} ({%}) — 5 維度 LLM 摘要
- LLM 生成回填: {N}/{N}（Hermes Agent → tech_features_<PID>.json → 自動回填）
- 段落獨立提取: {N}/{N}（Background/Summary/Claim1/Claim2/Examples）
- Prompt pending: {N} 篇待 Hermes Agent 接手
- 過濾率: {TOTAL}→{FINAL}（{%} 被過濾）

## 關鍵教訓

1. {教訓1}
2. {教訓2}
3. 搜索必須用 `assignee:` 語法，擴展至 8 個別名覆蓋子公司
4. 使用 `after=priority:` 替代無效的 `filing_date=` URL 參數
5. 批量提取每批 ≤9 篇，批次間暫停 10 秒避免超時
6. 無標題行 Merck 專利需啟發式分段，`inner_text('body')` 作為 fallback
7. 日期需雙源驗證：搜索頁 DOM + 詳情頁提取，追蹤 `date_source`
8. LLM 技術要點生成：使用 `tech_feature_generator` 獨立進程提取段落，5 維度摘要優於正則匹配
9. 獨立進程 fallback：sync_playwright asyncio 衝突時，從已有數據組裝 prompt 跳過段落提取
10. 技術要點嚴禁編造：未提取到的段落標註 `[未提取到 N 段落，無法判斷]`

## GitHub 推送

```
推送方式: {GITHUB_TOKEN|token-embedded URL}
壓縮檔: {TIMESTAMP}_report.tar.gz
Repo: {GITHUB_REPO}
分支: {BRANCH}
狀態: {成功/失敗} — {SHA或錯誤訊息}
```

**認證繞行**: 若 GITHUB_TOKEN 環境變數不可見，從既有 repo 的 remote URL 取得含 token 的 URL 直接 push origin。

## 輸出檔案

- Markdown 報告: `{REPORT_PATH}`
- 原始 JSON: `{JSON_PATH}`
- GitHub 壓縮檔: `{TAR_GZ_PATH}`
