# 開源專利調研實測報告 v8

**測試日期**: 2026-05-20  
**背景**: Firecrawl 額度用完，需改用純開源方案  
**測試目標**: 找到可靠的開源替代方案，改進 Claim 1 提取率

---

## 測試環境

- **Crawl4AI**: 已安裝（版本快速變化）
- **Playwright**: chromium-1200, chromium-1223
- **browser-use**: `/tmp/mcp-browser-use/`
- **Python**: 3.11+

---

## 測試結果

### v6 版本（Crawl4AI 混合方案）
- **Claim 1 提取率**: 0%
- **實施例提取率**: 33%
- **問題**: `BrowserConfig` 參數兼容性問題

### v7 版本（Crawl4AI 改進版）
- **Claim 1 提取率**: 0%
- **實施例提取率**: 0%
- **問題**: `CrawlerRunConfig` 無 `enable_stealth` 屬性

### v8 版本（Playwright 直接訪問）
- **Claim 1 提取率**: 55.6% (5/9)
- **實施例提取率**: 44% (4/9)
- **總成功率**: 100%
- **結果**: ✅ 成功

---

## 關鍵發現

### 1. Crawl4AI 版本問題
- 參數變化快，API 不穩定
- `enable_stealth` 屬性已移除
- `args` 參數不再支持
- 不建議用於生產環境

### 2. Playwright 直接訪問優勢
- 100% 控制，無中間層
- 真實瀏覽器，處理 JavaScript
- API 穩定，少變動
- 完全免費，無額度限制

### 3. Claim 1 提取策略
- 單一模式：0% 提取率
- 多模式匹配：55.6% 提取率
- 關鍵：支持多種 Claims 格式

---

## 推薦方案

**首選**: Playwright 直接訪問（v8）
- 腳本：`patent_extract_v8_playwright.py`
- 成功率：100%
- Claim 1 提取率：55.6%

**備選**: USPTO API（需申請 Key）
- 優點：官方權威，精確日期控制
- 缺點：需申請 API Key（10-15 分鐘）

**不推薦**: Crawl4AI
- 原因：版本兼容性問題多
- 僅建議：快速原型測試

---

## 相關文件

- 腳本：`scripts/patent_extract_v8_playwright.py`
- 報告：`/tmp/patent_research_opensource_v8.md`
- GRPO 報告：`/tmp/grpo_planning_reflection_v6.md`
