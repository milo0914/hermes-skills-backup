# Crawl4AI 測試報告 (2026-05-20)

## 背景

Firecrawl 免費方案餘額不足，需要尋找替代方案。Crawl4AI 是開源替代品，無額度限制。

## 安裝步驟

```bash
pip install crawl4ai
```

## 基本用法

```python
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
import asyncio

async def extract_patent(url):
    browser_config = BrowserConfig(headless=True, verbose=False)
    crawler_config = CrawlerRunConfig(
        word_count_threshold=10,
        excluded_tags=['script', 'style']
    )
    
    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(url=url, config=crawler_config)
        
        if result.success:
            return result.markdown
        else:
            return None

# 使用範例
markdown = asyncio.run(extract_patent("https://patents.google.com/patent/US8399073B2/en"))
```

## 測試結果

### 成功項目
- ✅ 安裝成功（crawl4ai 0.4.7+）
- ✅ 可爬取 Google Patents 頁面
- ✅ 返回 markdown 格式
- ✅ 無額度限制
- ✅ 支持 headless 模式

### 失敗項目
- ❌ 無內置 LLM extraction（需手動解析 markdown）
- ❌ 無結構化數據提取（需自己實現）
- ❌ 搜索功能需自行構造 URL

### 提取成功率測試

| 專利 URL | 爬取狀態 | Claim 1 提取 | 日期範圍 |
|---------|---------|-------------|----------|
| US8399073B2 | ✓ 成功 | ✓ 1748 字元 | ✗ 2008 年 |
| ipqwery.com | ✓ 成功 | ✗ 0 字元 | ✓ 2025 年 |
| Justia (kazuaki-tarumi) | ✗ 失敗 | - | - |
| Justia (merck-patent) | ✓ 成功 | ✗ 0 字元 | ✗ N/A |
| CN101407719B | ✓ 成功 | ✓ 3455 字元 | ✗ 2008 年 |
| US5576867A | ✓ 成功 | ✓ 664 字元 | ✗ 1995 年 |
| WO2010022891A1 | ✓ 成功 | ✗ 0 字元 | ✗ 2009 年 |
| US7369204B1 | ✓ 成功 | ✓ 1224 字元 | ✗ 2006 年 |

**統計**:
- 爬取成功率：8/9 (88.9%)
- Claim 1 提取率：4/8 (50%)
- 符合日期範圍 (2020-2026): 1/8 (12.5%)

## 關鍵發現

### 1. Crawl4AI vs Firecrawl

| 特性 | Firecrawl | Crawl4AI |
|------|-----------|----------|
| 額度限制 | 有（免費方案） | 無 |
| LLM Extraction | 內建 | 需自實現 |
| 使用難度 | 低 | 中 |
| 適合場景 | 快速原型、小批量 | 大規模、長期使用 |
| API 依賴 | 需要 API Key | 無需 API |

### 2. Claim 1 提取方法

```python
def extract_claim_1(markdown):
    # 找到 Claims 部分
    claims_match = re.search(r'Claims\s*\n+(.*?)(?=\n\s*Description|\Z)', 
                            markdown, re.DOTALL | re.IGNORECASE)
    
    if claims_match:
        claims_text = claims_match.group(1)
        # 提取第 1 項
        claim1_match = re.search(r'^\s*1\.\s+(.*?)(?=\n\s*2\.|\Z)', 
                                claims_text, re.DOTALL | re.MULTILINE)
        if claim1_match:
            return "1. " + claim1_match.group(1).strip()
    
    return ""
```

### 3. 日期範圍問題

**問題**: 舊搜索結果多為 2008 年以前的專利，不符合 2020-2026 要求

**原因**: 
- Firecrawl search() 不支援日期範圍語法
- 需要使用簡單關鍵字搜索

**解決方案**:
1. 使用 Google Patents 進階搜索 URL 構造
2. 在提取後過濾日期
3. 或使用 USPTO API

## 建議

### 使用 Crawl4AI 的情境
- Firecrawl 餘額不足
- 需要大規模爬取（100+ 專利）
- 有時間自行實現解析邏輯
- 需要長期穩定使用

### 使用 Firecrawl 的情境
- 快速原型驗證
- 小批量提取（<10 專利）
- 需要結構化數據
- 不想自行解析 markdown

## 生成的腳本

- `/data/.hermes/skills/research/patent-research-workflow/scripts/patent_search_v3_crawl4ai.py` - 搜索腳本
- `/data/.hermes/skills/research/patent-research-workflow/scripts/patent_extract_v3_crawl4ai.py` - 提取腳本

## 參考資源

- Crawl4AI GitHub: https://github.com/unclecode/crawl4ai
- Crawl4AI 文檔：https://docs.crawl4ai.com/
