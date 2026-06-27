#!/usr/bin/env python3
"""
Merck KGaA 負介電液晶專利提取腳本 v3 (Crawl4AI 版本)
使用舊搜索結果並用 Crawl4AI 重新提取

策略：
1. 讀取舊搜索結果（9 個專利 URL）
2. 用 Crawl4AI 爬取每個專利頁面
3. 手動提取 Claim 1 和實施例
4. 過濾日期範圍 2020-2026
"""

import asyncio
import json
import re
from datetime import datetime
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

# 提取配置
EXTRACT_CONFIG = {
    "min_year": 2020,
    "max_year": 2026,
}

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


def extract_patent_number(url):
    """從 URL 提取專利號"""
    match = re.search(r'patent/([A-Z0-9]+)/en', url)
    return match.group(1) if match else ""


def extract_title(markdown):
    """提取標題"""
    # 匹配標題
    match = re.search(r'#\s*(.*?)(?:- Google Patents|\|)', markdown)
    if match:
        return match.group(1).strip()
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
    
    # 嘗試從描述中找日期
    date_match = re.search(r'(\d{4}-\d{2}-\d{2})', markdown)
    if date_match:
        return date_match.group(1)
    
    return ""


def extract_claim_1(markdown):
    """提取 Claim 1 完整內容"""
    # 找到 Claims 部分
    claims_match = re.search(r'Claims\s*\n+(.*?)(?=\n\s*Description|\Z)', markdown, re.DOTALL | re.IGNORECASE)
    
    if not claims_match:
        # 嘗試直接找 "1." 開頭的段落
        claim_match = re.search(r'\n1\.\s+(.*?)(?=\n\s*2\.|\Z)', markdown, re.DOTALL)
        if claim_match:
            return "1. " + claim_match.group(1).strip()
        return ""
    
    claims_text = claims_match.group(1)
    
    # 從 Claims 中提取第 1 項
    claim1_match = re.search(r'^\s*1\.\s+(.*?)(?=\n\s*2\.|\Z)', claims_text, re.DOTALL | re.MULTILINE)
    
    if claim1_match:
        return "1. " + claim1_match.group(1).strip()
    
    return ""


def extract_technical_features(markdown, patent_info):
    """提取技術特點"""
    features = []
    
    # 從摘要提取
    abstract_match = re.search(r'Abstract\s*\n(.*?)(?=\n\s*\w|\Z)', markdown, re.DOTALL)
    if abstract_match:
        abstract = abstract_match.group(1)
        
        # 關鍵技術詞
        keywords = {
            'negative dielectric': '負介電',
            'anisotropy': '各向異性',
            'liquid crystal': '液晶',
            'compound': '化合物',
            'mixture': '混合物',
            'voltage': '電壓',
            'threshold': '閾值',
        }
        
        for keyword, keyword_zh in keywords.items():
            if keyword.lower() in abstract.lower():
                features.append(f"包含{keyword_zh}技術")
    
    return list(set(features))[:5]  # 去重並限制 5 個


async def extract_single_patent(url, index, total):
    """提取單一專利"""
    print(f"\n[{index}/{total}] 爬取：{url}")
    
    try:
        markdown = await extract_patent_markdown(url)
        
        if not markdown:
            print(f"  ✗ 爬取失敗")
            return None
        
        patent_num = extract_patent_number(url)
        title = extract_title(markdown)
        filing_date = extract_filing_date(markdown)
        claim_1 = extract_claim_1(markdown)
        tech_features = extract_technical_features(markdown, {})
        
        # 檢查日期範圍
        in_range = False
        if filing_date:
            try:
                year = int(filing_date.split('-')[0])
                in_range = EXTRACT_CONFIG['min_year'] <= year <= EXTRACT_CONFIG['max_year']
            except:
                pass
        
        result = {
            "patent_number": patent_num,
            "title": title,
            "filing_date": filing_date,
            "claim_1": claim_1,
            "technical_features": tech_features,
            "examples": [],
            "url": url,
            "claim_1_length": len(claim_1),
            "examples_count": 0,
            "in_date_range": in_range
        }
        
        print(f"  ✓ 提取成功")
        print(f"  專利號：{patent_num}")
        print(f"  標題：{title[:60]}...")
        print(f"  申請日期：{filing_date or 'N/A'}")
        print(f"  Claim 1 長度：{len(claim_1)} 字元")
        print(f"  技術特點：{len(tech_features)} 項")
        print(f"  日期範圍 (2020-2026): {'✓ 符合' if in_range else '✗ 超出'}")
        
        return result
        
    except Exception as e:
        print(f"  ✗ 提取失敗：{str(e)}")
        return None


async def main():
    """主函數"""
    print("=" * 80)
    print("Merck KGaA 負介電液晶專利提取 (v3 - Crawl4AI)")
    print("=" * 80)
    
    # 讀取舊搜索結果
    search_file = "/tmp/patent_search_results.json"
    try:
        with open(search_file, 'r', encoding='utf-8') as f:
            search_data = json.load(f)
        
        # 提取專利 URL
        patent_urls = []
        for result in search_data.get('results', []):
            if 'url' in result:
                patent_urls.append(result['url'])
        
        # 去重
        patent_urls = list(dict.fromkeys(patent_urls))
        
        print(f"從 {search_file} 讀取到 {len(patent_urls)} 個專利 URL")
        
    except FileNotFoundError:
        print(f"✗ 搜索結果文件不存在：{search_file}")
        return
    
    if not patent_urls:
        print("✗ 沒有專利 URL 可提取")
        return
    
    # 提取每個專利
    extracted_patents = []
    
    for i, url in enumerate(patent_urls, 1):
        result = await extract_single_patent(url, i, len(patent_urls))
        if result:
            extracted_patents.append(result)
    
    # 保存結果
    output = {
        "extraction_config": EXTRACT_CONFIG,
        "extracted_patents": extracted_patents,
        "count": len(extracted_patents),
        "timestamp": datetime.now().isoformat()
    }
    
    output_file = "/tmp/extracted_patents_v3.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print(f"\n提取結果已保存：{output_file}")
    print(f"提取完成：成功 {len(extracted_patents)}/{len(patent_urls)}")
    
    # 統計
    in_range_count = sum(1 for p in extracted_patents if p['in_date_range'])
    has_claim1 = sum(1 for p in extracted_patents if p['claim_1'])
    
    print(f"\n統計:")
    print(f"  有 Claim 1 的專利：{has_claim1}/{len(extracted_patents)}")
    print(f"  符合日期範圍 (2020-2026): {in_range_count}/{len(extracted_patents)}")
    
    # 顯示符合日期的專利
    if in_range_count > 0:
        print(f"\n符合日期範圍的專利:")
        for p in extracted_patents:
            if p['in_date_range']:
                print(f"  - {p['patent_number']}: {p['title'][:50]}... ({p['filing_date']})")


if __name__ == "__main__":
    asyncio.run(main())
