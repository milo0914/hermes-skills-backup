#!/usr/bin/env python3
"""
Merck KGaA 負介電液晶專利提取 v10-A
方案 A：HTML 結構化解析改進（meta 標籤、JSON-LD、微數據）
"""

import json
import re
from typing import Optional, Dict, Any, List
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def parse_structured_data(html: str, url: str) -> Dict[str, Any]:
    """解析 HTML 中的結構化數據"""
    soup = BeautifulSoup(html, 'lxml')
    result = {
        'patent_number': None,
        'title': None,
        'publication_date': None,
        'filing_date': None,
        'abstract': None,
        'inventors': [],
        'assignee': None
    }
    
    # 1. 解析 JSON-LD
    json_ld_scripts = soup.find_all('script', type='application/ld+json')
    for script in json_ld_scripts:
        try:
            data = json.loads(script.string)
            if data.get('@type') == 'Patent' or 'Patent' in str(data.get('@type', '')):
                result['patent_number'] = data.get('publicationNumber') or data.get('patentNumber')
                result['title'] = data.get('name') or data.get('headline')
                result['abstract'] = data.get('abstract') or data.get('description')
                if 'datePublished' in data:
                    result['publication_date'] = data['datePublished']
                if 'dateCreated' in data:
                    result['filing_date'] = data['dateCreated']
                if 'creator' in data:
                    if isinstance(data['creator'], list):
                        result['inventors'] = [i.get('name') if isinstance(i, dict) else str(i) for i in data['creator']]
                    else:
                        result['inventors'] = [data['creator']]
                if 'assignee' in data:
                    if isinstance(data['assignee'], dict):
                        result['assignee'] = data['assignee'].get('name')
                    else:
                        result['assignee'] = str(data['assignee'])
        except:
            pass
    
    # 2. 解析 meta 標籤
    meta_map = {
        'citation_publication_date': 'publication_date',
        'citation_patent_number': 'patent_number',
        'citation_title': 'title',
        'citation_abstract': 'abstract',
        'citation_filing_date': 'filing_date',
        'citation_assignee': 'assignee',
    }
    
    for meta_name, target in meta_map.items():
        meta = soup.find('meta', attrs={'name': meta_name})
        if meta and meta.get('content'):
            if not result.get(target):
                result[target] = meta.get('content')
    
    # 3. 從 URL 提取專利號
    if not result.get('patent_number'):
        url_match = re.search(r'patent/([A-Z]{2,4}\d+[A-Z]?)', url)
        if url_match:
            result['patent_number'] = url_match.group(1)
    
    return result

def extract_claim1_from_text(text: str) -> Optional[str]:
    """多模式匹配 Claim 1"""
    patterns = [
        (r'WHAT IS CLAIMED IS:\s*(?:1\.\s*)([\s\S]*?(?:;\s*or\s*[\s\S]*?)+)', "標準格式", 1.0),
        (r'CLAIMS\s*(?:1\.\s*)([\s\S]*?(?:;\s*or\s*[\s\S]*?)+)', "CLAIMS 開頭", 0.9),
        (r'1\.\s+([A-Z][\s\S]{50,20000})', "寬鬆數字", 0.85),
        (r'(?:Claim 1|第 1 項)[:\s]*([\s\S]{50,10000})', "WO 格式", 0.75),
        (r'1\.\s+([\s\S]{50,15000})(?=\n\n2\.|\n\n|\Z)', "最簡保底", 0.7),
    ]
    
    results = []
    for pattern, name, confidence in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            claim = match.group(1).strip()
            if 50 < len(claim) < 20000:
                results.append((claim, name, confidence))
    
    if results:
        results.sort(key=lambda x: x[2], reverse=True)
        return results[0][0]
    return None

def extract_examples_from_text(text: str) -> List[str]:
    """提取實施例"""
    examples = []
    example_pattern = r'(?:Example|EXAMPLE)\s*\d+[:\.\s][\s\S]*?(?=(?:Example|EXAMPLE)\s*\d+|$)'
    matches = re.findall(example_pattern, text, re.IGNORECASE)
    if matches:
        examples.extend([m.strip() for m in matches])
    
    embodiment_pattern = r'(?:In an?|According to an?)(?:\s+)?(?:example|embodiment|implementation)[\s\S]*?(?=(?:In an?|According to an?)(?:\s+)?(?:example|embodiment|implementation)|$)'
    matches = re.findall(embodiment_pattern, text, re.IGNORECASE)
    if matches:
        examples.extend([m.strip() for m in matches])
    
    return examples[:10]

def batch_extract_v10a(search_file: str, output_file: str):
    """批量提取 v10-A"""
    
    with open(search_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    if isinstance(data, list):
        patents = data
    elif isinstance(data, dict) and 'results' in data:
        patents = data['results']
    else:
        patents = [data]
    
    print("=" * 100)
    print("Merck KGaA 負介電液晶專利提取 v10-A（HTML 結構化解析）")
    print("=" * 100)
    
    extracted = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
        )
        
        for i, patent in enumerate(patents, 1):
            if isinstance(patent, str):
                url = patent
            elif isinstance(patent, dict):
                url = patent.get('url') or patent.get('link')
            else:
                continue
            
            if not url:
                continue
            
            print(f"\n[{i}/{len(patents)}] 提取：{url}")
            
            try:
                page = browser.new_page()
                page.goto(url, wait_until='domcontentloaded', timeout=60000)
                
                try:
                    page.wait_for_load_state('networkidle', timeout=10000)
                except:
                    pass
                
                html = page.content()
                text = page.inner_text('body')
                title = page.title()
                
                # 使用結構化解析
                structured = parse_structured_data(html, url)
                
                # 提取 Claim 1
                claim1 = extract_claim1_from_text(text)
                
                # 提取實施例
                examples = extract_examples_from_text(text)
                
                result = {
                    'success': True,
                    'url': url,
                    'patent_number': structured.get('patent_number'),
                    'title': structured.get('title') or title,
                    'publication_date': structured.get('publication_date'),
                    'filing_date': structured.get('filing_date'),
                    'abstract': structured.get('abstract'),
                    'claim_1': claim1,
                    'claim_1_length': len(claim1) if claim1 else 0,
                    'examples': examples,
                    'example_count': len(examples),
                    'text_length': len(text),
                    'method': 'structured_html'
                }
                
                print(f" ✓ 提取成功")
                print(f" 專利號：{result['patent_number'] or 'N/A'}")
                print(f" 公開日：{result['publication_date'] or 'N/A'}")
                print(f" 申請日：{result['filing_date'] or 'N/A'}")
                print(f" Claim 1: {result['claim_1_length']} 字元")
                print(f" 實施例：{result['example_count']} 個")
                
            except Exception as e:
                result = {
                    'success': False,
                    'url': url,
                    'error': str(e),
                    'method': 'structured_html'
                }
                print(f" ✗ 提取失敗：{e}")
            
            finally:
                page.close()
            
            extracted.append(result)
        
        browser.close()
    
    # 保存結果
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(extracted, f, ensure_ascii=False, indent=2)
    
    # 統計
    success_count = sum(1 for p in extracted if p['success'])
    claim1_count = sum(1 for p in extracted if p.get('claim_1'))
    date_count = sum(1 for p in extracted if p.get('publication_date') or p.get('filing_date'))
    
    print("\n" + "=" * 100)
    print("提取統計（v10-A 結構化解析）")
    print("=" * 100)
    print(f" 總提取數量：{success_count}/{len(extracted)}")
    if success_count > 0:
        print(f" Claim 1 提取：{claim1_count}/{len(extracted)} ({claim1_count/len(extracted)*100:.1f}%)")
        print(f" 日期提取：{date_count}/{len(extracted)} ({date_count/len(extracted)*100:.1f}%)")
    print(f" 結果已保存：{output_file}")

if __name__ == '__main__':
    batch_extract_v10a('/tmp/patent_search_results.json', '/tmp/extracted_patents_v10a.json')
