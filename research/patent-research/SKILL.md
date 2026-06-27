---
name: patent-research
description: 專利調研自動化 - 使用 browser-use、Playwright、Crawl4AI 進行專利數據爬取和分析
author: user
version: 1.0.0
created: 2026-05-12
tags:
  - patent
  - research
  - web-scraping
  - browser-automation
  - data-analysis
---

# Patent Research Skill

專利調研技能 - 使用自動化瀏覽器工具進行專利數據爬取和分析

> **注意**: 此技能已被 `patent-playwright-scraper` 大幅超越和涵蓋。後者包含 30 個實戰陷阱、完整的 EP 專利 DOM 提取策略、Claim1 品質驗證、多來源合併、報告 v4 生成等進階功能。**新任務應優先載入 `patent-playwright-scraper`**，此技能僅保留作為基礎參考。

## Trigger Conditions
- 用戶需要搜索特定公司、技術領域或關鍵詞的專利
- 需要從 Google Patents、Justia、WIPO、Espacenet 等數據庫獲取專利信息
- 需要批量爬取多個專利並生成分析報告
- 需要將專利數據轉換為結構化格式（JSON/Markdown/HTML）

## Required Tools
- **browser-use** + Playwright: 處理需要 JavaScript 渲染的專利數據庫
- **Crawl4AI**: 高性能網頁爬取，支持異步和 AI 內容分析
- **Playwright**: 瀏覽器自動化，處理複雜交互
- **Firecrawl API**: 可選，用於快速爬取（API key: fc-3303155c75a945d994363256606281d2）

## Installation Requirements

### 1. 安裝基礎包
```bash
# Crawl4AI
pip install crawl4ai

# Playwright + 瀏覽器
pip install playwright
python3 -m playwright install chromium

# browser-use
pip install browser-use

# uv (用於 MCP 服務器)
pip install uv
```

### 2. 安裝 browser-use MCP 服務器
```bash
export PATH="$HOME/.local/bin:$PATH"
cd /tmp
git clone https://github.com/Saik0s/mcp-browser-use.git
cd mcp-browser-use
uv sync
```

### 3. 驗證安裝
```python
# 檢查所有包
import crawl4ai
import playwright
import browser_use
print("所有工具已安裝")
```

## Workflow Steps

### Phase 1: 需求分析
1. 確認目標公司/技術領域/關鍵詞
2. 確定目標專利數據庫（Google Patents, Justia, WIPO, Espacenet）
3. 確認需要的字段：專利號、標題、摘要、申請日期、授權日期、權利要求等

### Phase 2: 數據爬取
1. 選擇合適的爬取策略：
   - 簡單頁面：使用 Crawl4AI 快速爬取
   - 需要 JavaScript 渲染：使用 Playwright 或 browser-use
   - 批量爬取：使用 Firecrawl API

2. 爬取示例（使用 browser-use）：
```python
from browser_use import Agent
from playwright.sync_api import sync_playwright

def search_patents(query, database='google'):
    agent = Agent(
        task=f"Search for patents matching '{query}' in {database} patents database",
        tools=['browser']
    )
    result = agent.run()
    return result
```

### Phase 3: 數據處理
1. 清洗數據：去除無關結果，提取結構化字段
2. 去重：使用專利號去重
3. 分類：根據技術領域或關鍵詞分類

### Phase 4: 報告生成
1. 生成 Markdown 報告（包含摘要、關鍵發現、專利列表）
2. 生成 HTML 報告（可視化展示）
3. 保存原始 JSON 數據

## Output Templates

### JSON 結構
```json
{
  "search_query": "negative dielectric constant polyimide",
  "company": "Merck",
  "total_found": 7,
  "patents": [
    {
      "patent_number": "US12618007",
      "title": "...",
      "abstract": "...",
      "filing_date": "2023-01-15",
      "grant_date": "2024-06-18",
      "assignee": "Merck KGaA",
      "inventors": ["..."],
      "claims_count": 15,
      "url": "..."
    }
  ]
}
```

### Markdown 報告結構
```markdown
# [公司/技術] 專利分析報告

## 執行摘要
- 總專利數：X
- 時間範圍：YYYY-MM-DD 至 YYYY-MM-DD
- 關鍵技術領域：...

## 核心專利列表
| 專利號 | 標題 | 申請日期 | 權利要求數 |
|--------|------|----------|------------|
| ... | ... | ... | ... |

## 技術趨勢分析
...

## 附錄：原始數據
...
```

## Pitfalls & Solutions

### 1. 反爬蟲機制
- **問題**: Google Patents 等網站有反爬蟲機制
- **解決**: 使用 browser-use 模擬真實用戶行為，添加延遲

### 2. JavaScript 渲染
- **問題**: 簡單 HTTP 請求無法獲取動態加載內容
- **解決**: 必須使用 Playwright 或 browser-use 等瀏覽器自動化工具

### 3. 數據結構不一致
- **問題**: 不同專利數據庫的字段格式不同
- **解決**: 建立統一的數據模型，爬取後進行標準化轉換

### 4. 批量爬取超時
- **問題**: 大量爬取時容易觸發限流
- **解決**: 
 - 添加隨機延遲（2-5 秒）
 - 使用異步爬取（Crawl4AI）
 - 分批處理，保存中間結果

### 5. API Key 管理
- **問題**: Firecrawl 等 API 需要鑰匙
- **解決**: 使用環境變量，不要硬編碼到代碼中

### 6. Claim 1 抓取失敗（2026-05-12 實戰經驗）
- **問題**: Justia Patents 的 HTML 結構特殊，`.claims .claim` 選擇器無效，抓到的常是描述段落而非正式請求項
- **徵兆**: 抓到的 "Claim 1" 開頭是 "However, these compositions..." 或 "In addition to..." 等描述性文字
- **解決方案**:
  1. 使用文本正則匹配替代 CSS 選擇器：
     ```python
     import re
     content = page.inner_text('body')
     # 查找 "What is claimed is" 後的內容
     claim1_match = re.search(r'What is claimed is:(.*?)(?:\n\n|2\.|\Z)', content, re.DOTALL)
     if claim1_match:
         claim1 = claim1_match.group(1).strip()
     else:
         # 嘗試直接匹配 "1." 開頭
         claim1_match = re.search(r'1\.\s+(.*?)(?:\n\n|2\.|\Z)', content, re.DOTALL)
     ```
  2. 若 Justia 失敗，改用 Google Patents 交叉驗證
  3. **關鍵**: 不要依賴單一來源，建議同時爬取 Justia + Google Patents 互補

### 7. Justia 超時問題
- **問題**: 部分專利頁面（如 12618008, 12595417）使用 `wait_until='networkidle'` 會超時 60 秒
- **徵兆**: `Page.goto: Timeout 60000ms exceeded`
- **解決方案**:
  1. 改用 `wait_until='domcontentloaded'` 並手動等待關鍵元素
  2. 添加 `page.wait_for_timeout(8000)` 等待 JavaScript 渲染
  3. 若仍失敗，切換到 Google Patents 數據源
  ```python
  page.goto(url, wait_until='domcontentloaded', timeout=60000)
  page.wait_for_selector('.content, .description, .claims', timeout=10000)
  page.wait_for_timeout(8000)  # 等待 JS 渲染
  ```

### 8. Google Patents 選擇器失效
- **問題**: Google Patents 的 `h1 span`, `div[data-section="abstract"]` 等選擇器無法抓取內容
- **原因**: 頁面使用 Shadow DOM 或動態加載，需要等待更長時間
- **解決方案**:
  1. 使用 `page.wait_for_timeout(5000)` 延長等待
  2. 嘗試備用選擇器：`div.claw-note p` (claims), `section[data-section="claims"]`
  3. 若仍失敗，回退到 Justia 或使用 Firecrawl API

### 9. 實施例（Examples）抓取策略
- **問題**: 實施例通常很長且分散，直接抓取容易遺漏
- **有效模式**:
  ```python
  # 使用正則匹配 "Example 1:", "EXAMPLE 1.", "Example 1-" 等變體
  example_pattern = r'(?:EXAMPLE|Example)\s+\d+[:\.\-].*?(?=(?:EXAMPLE|Example)\s+\d+[:\.\-]|\Z)'
  example_matches = re.findall(example_pattern, desc_text, re.IGNORECASE | re.DOTALL)
  
  # 限制每個實施例長度，避免超載
  examples = [ex.strip()[:1000] for ex in example_matches[:5]]
  ```
- **實戰發現**: US 12595414 包含 3 個完整實施例（UUQU-4-N, UUZU-4-N 合成），使用此方法成功抓取

### 10. 交叉驗證策略（推薦工作流程）
- **步驟**:
  1. 先從 Justia 批量抓取基本字段（專利號、標題、申請/公告日期）
  2. 對超時失敗的專利，改用 Google Patents 重试
  3. 對 Claim 1，同時從 Justia 和 Google Patents 抓取，比對一致性
  4. 對實施例，優先用 Justia（結構化較好），失敗則用 Google Patents
- **理由**: 單一數據源總有失靈時，交叉驗證提高成功率

## Verification Steps
1. 爬取後立即驗證數據量是否合理（不應為 0 或異常大）
2. 隨機抽查 2-3 個專利，確認字段完整
3. 檢查專利號格式是否正確（如 US12345678）
4. 確認報告中無重複專利

## Example Commands

### 快速爬取 Justia 專利列表
```bash
cd /tmp
python3 -c "
from crawl4ai import AsyncWebCrawler
import asyncio

async def scrape():
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url='https://patents.justia.com/assignee/merck-kgaa')
        print(result.markdown)

asyncio.run(scrape())
"
```

### 使用 browser-use 進行複雜搜索
```bash
cd /tmp/mcp-browser-use
uv run mcp-server-browser-use server
```

然後在對話中：
"使用 browser-use 搜索 Google Patents 上 Merck 公司的 negative dielectric polyimide 專利"

## Resources
- Google Patents: https://patents.google.com/
- Justia Patents: https://patents.justia.com/
- WIPO Patentscope: https://patentscope.wipo.int/
- Espacenet: https://worldwide.espacenet.com/
- Firecrawl API: https://www.firecrawl.dev/
- browser-use GitHub: https://github.com/Saik0s/mcp-browser-use

## Notes
- 優先使用官方數據庫而非第三方聚合網站
- 保存原始 JSON 數據以便後續重新分析
- 報告應包含可追溯的專利 URL
- 對於重要專利，記錄完整的權利要求書
- 考慮使用 USPTO API 或 Google Patents API 進行大規模批量查詢
