#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Merck KGaA 負介電液晶專利提取 v6 - 混合方案（Crawl4AI + 手動解析）
GRPO 規劃改進版 - 方案 C（評分 1.65/2.0）

改進策略:
1. 使用 Crawl4AI 爬取專利頁面 markdown
2. 手動解析 markdown 提取 Claim 1（精確正則）
3. 手動解析實施例（Example/Embodiment 段落）
4. 嚴格日期過濾（2020-2026）

執行方式:
    python3 patent_extract_v6_hybrid.py
"""

import json
import re
import asyncio
from datetime import datetime
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

async def extract_patent_info(url):
    """使用 Crawl4AI 提取專利信息"""
    browser_config = BrowserConfig(
        headless=True,
        verbose=False
    )
    crawler_config = CrawlerRunConfig(
        word_count_threshold=1,
        page_timeout=30000
    )
    
    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(url=url, config=crawler_config)
        return result

def extract_claim_1(markdown):
    """從 markdown 中提取 Claim 1"""
    if not markdown:
        return ""
    
    # 找到 Claims 部分
    claims_match = re.search(r'Claims\s*\n+(.*?)(?=\n\s*Description|\Z)', markdown, re.DOTALL | re.IGNORECASE)
    
    if claims_match:
        claims_text = claims_match.group(1)
        # 提取第 1 項 Claim
        claim1_match = re.search(r'^\s*1\.\s+(.*?)(?=\n\s*2\.|\Z)', claims_text, re.DOTALL | re.MULTILINE)
        if claim1_match:
            return "1. " + claim1_match.group(1).strip()
    
    return ""

def extract_examples(markdown):
    """從 markdown 中提取實施例"""
    if not markdown:
        return []
    
    examples = []
    
    # 查找 Example 或 Embodiment 段落
    example_pattern = r'(Example|Embodiment)\s+\d+[:\.\n]'
    matches = re.finditer(example_pattern, markdown, re.IGNORECASE)
    
    for match in matches:
        start = match.start()
        # 向前找 100 字元，向後找 500 字元
        excerpt = markdown[max(0, start-100):min(len(markdown), start+500)]
        examples.append(excerpt.strip())
    
    return examples[:5]  # 最多 5 個實施例

def extract_technical_features(markdown):
    """從摘要和描述中提取技術特點"""
    if not markdown:
        return []
    
    features = []
    
    # 從 Abstract 提取
    abstract_match = re.search(r'Abstract\s*\n+(.*?)(?=\n\s*Description|\Z)', markdown, re.DOTALL | re.IGNORECASE)
    if abstract_match:
        abstract = abstract_match.group(1)
        # 提取關鍵短語
        if 'dielectric' in abstract.lower():
            features.append("Negative dielectric anisotropy material")
        if 'liquid crystal' in abstract.lower():
            features.append("Liquid crystal composition")
        if 'display' in abstract.lower():
            features.append("Display device application")
    
    return list(set(features))[:5]  # 去重，最多 5 個

def extract_filing_date(markdown):
    """從 markdown 中提取申請日期"""
    if not markdown:
        return ""
    
    # 查找日期模式
    date_patterns = [
        r'Filing Date[:\s]+(\d{4}-\d{2}-\d{2})',
        r'Filing Date[:\s]+(\d{2}/\d{2}/\d{4})',
        r'Filed[:\s]+(\w+ \d+, \d{4})',
    ]
    
    for pattern in date_patterns:
        match = re.search(pattern, markdown, re.IGNORECASE)
        if match:
            return match.group(1)
    
    return ""

def check_date_range(filing_date):
    """檢查日期是否在 2020-2026 範圍內"""
    if not filing_date:
        return False
    
    try:
        # 解析日期
        year = None
        if '-' in filing_date:
            year = int(filing_date.split('-')[0])
        elif '/' in filing_date:
            year = int(filing_date.split('/')[-1])
        elif ',' in filing_date:
            year = int(filing_date.split(',')[-1].strip())
        
        if year:
            return 2020 <= year <= 2026
    
    except:
        pass
    
    return False

async def main():
    print("=" * 80)
    print("Merck KGaA 負介電液晶專利提取 v6（混合方案 - Crawl4AI + 手動解析）")
    print("=" * 80)
    
    # 讀取搜索結果（優先使用 v6，如果不存在則使用舊結果）
    search_files = [
        "/tmp/patent_search_results_v6.json",
        "/tmp/patent_search_results.json",
    ]
    
    patents = []
    search_file_used = None
    
    for search_file in search_files:
        try:
            with open(search_file, "r", encoding="utf-8") as f:
                search_data = json.load(f)
            
            # 新格式（patents 列表）
            if 'patents' in search_data:
                patents = search_data.get('patents', [])
                search_file_used = search_file
                break
            
            # 舊格式（results 列表）
            elif 'results' in search_data:
                results = search_data.get('results', [])
                for item in results:
                    if isinstance(item, dict):
                        patents.append(item)
                search_file_used = search_file
                break
                
        except FileNotFoundError:
            continue
        except Exception as e:
            print(f"讀取 {search_file} 失敗：{e}")
            continue
    
    if not patents:
        print(f"❌ 找不到搜索結果文件")
        print("請先執行搜索腳本：python3 patent_search_v6_hybrid.py")
        exit(1)
    
    print(f"從 {search_file_used} 讀取到 {len(patents)} 個專利")
    
    # 提取專利信息
    extracted_patents = []
    
    for i, patent in enumerate(patents[:10], 1):  # 限制前 10 個
        url = patent.get("url", "")
        print(f"\n[{i}/{min(10, len(patents))}] 提取：{url}")
        
        try:
            # 使用 Crawl4AI 爬取
            result = await extract_patent_info(url)
            
            # 提取信息
            claim_1 = extract_claim_1(result.markdown)
            examples = extract_examples(result.markdown)
            technical_features = extract_technical_features(result.markdown)
            filing_date = extract_filing_date(result.markdown)
            
            # 檢查日期範圍
            date_ok = check_date_range(filing_date)
            
            extracted = {
                "url": url,
                "title": patent.get("title", ""),
                "patent_number": "",  # 待提取
                "filing_date": filing_date,
                "claim_1": claim_1,
                "examples": examples,
                "technical_features": technical_features,
                "date_in_range": date_ok,
                "markdown_length": len(result.markdown)
            }
            
            extracted_patents.append(extracted)
            
            print(f" ✓ 提取成功")
            print(f"  專利號：{extracted['patent_number'] or 'N/A'}")
            print(f"  Claim 1 長度：{len(claim_1)} 字元")
            print(f"  實施例：{len(examples)} 個")
            print(f"  技術特點：{len(technical_features)} 項")
            print(f"  日期範圍：{'✓ 符合' if date_ok else '✗ 超出'}")
            
        except Exception as e:
            print(f" ✗ 提取失敗：{e}")
            extracted_patents.append({
                "url": url,
                "error": str(e)
            })
    
    # 保存結果
    output_data = {
        "extract_time": datetime.now().isoformat(),
        "total_extracted": len(extracted_patents),
        "successful": len([p for p in extracted_patents if "error" not in p]),
        "claim_1_count": len([p for p in extracted_patents if p.get("claim_1")]),
        "example_count": len([p for p in extracted_patents if p.get("examples")]),
        "date_range_ok": len([p for p in extracted_patents if p.get("date_in_range")]),
        "patents": extracted_patents
    }
    
    with open("/tmp/extracted_patents_v6.json", "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False, default=str)
    
    print("\n" + "=" * 80)
    print("提取統計")
    print("=" * 80)
    print(f" 總提取數量：{output_data['total_extracted']}")
    print(f" 有 Claim 1: {output_data['claim_1_count']}/{output_data['successful']}")
    print(f" 有實施例：{output_data['example_count']}/{output_data['successful']}")
    print(f" 符合日期範圍 (2020-2026): {output_data['date_range_ok']}/{output_data['successful']}")
    print(f" 結果已保存：/tmp/extracted_patents_v6.json")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())
