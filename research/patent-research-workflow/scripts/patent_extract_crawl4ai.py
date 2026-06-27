#!/usr/bin/env python3
"""
Crawl4AI 專利提取腳本
使用 Crawl4AI 爬取 Google Patents 頁面並提取 Claim 1

用法：
    python patent_extract_crawl4ai.py <patent_url>
    
範例：
    python patent_extract_crawl4ai.py https://patents.google.com/patent/US8399073B2/en
"""

import asyncio
import sys
import re
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig


async def extract_patent_markdown(url):
    """爬取專利頁面並返回 markdown"""
    browser_config = BrowserConfig(
        headless=True,
        verbose=False
    )
    
    crawler_config = CrawlerRunConfig(
        word_count_threshold=10,
        excluded_tags=['script', 'style'],
        verbose=False
    )
    
    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(url=url, config=crawler_config)
        
        if result.success:
            return result.markdown
        else:
            return None


def extract_claim_1(markdown):
    """從 markdown 中提取 Claim 1"""
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
    
    # 嘗試直接找 "1." 開頭的段落
    claim_match = re.search(r'\n1\.\s+(.*?)(?=\n\s*2\.|\Z)', markdown, re.DOTALL)
    if claim_match:
        return "1. " + claim_match.group(1).strip()
    
    return ""


def extract_filing_date(markdown):
    """提取申請日期"""
    patterns = [
        r'Filing date[:\s]+(\d{4}-\d{2}-\d{2})',
        r'Filing date[:\s]+(\d{2}/\d{2}/\d{4})',
        r'Priority date[:\s]+(\d{4}-\d{2}-\d{2})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, markdown, re.IGNORECASE)
        if match:
            date_str = match.group(1)
            if '/' in date_str:
                parts = date_str.split('/')
                date_str = f"{parts[2]}-{parts[0]}-{parts[1]}"
            return date_str
    
    return ""


async def main():
    if len(sys.argv) < 2:
        print("用法：python patent_extract_crawl4ai.py <patent_url>")
        print("範例：python patent_extract_crawl4ai.py https://patents.google.com/patent/US8399073B2/en")
        sys.exit(1)
    
    url = sys.argv[1]
    print(f"爬取：{url}")
    
    markdown = await extract_patent_markdown(url)
    
    if not markdown:
        print("✗ 爬取失敗")
        sys.exit(1)
    
    print(f"✓ 爬取成功")
    print(f"Markdown 長度：{len(markdown)} 字元")
    
    # 提取 Claim 1
    claim_1 = extract_claim_1(markdown)
    if claim_1:
        print(f"\nClaim 1 長度：{len(claim_1)} 字元")
        print(f"Claim 1 前 200 字：{claim_1[:200]}...")
    else:
        print("\n✗ 未找到 Claim 1")
    
    # 提取申請日期
    filing_date = extract_filing_date(markdown)
    if filing_date:
        print(f"申請日期：{filing_date}")
    else:
        print("✗ 未找到申請日期")


if __name__ == "__main__":
    asyncio.run(main())
