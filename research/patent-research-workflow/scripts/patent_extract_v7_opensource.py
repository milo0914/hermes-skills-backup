#!/usr/bin/env python3
"""
Merck KGaA 負介電液晶專利提取 v7 (開源版 - 改進 Claim 1 提取)
目標：使用 Crawl4AI + 改進的正則表達式，解決 Claim 1 提取失敗問題
"""

import asyncio
import json
import re
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

def extract_claim_1_improved(markdown_text):
    """
    改進版 Claim 1 提取 - 多模式匹配
    """
    if not markdown_text:
        return ""
    
    # 模式 1: 標準 Claims 部分 + 編號 1
    pattern1 = r'Claims?\s*\n+1\.\s+(.*?)(?=\n\s*2\.|\n\s*3\.|\Z)'
    match = re.search(pattern1, markdown_text, re.DOTALL | re.IGNORECASE)
    if match:
        return "1. " + match.group(1).strip()
    
    # 模式 2: CLAIMS 大寫
    pattern2 = r'CLAIMS?\s*\n+1\.\s+(.*?)(?=\n\s*2\.|\n\s*3\.|\Z)'
    match = re.search(pattern2, markdown_text, re.DOTALL | re.IGNORECASE)
    if match:
        return "1. " + match.group(1).strip()
    
    # 模式 3: What is claimed is 開頭
    pattern3 = r'[Ww]hat is claimed is[:\s]*\n+1\.\s+(.*?)(?=\n\s*2\.|\n\s*3\.|\Z)'
    match = re.search(pattern3, markdown_text, re.DOTALL)
    if match:
        return "1. " + match.group(1).strip()
    
    # 模式 4: 直接找 "1." 開頭（無 Claims 標題）
    pattern4 = r'^\s*1\.\s+(.*?)(?=\n\s*2\.|\n\s*3\.|\Z)'
    match = re.search(pattern4, markdown_text, re.DOTALL | re.MULTILINE)
    if match:
        return "1. " + match.group(1).strip()
    
    # 模式 5: 找 "The invention claimed is:" 後的第一項
    pattern5 = r'[Tt]he invention claimed is[:\s]*\n+1\.\s+(.*?)(?=\n\s*2\.|\n\s*3\.|\Z)'
    match = re.search(pattern5, markdown_text, re.DOTALL)
    if match:
        return "1. " + match.group(1).strip()
    
    return ""

def extract_examples_improved(markdown_text):
    """
    改進版實施例提取 - 多模式匹配
    """
    if not markdown_text:
        return []
    
    examples = []
    
    # 模式 1: Example + 數字
    pattern1 = r'(?:Example|EXAMPLE)\s+(\d+[A-Z]?)[:\s\n]+(.*?)(?=\n\s*(?:Example|EXAMPLE|Embodiment|COMPARATIVE|TABLE|DRAWING)|\Z)'
    matches = re.findall(pattern1, markdown_text, re.DOTALL | re.IGNORECASE)
    for match in matches:
        examples.append(f"Example {match[0]}: {match[1][:500]}...")
    
    # 模式 2: Embodiment + 數字
    pattern2 = r'(?:Embodiment|EMBODIMENT)\s+(\d+)[:\s\n]+(.*?)(?=\n\s*(?:Example|Embodiment|COMPARATIVE|TABLE|DRAWING)|\Z)'
    matches = re.findall(pattern2, markdown_text, re.DOTALL | re.IGNORECASE)
    for match in matches:
        examples.append(f"Embodiment {match[0]}: {match[1][:500]}...")
    
    # 模式 3: 如果有 "Examples" 標題下的內容
    pattern3 = r'(?:Examples|EXAMPLES)[:\s\n]+(.*?)(?=\n\s*(?:COMPARATIVE|TABLE|DRAWING|Claim)|\Z)'
    match = re.search(pattern3, markdown_text, re.DOTALL | re.IGNORECASE)
    if match:
        examples.append(f"Examples section: {match.group(1)[:500]}...")
    
    return examples[:5]  # 最多返回 5 個

def extract_technical_features(markdown_text):
    """
    提取技術特點 - 從摘要和技術領域提取
    """
    if not markdown_text:
        return []
    
    features = []
    
    # 從 Abstract 提取
    abstract_match = re.search(r'Abstract[:\s\n]+(.*?)(?=\n\s*(?:Technical Field|Background|Summary)|\Z)', markdown_text, re.DOTALL | re.IGNORECASE)
    if abstract_match:
        abstract_text = abstract_match.group(1)
        # 提取關鍵短語
        keywords = re.findall(r'(?:comprises?|includes?|features?|provides?|enables?|improves?)[\s\S]{0,100}', abstract_text, re.IGNORECASE)
        features.extend([kw.strip() for kw in keywords[:3]])
    
    # 從 Technical Field 提取
    tech_field_match = re.search(r'Technical Field[:\s\n]+(.*?)(?=\n\s*(?:Background|Summary|Abstract)|\Z)', markdown_text, re.DOTALL | re.IGNORECASE)
    if tech_field_match:
        features.append(f"Technical Field: {tech_field_match.group(1)[:200]}")
    
    return features[:5] if features else ["未明確提取到技術特點"]

def extract_patent_number(markdown_text):
    """
    提取專利號
    """
    if not markdown_text:
        return ""
    
    # 模式 1: 標準專利號格式
    patterns = [
        r'Patent Number[:\s]+([A-Z]{2}\d+[A-Z]?)',
        r'Publication Number[:\s]+([A-Z]{2}\d+[A-Z]?)',
        r'Patent No\.[:\s]+([A-Z]{2}\d+[A-Z]?)',
        r'([A-Z]{2}\d+[A-Z]?)\s+(?:en|de|fr)',  # URL 結尾
    ]
    
    for pattern in patterns:
        match = re.search(pattern, markdown_text, re.IGNORECASE)
        if match:
            return match.group(1)
    
    return ""

def extract_filing_date(markdown_text):
    """
    提取申請日期
    """
    if not markdown_text:
        return ""
    
    # 各種日期格式
    patterns = [
        (r'Filing Date[:\s]+(\d{4}-\d{2}-\d{2})', '%Y-%m-%d'),
        (r'Filing Date[:\s]+(\d{2}/\d{2}/\d{4})', '%m/%d/%Y'),
        (r'Filed[:\s]+(\w+\s+\d+,\s+\d{4})', '%B %d, %Y'),
    ]
    
    for pattern, date_format in patterns:
        match = re.search(pattern, markdown_text, re.IGNORECASE)
        if match:
            return match.group(1)
    
    return ""

async def extract_patent_info(url, crawler_config):
    """
    提取單一專利信息
    """
    try:
        async with AsyncWebCrawler(config=crawler_config) as crawler:
            result = await crawler.arun(url=url, config=crawler_config)
            
            if not result.success:
                return None
            
            markdown_text = result.markdown
            
            return {
                'url': url,
                'patent_number': extract_patent_number(markdown_text),
                'filing_date': extract_filing_date(markdown_text),
                'claim_1': extract_claim_1_improved(markdown_text),
                'examples': extract_examples_improved(markdown_text),
                'technical_features': extract_technical_features(markdown_text),
                'markdown_length': len(markdown_text)
            }
    except Exception as e:
        print(f"  ✗ 提取失敗：{e}")
        return None

async def main():
    print("=" * 80)
    print("Merck KGaA 負介電液晶專利提取 v7（開源版 - 改進 Claim 1 提取）")
    print("=" * 80)
    
    # 讀取搜索結果
    search_files = [
        "/tmp/patent_search_results.json",
    ]
    
    patents = []
    search_file_used = None
    
    for search_file in search_files:
        try:
            with open(search_file, "r", encoding="utf-8") as f:
                search_data = json.load(f)
            
            if 'patents' in search_data:
                patents = search_data.get('patents', [])
                search_file_used = search_file
                break
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
        print("❌ 找不到搜索結果文件")
        exit(1)
    
    print(f"從 {search_file_used} 讀取到 {len(patents)} 個專利")
    
    # 配置 Crawl4AI - 使用正確的參數
    browser_config = BrowserConfig(headless=True, verbose=False)
    crawler_config = CrawlerRunConfig(
        word_count_threshold=1,
        page_timeout=60000,  # 60 秒超時
        wait_until='domcontentloaded',
        verbose=False
    )
    
    # 提取專利信息
    extracted_patents = []
    success_count = 0
    claim_1_count = 0
    examples_count = 0
    
    for i, patent in enumerate(patents, 1):
        url = patent.get('url', '')
        print(f"\n[{i}/{len(patents)}] 提取：{url}")
        
        result = await extract_patent_info(url, crawler_config)
        
        if result:
            success_count += 1
            has_claim_1 = bool(result['claim_1'] and len(result['claim_1']) > 10)
            has_examples = len(result['examples']) > 0
            
            if has_claim_1:
                claim_1_count += 1
            if has_examples:
                examples_count += 1
            
            print(f" ✓ 提取成功")
            print(f"  專利號：{result['patent_number'] or 'N/A'}")
            print(f"  Claim 1 長度：{len(result['claim_1'])} 字元")
            print(f"  實施例：{len(result['examples'])} 個")
            print(f"  技術特點：{len(result['technical_features'])} 項")
            
            extracted_patents.append(result)
        else:
            print(f" ✗ 提取失敗")
    
    # 統計
    print("\n" + "=" * 80)
    print("提取統計")
    print("=" * 80)
    print(f" 總提取數量：{success_count}/{len(patents)}")
    print(f" 有 Claim 1: {claim_1_count}/{success_count} ({claim_1_count/success_count*100:.1f}%)" if success_count > 0 else " 有 Claim 1: 0")
    print(f" 有實施例：{examples_count}/{success_count} ({examples_count/success_count*100:.1f}%)" if success_count > 0 else " 有實施例：0")
    print(f" 結果已保存：/tmp/extracted_patents_v7.json")
    
    # 保存結果
    with open("/tmp/extracted_patents_v7.json", "w", encoding="utf-8") as f:
        json.dump(extracted_patents, f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    asyncio.run(main())
