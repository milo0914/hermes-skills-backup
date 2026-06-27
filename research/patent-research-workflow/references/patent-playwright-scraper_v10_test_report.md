# v10 測試報告與 LLM 集成指南

## 測試概要

**測試時間**: 2026-05-20  
**測試樣本**: 9 個專利 URL（Google Patents 6 個，Justia 3 個）  
**測試環境**: Playwright + BeautifulSoup4 + Crawl4AI

## 測試結果摘要

| 版本 | Claim 1 提取率 | 實施例提取率 | 日期提取率 | 專利號提取率 | 總成功率 |
|------|--------------|------------|-----------|------------|---------|
| v8 | 55.6% (5/9) | 44% (4/9) | 0% (0/9) | 77.8% (7/9) | 100% |
| v9 | 66.7% (6/9) | 33.3% (3/9) | 22.2% (2/9) | 77.8% (7/9) | 100% |
| v10-A | 66.7% (6/9) | 33.3% (3/9) | 0% (0/9) | 77.8% (7/9) | 100% |

## 關鍵發現

### 1. Justia 反爬機制（3/9 失敗）
- **現象**: 返回 "Just a moment..." 頁面
- **影響**: Claim 1、實施例、日期全部失敗
- **解決方案**:
  - 方案 B：真實 User-Agent + 隨機延遲（1-3 秒）
  - 方案 C：使用 USPTO API 替代
  - 方案 D：browser-use MCP 真實瀏覽器

### 2. 日期提取失效
- **v9**: 22.2% 成功率（來自 ipqwery）
- **v10-A**: 0%（Google Patents meta 標籤不存在）
- **建議**: 使用 USPTO API 或 BigQuery

### 3. Claim 1 長度控制
- **v9**: 無上限，可能提取過長文本（29888 字元）
- **v10-A**: 限制 10000 字元，避免冗長
- **影響**: 改善可讀性，但可能遺失信息

### 4. 專利號格式問題
- **v9**: 正確格式 `US8399073B`
- **v10-A**: 錯誤格式 `US:8399073`（JSON-LD 解析問題）
- **建議**: 回退到 URL 提取

## LLM 集成方案

### 推薦：混合式方案（v10-C）

**架構**:
```
正則提取（100% 案例，免費）
    ↓
置信度評估（長度、關鍵詞、格式）
    ↓
高置信度 (>0.7) → 直接輸出
    ↓
低置信度 (<0.7) → LLM 驗證修正
    ↓
最終結果
```

**成本估算**:
- 80% 案例：正則處理（$0）
- 20% 案例：LLM 驗證（~$0.02/個）
- 100 個專利總成本：~$0.40-0.80

**預期效果**:
- Claim 1 提取率：66.7% → 85%+
- 實施例提取率：33.3% → 60%+
- 日期提取率：0% → 70%+（需 USPTO API）

### 實作建議

1. **第一階段**: 優化正則 + 置信度評估（免費）
2. **第二階段**: 集成 LLM 驗證（低成本）
3. **第三階段**: USPTO API 集成（權威數據源）

## 測試腳本

- `patent_extract_v9_full.py` - v9 完整版
- `patent_extract_v10a_structured.py` - v10-A 結構化版
- `patent_extract_v10c_hybrid.py` - v10-C 混合版（待創建）
- `test_claim1_patterns.py` - 正則模式測試

## 參考鏈接

- [USPTO API 文檔](https://www.uspto.gov/learning-and-resources/open-data-and-mobility/uspto-api-documentation)
- [Google Patents BigQuery](https://cloud.google.com/bigquery/public-data/patents)
- [Browser-use MCP](https://github.com/browser-use/browser-use)
- [LangChain Playwright](https://python.langchain.com/docs/integrations/providers/playwright)
