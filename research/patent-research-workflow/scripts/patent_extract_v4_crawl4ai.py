#!/usr/bin/env python3
"""
Merck KGaA 負介電液晶專利提取 (v4 - 改進版 Claim 1 和實施例提取)

改進重點:
1. 使用正則表達式精確提取 Claim 1
2. 識別 Example/Embodiment 段落
3. 提取技術特點和效果數據
4. 使用 Crawl4AI 爬取專利頁面
"""

import asyncio
import json
import re
from datetime import datetime
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

def extract_claim_1(markdown):
    """
    從 markdown 中提取 Claim 1
    
    策略:
    1. 找到 "Claims" 部分
    2. 提取編號為 "1" 的完整條目
    3. 處理多行和縮進
    """
    if not markdown:
        return ""
    
    # 策略 1: 查找 "Claims" 標題後的內容
    claims_match = re.search(
        r'(?:Claims|CLAIMS)[\s\n]*[:\-]?\s*\n+(.*?)(?:\n\s*Description|\n\s*[A-Z][a-z]+\s*:|\Z)',
        markdown, 
        re.DOTALL | re.IGNORECASE
    )
    
    if claims_match:
        claims_text = claims_match.group(1)
        
        # 提取第 1 項 Claim
        # 匹配 "1." 或 "1 " 開頭，到 "2." 或 "2 " 之前
        claim1_match = re.search(
            r'^\s*1[\.:\s]\s+(.*?)(?=\n\s*2[\.:\s]|\Z)',
            claims_text,
            re.DOTALL | re.MULTILINE
        )
        
        if claim1_match:
            claim_text = claim1_match.group(1).strip()
            # 清理多餘的空白和換行
            claim_text = re.sub(r'\s+', ' ', claim_text)
            return f"1. {claim_text}"
    
    # 策略 2: 直接查找 "1." 開頭的段落
    claim1_direct = re.search(
        r'(?:^|\n)\s*1[\.:\s]\s+([A-Z].*?)(?=\n\s*2[\.:\s]|\n\n|\Z)',
        markdown,
        re.DOTALL | re.IGNORECASE
    )
    
    if claim1_direct:
        claim_text = claim1_direct.group(1).strip()
        claim_text = re.sub(r'\s+', ' ', claim_text)
        return f"1. {claim_text}"
    
    return ""

def extract_technical_features(markdown, limit=5):
    """
    從摘要和描述中提取技術特點
    
    策略:
    1. 從 "Abstract" 或 "Technical Field" 提取
    2. 識別關鍵技術詞彙
    3. 提取 3-5 個關鍵特點
    """
    if not markdown:
        return []
    
    features = []
    
    # 策略 1: 從 Abstract 提取
    abstract_match = re.search(
        r'(?:Abstract|ABSTRACT)[\s\n]*[:\-]?\s*\n+(.*?)(?:\n\s*[A-Z][a-z]+\s*:|\n\n[A-Z]|\Z)',
        markdown,
        re.DOTALL | re.IGNORECASE
    )
    
    if abstract_match:
        abstract_text = abstract_match.group(1)
        
        # 提取關鍵短語（以逗號或句號分隔）
        phrases = re.findall(r'([A-Z][a-z]+(?:\s+[a-z]+){0,5}(?:\s+(?:of|for|with|in|to)\s+[a-z]+)?)', abstract_text)
        
        # 過濾出技術相關短語
        tech_keywords = ['liquid', 'crystal', 'dielectric', 'anisotropy', 'compound', 'mixture', 'material', 'composition']
        for phrase in phrases[:limit]:
            if any(kw in phrase.lower() for kw in tech_keywords):
                features.append(phrase.strip())
    
    # 策略 2: 從 "Technical Field" 或 "Summary" 提取
    summary_match = re.search(
        r'(?:Technical Field|Summary|SUMMARY)[\s\n]*[:\-]?\s*\n+(.*?)(?:\n\s*[A-Z][a-z]+\s*:|\n\n[A-Z]|\Z)',
        markdown,
        re.DOTALL | re.IGNORECASE
    )
    
    if summary_match and len(features) < limit:
        summary_text = summary_match.group(1)
        
        # 提取句子
        sentences = re.findall(r'([A-Z][^.]*?(?:liquid|crystal|dielectric)[^.]*\.)', summary_text, re.IGNORECASE)
        
        for sent in sentences[:limit - len(features)]:
            features.append(sent.strip())
    
    return features[:limit]

def extract_examples(markdown):
    """
    從專利中提取實施例 (Examples)
    
    策略:
    1. 找到 "Examples" 或 "Embodiments" 部分
    2. 提取每個 Example 的編號和內容
    3. 特別關注包含效果數據的段落
    """
    if not markdown:
        return []
    
    examples = []
    
    # 策略 1: 查找 "Examples" 部分
    examples_section = re.search(
        r'(?:Examples|EXAMPLES|Embodiments|EMBODIMENTS)[\s\n]*[:\-]?\s*\n+(.*?)(?:\n\s*[^E]|\Z)',
        markdown,
        re.DOTALL | re.IGNORECASE
    )
    
    if examples_section:
        examples_text = examples_section.group(1)
        
        # 提取每個 Example（格式："Example 1", "Example 2" 等）
        example_matches = re.finditer(
            r'(?:Example|Embodiment)\s*(\d+|[A-Z])[:\.\s]\s+(.*?)(?=(?:Example|Embodiment)\s*\d+|\Z)',
            examples_text,
            re.DOTALL | re.IGNORECASE
        )
        
        for match in example_matches:
            example_num = match.group(1)
            example_content = match.group(2).strip()
            
            # 提取效果數據（如果有的話）
            effects = []
            effect_keywords = ['yield', 'efficiency', 'voltage', 'threshold', 'response time', 'stability']
            for line in example_content.split('\n'):
                if any(kw in line.lower() for kw in effect_keywords):
                    effects.append(line.strip())
            
            examples.append({
                'number': example_num,
                'content': example_content[:500],  # 限制長度
                'effects': effects[:3]  # 最多 3 個效果
            })
    
    # 策略 2: 如果沒有找到 Examples 部分，查找 "Preparation" 或 "Synthesis"
    if not examples:
        prep_match = re.search(
            r'(?:Preparation|Synthesis|PREPARATION|SYNTHESIS)[\s\n]*[:\-]?\s*\n+(.*?)(?:\n\s*[^P]|\Z)',
            markdown,
            re.DOTALL | re.IGNORECASE
        )
        
        if prep_match:
            prep_text = prep_match.group(1)
            examples.append({
                'number': '1',
                'content': prep_text[:500],
                'effects': []
            })
    
    return examples

def extract_patent_number(markdown):
    """提取專利號"""
    if not markdown:
        return ""
    
    # 從標題行提取
    title_match = re.search(r'^#\s+([A-Z]{2}\d+[A-Z0-9]+)', markdown)
    if title_match:
        return title_match.group(1)
    
    # 從內容提取
    patent_match = re.search(r'([A-Z]{2}\d+[A-Z0-9]+)', markdown[:2000])
    if patent_match:
        return patent_match.group(1)
    
    return ""

def extract_title(markdown):
    """提取專利標題"""
    if not markdown:
        return ""
    
    # 從第一行提取（去掉 # 和 Google Patents）
    title_match = re.search(r'^#\s+(.+?)(?:\s+-\s+Google Patents)?$', markdown, re.MULTILINE)
    if title_match:
        return title_match.group(1).strip()
    
    return ""

def extract_dates(markdown):
    """提取申請日期和公開日期"""
    dates = {
        'filing_date': None,
        'filing_year': None,
        'publication_date': None,
        'publication_year': None
    }
    
    if not markdown:
        return dates
    
    # 提取申請日期
    filing_match = re.search(r'Filing date[:\s]+([A-Za-z0-9,\-\s]+)', markdown, re.IGNORECASE)
    if filing_match:
        raw_date = filing_match.group(1).strip()
        dates['filing_date'] = raw_date
        
        # 嘗試解析年份
        try:
            # 格式："Dec 22, 2008"
            from datetime import datetime
            parsed = datetime.strptime(raw_date, '%b %d, %Y')
            dates['filing_year'] = parsed.year
        except:
            # 格式："2008-12-22"
            year_match = re.search(r'(\d{4})', raw_date)
            if year_match:
                dates['filing_year'] = int(year_match.group(1))
    
    # 提取公開日期
    pub_match = re.search(r'Publication date[:\s]+([A-Za-z0-9,\-\s]+)', markdown, re.IGNORECASE)
    if pub_match:
        raw_date = pub_match.group(1).strip()
        dates['publication_date'] = raw_date
        
        try:
            from datetime import datetime
            parsed = datetime.strptime(raw_date, '%b %d, %Y')
            dates['publication_year'] = parsed.year
        except:
            year_match = re.search(r'(\d{4})', raw_date)
            if year_match:
                dates['publication_year'] = int(year_match.group(1))
    
    return dates

async def extract_patent_info(markdown, url):
    """整合所有提取邏輯"""
    patent = {
        'url': url,
        'patent_number': extract_patent_number(markdown),
        'title': extract_title(markdown),
        'claim_1': extract_claim_1(markdown),
        'technical_features': extract_technical_features(markdown),
        'examples': extract_examples(markdown),
    }
    
    dates = extract_dates(markdown)
    patent.update(dates)
    
    # 檢查日期範圍
    filing_year = patent.get('filing_year')
    patent['in_date_range'] = filing_year and 2020 <= filing_year <= 2026
    
    return patent

async def crawl_and_extract(url):
    """爬取並提取單一專利"""
    browser_config = BrowserConfig(headless=True, verbose=False)
    crawler_config = CrawlerRunConfig(
        word_count_threshold=1,
        remove_overlay_elements=True,
    )
    
    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(url=url, config=crawler_config)
        
        if result.success:
            return await extract_patent_info(result.markdown, url)
        else:
            return None

async def main():
    print("=" * 80)
    print("Merck KGaA 負介電液晶專利提取 (v4 - 改進版)")
    print("=" * 80)
    
    # 讀取搜索結果（優先使用 v4，如果不存在則使用舊格式）
    search_files = [
        "/tmp/patent_search_results_v4.json",
        "/tmp/patent_search_results.json",
    ]
    
    patents_to_extract = []
    search_file_used = None
    
    for search_file in search_files:
        try:
            with open(search_file, "r", encoding="utf-8") as f:
                search_data = json.load(f)
            
            # v4 格式（patents 列表）
            if 'patents' in search_data:
                patents_to_extract = search_data.get('patents', [])
                search_file_used = search_file
                if patents_to_extract:
                    break
                # 如果為空，繼續檢查下一個文件
            
            # 舊格式（results 列表）
            elif 'results' in search_data:
                raw_results = search_data.get('results', [])
                # 轉換為統一的格式
                patents_to_extract = []
                for item in raw_results:
                    if isinstance(item, dict):
                        patents_to_extract.append(item)
                search_file_used = search_file
                if patents_to_extract:
                    break
                # 如果為空，繼續檢查下一個文件
            
            # 直接是 list
            elif isinstance(search_data, list):
                patents_to_extract = search_data
                search_file_used = search_file
                if patents_to_extract:
                    break
                # 如果為空，繼續檢查下一個文件
                
        except FileNotFoundError:
            continue
        except json.JSONDecodeError:
            continue
    
    if not patents_to_extract:
        print("✗ 沒有找到專利，請先執行搜索腳本")
        print("  預期文件：/tmp/patent_search_results_v4.json 或 /tmp/patent_search_results.json")
        return
    
    print(f"從 {search_file_used} 讀取到 {len(patents_to_extract)} 個專利")
    
    # 提取每個專利
    extracted_patents = []
    
    for i, patent_info in enumerate(patents_to_extract, 1):
        url = patent_info.get('url', '')
        
        print(f"\n[{i}/{len(patents_to_extract)}] 提取：{url}")
        
        patent_data = await crawl_and_extract(url)
        
        if patent_data:
            extracted_patents.append(patent_data)
            print(f"  ✓ 提取成功")
            print(f"    專利號：{patent_data.get('patent_number', 'N/A')}")
            print(f"    Claim 1 長度：{len(patent_data.get('claim_1', ''))} 字元")
            print(f"    技術特點：{len(patent_data.get('technical_features', []))} 項")
            print(f"    實施例：{len(patent_data.get('examples', []))} 個")
            print(f"    日期範圍：{'✓ 符合' if patent_data.get('in_date_range') else '✗ 超出'}")
        else:
            print(f"  ✗ 提取失敗")
    
    # 保存結果
    results = {
        'timestamp': datetime.now().isoformat(),
        'count': len(extracted_patents),
        'patents': extracted_patents
    }
    
    with open("/tmp/extracted_patents_v4.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    # 統計
    total = len(extracted_patents)
    with_claim_1 = sum(1 for p in extracted_patents if p.get('claim_1'))
    with_examples = sum(1 for p in extracted_patents if p.get('examples'))
    in_date_range = sum(1 for p in extracted_patents if p.get('in_date_range'))
    
    print("\n" + "=" * 80)
    print("提取統計")
    print("=" * 80)
    print(f"  總提取數量：{total}")
    print(f"  有 Claim 1: {with_claim_1}/{total}")
    print(f"  有實施例：{with_examples}/{total}")
    print(f"  符合日期範圍 (2020-2026): {in_date_range}/{total}")
    print(f"  結果已保存：/tmp/extracted_patents_v4.json")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())
