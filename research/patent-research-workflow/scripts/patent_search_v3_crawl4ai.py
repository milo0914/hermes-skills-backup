#!/usr/bin/env python3
"""
Merck KGaA 負介電液晶專利搜索腳本 v3 (Crawl4AI 版本)
使用 Crawl4AI 爬取 Google Patents 搜索結果
無額度限制，解決 Firecrawl 餘額不足問題

策略：
1. 使用簡單關鍵字構造 Google Patents 搜索 URL
2. 用 Crawl4AI 爬取搜索結果頁面
3. 從頁面中提取專利 URL 列表
4. 後續在提取階段過濾日期和提取詳細內容
"""

import asyncio
import json
import re
from datetime import datetime
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

# 搜索參數
SEARCH_CONFIG = {
    "query": "Merck KGaA negative dielectric liquid crystal",
    "cpc": "C09K19/30",  # 負介電各向異性液晶
    "min_date": "2020-01-01",
    "max_date": "2026-12-31",
    "limit": 20  # 最多爬取 20 個結果
}

def construct_google_patents_search_url(config):
    """
    構造 Google Patents 進階搜索 URL
    
    參數：
    - query: 搜索關鍵字
    - cpc: CPC 分類代碼
    - min_date: 最小申請日期
    - max_date: 最大申請日期
    """
    # Google Patents 進階搜索語法
    # filing_date:[start TO end] 或 filing_date:YYYYMMDD
    base_url = "https://patents.google.com/?"
    
    # 構造搜索查詢
    # 注意：Google Patents 的日期語法是 filing_date:YYYYMMDD 或 filing_date:[start TO end]
    date_range = f"filing_date:[{config['min_date'].replace('-', '')} TO {config['max_date'].replace('-', '')}]"
    
    # CPC 分類
    cpc_query = f"cpc:{config['cpc']}"
    
    # 組合查詢
    full_query = f"{config['query']} {cpc_query} {date_range}"
    
    # URL 編碼（簡單版本，實際應該用 urllib.parse.quote）
    encoded_query = full_query.replace(' ', '+')
    
    return f"{base_url}q={encoded_query}"


async def extract_patent_urls_from_page(markdown_text):
    """
    從 Google Patents 搜索結果頁面提取專利 URL
    
    從 markdown 中提取專利連結
    """
    patent_urls = []
    
    # 匹配 Google Patents 連結的模式
    # 例如：https://patents.google.com/patent/US8399073B2/en
    pattern = r'https://patents\.google\.com/patent/[A-Z0-9]+/en'
    
    matches = re.findall(pattern, markdown_text)
    
    # 去重
    seen = set()
    for url in matches:
        if url not in seen:
            seen.add(url)
            patent_urls.append(url)
    
    return patent_urls


async def search_patents(config, max_results=20):
    """
    搜索專利並返回專利 URL 列表
    
    參數：
    - config: 搜索配置
    - max_results: 最多返回的專利數量
    """
    print("=" * 80)
    print(f"Merck KGaA 負介電液晶專利搜索 (v3 - Crawl4AI)")
    print("=" * 80)
    print(f"搜索配置:")
    print(f"  關鍵字：{config['query']}")
    print(f"  CPC 分類：{config['cpc']}")
    print(f"  日期範圍：{config['min_date']} 至 {config['max_date']}")
    print(f"  最多結果：{max_results}")
    print("=" * 80)
    
    # 構造搜索 URL
    search_url = construct_google_patents_search_url(config)
    print(f"\n搜索 URL: {search_url}")
    
    # 配置瀏覽器
    browser_config = BrowserConfig(
        headless=True,
        verbose=False
    )
    
    crawler_config = CrawlerRunConfig(
        word_count_threshold=10,
        excluded_tags=['script', 'style'],
        verbose=False
    )
    
    # 爬取搜索結果頁面
    print(f"\n正在爬取搜索結果...")
    
    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(url=search_url, config=crawler_config)
        
        if not result.success:
            print(f"✗ 搜索失敗：{result.error_message}")
            return []
        
        print(f"✓ 搜索成功")
        
        # 提取專利 URL
        patent_urls = await extract_patent_urls_from_page(result.markdown)
        
        print(f"找到 {len(patent_urls)} 個專利 URL")
        
        # 限制結果數量
        if len(patent_urls) > max_results:
            patent_urls = patent_urls[:max_results]
            print(f"限制為前 {max_results} 個結果")
        
        return patent_urls


async def main():
    """主函數"""
    # 執行搜索
    patent_urls = await search_patents(SEARCH_CONFIG, max_results=SEARCH_CONFIG['limit'])
    
    if not patent_urls:
        print("\n✗ 未找到專利")
        return
    
    # 保存結果
    results = {
        "search_config": SEARCH_CONFIG,
        "search_url": construct_google_patents_search_url(SEARCH_CONFIG),
        "patent_urls": patent_urls,
        "count": len(patent_urls),
        "timestamp": datetime.now().isoformat()
    }
    
    output_file = "/tmp/patent_search_results_v3.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"\n搜索結果已保存：{output_file}")
    print(f"專利數量：{len(patent_urls)}")
    
    # 顯示前 5 個專利 URL
    print(f"\n前 5 個專利 URL:")
    for i, url in enumerate(patent_urls[:5], 1):
        print(f"  {i}. {url}")


if __name__ == "__main__":
    asyncio.run(main())
