#!/usr/bin/env python3
"""
Merck KGaA 負介電液晶專利搜索 (v4 - 進階 URL + Crawl4AI)

改進重點:
1. 使用 Google Patents 進階搜索 URL 構造
2. 包含 CPC 分類和日期範圍
3. 使用 Crawl4AI 爬取搜索結果頁面
4. 提取專利 URL 列表

關鍵字：Merck KGaA, negative dielectric, liquid crystal, C09K19/30
日期範圍：2020-01-01 至 2026-12-31
"""

import asyncio
import json
import re
from datetime import datetime
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

# 搜索配置 - 改用簡單關鍵字，在提取後過濾日期
SEARCH_CONFIGS = [
    {
        "name": "基本搜索",
        "query": "Merck KGaA negative dielectric liquid crystal",
    },
    {
        "name": "CPC 分類",
        "query": "cpc:C09K19/30 Merck KGaA",
    },
    {
        "name": "公司 + 技術",
        "query": "assignee:Merck KGaA negative dielectric",
    },
    {
        "name": "技術關鍵字",
        "query": "negative dielectric anisotropy liquid crystal",
    },
]

def construct_search_url(query):
    """構造 Google Patents 搜索 URL"""
    from urllib.parse import quote_plus
    base_url = "https://patents.google.com/"
    return f"{base_url}?q={quote_plus(query)}"

async def crawl_search_results(url):
    """使用 Crawl4AI 爬取搜索結果頁面"""
    browser_config = BrowserConfig(headless=True, verbose=False)
    crawler_config = CrawlerRunConfig(
        word_count_threshold=1,
        remove_overlay_elements=True,
    )
    
    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(url=url, config=crawler_config)
        
        if result.success:
            return result.markdown
        else:
            print(f"✗ 爬取失敗：{result.error_message}")
            return None

def extract_patent_urls_from_markdown(markdown):
    """從 markdown 中提取專利 URL"""
    if not markdown:
        return []
    
    # 匹配 Google Patents URL
    # 格式：https://patents.google.com/patent/US8399073B2/en
    pattern = r'https://patents\.google\.com/patent/[A-Za-z0-9]+/[A-Za-z0-9]+'
    
    urls = re.findall(pattern, markdown)
    
    # 去重
    unique_urls = list(dict.fromkeys(urls))
    
    return unique_urls

def extract_patent_info_from_markdown(markdown):
    """從 markdown 中提取專利基本信息（標題、申請日期等）"""
    if not markdown:
        return {}
    
    info = {}
    
    # 提取專利號（從標題行）
    title_match = re.search(r'^#\s+(.*?)(?:\s+-\s+Google Patents)?$', markdown, re.MULTILINE | re.IGNORECASE)
    if title_match:
        info['title'] = title_match.group(1).strip()
    
    # 提取申請日期
    # 格式：Filing date: Dec 22, 2008
    filing_match = re.search(r'Filing date[:\s]+([A-Za-z0-9,]+)', markdown, re.IGNORECASE)
    if filing_match:
        info['filing_date_raw'] = filing_match.group(1).strip()
        # 解析日期
        try:
            from datetime import datetime
            filing_date = datetime.strptime(info['filing_date_raw'], '%b %d, %Y')
            info['filing_date'] = filing_date.strftime('%Y-%m-%d')
            info['filing_year'] = filing_date.year
        except:
            info['filing_date'] = info['filing_date_raw']
            info['filing_year'] = None
    else:
        # 嘗試其他格式：2008-12-22
        iso_match = re.search(r'Filing date[:\s]+(\d{4}-\d{2}-\d{2})', markdown, re.IGNORECASE)
        if iso_match:
            info['filing_date'] = iso_match.group(1)
            try:
                info['filing_year'] = int(iso_match.group(1).split('-')[0])
            except:
                info['filing_year'] = None
    
    # 提取公開日期
    pub_match = re.search(r'Publication date[:\s]+([A-Za-z0-9,]+)', markdown, re.IGNORECASE)
    if pub_match:
        info['publication_date_raw'] = pub_match.group(1).strip()
        try:
            from datetime import datetime
            pub_date = datetime.strptime(info['publication_date_raw'], '%b %d, %Y')
            info['publication_date'] = pub_date.strftime('%Y-%m-%d')
            info['publication_year'] = pub_date.year
        except:
            info['publication_date'] = info['publication_date_raw']
            info['publication_year'] = None
    
    # 提取專利號（從頁面內容）
    # 格式：US8399073B2
    patent_num_match = re.search(r'([A-Z]{2}\d+[A-Z0-9]+)', markdown[:5000])
    if patent_num_match:
        info['patent_number'] = patent_num_match.group(1)
    
    return info

async def main():
    print("=" * 80)
    print("Merck KGaA 負介電液晶專利搜索 (v4 - 進階 URL + Crawl4AI)")
    print("=" * 80)
    print(f"搜索時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"目標：搜索 2020-2026 年間的專利")
    print("=" * 80)
    print()
    
    all_patents = []
    seen_urls = set()
    
    for i, config in enumerate(SEARCH_CONFIGS, 1):
        query = config['query']
        url = construct_search_url(query)
        
        print(f"[{i}/{len(SEARCH_CONFIGS)}] 搜索：{config['name']}")
        print(f"   查詢：{query}")
        print(f"   URL: {url[:100]}...")
        
        # 爬取搜索結果
        markdown = await crawl_search_results(url)
        
        if not markdown:
            print(f"   ✗ 爬取失敗")
            continue
        
        print(f"   ✓ 爬取成功，markdown 長度：{len(markdown)}")
        
        # 提取專利 URL
        patent_urls = extract_patent_urls_from_markdown(markdown)
        print(f"   找到 {len(patent_urls)} 個專利 URL")
        
        # 提取每個專利的基本信息
        for patent_url in patent_urls[:10]:  # 每個查詢最多 10 個
            if patent_url in seen_urls:
                continue
            
            seen_urls.add(patent_url)
            
            # 爬取專利頁面
            patent_markdown = await crawl_search_results(patent_url)
            
            if not patent_markdown:
                print(f"   ✗ 專利爬取失敗：{patent_url}")
                continue
            
            # 提取專利信息
            patent_info = extract_patent_info_from_markdown(patent_markdown)
            patent_info['url'] = patent_url
            patent_info['source_query'] = query
            
            # 檢查日期範圍
            filing_year = patent_info.get('filing_year')
            in_range = filing_year and 2020 <= filing_year <= 2026
            
            if in_range:
                print(f"   ✓ 符合日期範圍：{patent_info.get('patent_number', 'N/A')} ({patent_info.get('filing_date', 'N/A')})")
                all_patents.append(patent_info)
            else:
                print(f"   ✗ 超出日期範圍：{patent_info.get('patent_number', 'N/A')} ({patent_info.get('filing_date', 'N/A')})")
        
        print()
    
    # 保存結果
    results = {
        "timestamp": datetime.now().isoformat(),
        "count": len(all_patents),
        "patents": all_patents
    }
    
    with open("/tmp/patent_search_results_v4.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print("=" * 80)
    print("搜索完成")
    print(f"  符合日期範圍 (2020-2026) 的專利：{len(all_patents)} 個")
    print(f"  結果已保存：/tmp/patent_search_results_v4.json")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())
