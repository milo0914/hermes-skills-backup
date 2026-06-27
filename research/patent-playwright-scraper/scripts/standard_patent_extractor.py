#!/usr/bin/env python3
"""
標準 Playwright 專利提取腳本
適用於 Google Patents、USPTO、Justia 等專利網站

用法：
    python standard_patent_extractor.py <input_json> <output_json>
    
輸入格式 (JSON):
    [
        {"url": "https://patents.google.com/patent/US8399073B2/en"},
        {"url": "https://patents.google.com/patent/US5576867A/en"}
    ]
    
輸出格式 (JSON):
    [
        {
            "url": "https://patents.google.com/patent/US8399073B2/en",
            "patent_number": "US8399073B2",
            "title": "...",
            "claim1": "...",
            "claim1_length": 123,
            "examples": ["...", "..."],
            "example_count": 2,
            "success": true
        }
    ]
"""

import sys
import json
import time
import re
from pathlib import Path
from typing import Optional, List, Dict
from playwright.sync_api import sync_playwright


def extract_patent_number(text: str, url: str) -> Optional[str]:
    """提取專利號"""
    # 從 URL 提取
    url_patterns = [
        r'patents\.google\.com/patent/([A-Z]{2,4}\d+[A-Z]?(?:\d{0,2})?)',
        r'uspto\.gov/patent/([A-Z]{2}\d+)',
        r'justia\.com/patents/\d+/([A-Z]+\d+)',
    ]
    
    for pattern in url_patterns:
        match = re.search(pattern, url, re.IGNORECASE)
        if match:
            return match.group(1).upper()
    
    # 從文本提取
    text_patterns = [
        r'(?:Patent number|US Patent|專利號)[:\s]*([A-Z]{2,4}\d+[A-Z]?(?:\d{0,2})?)',
        r'([A-Z]{2}\d+[A-Z]?(?:\d{0,2})?)\s*(?:B2|B1|A|A1|A2)?\s*(?:issued|granted)',
    ]
    
    for pattern in text_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).upper()
    
    return None


def extract_claim1(text: str) -> Optional[str]:
    """多模式匹配 Claim 1"""
    patterns = [
        # 模式 1: 標準 Google Patents 格式
        r'WHAT IS CLAIMED IS:\s*(?:1\.\s*)([\s\S]*?(?:;\s*or\s*[\s\S]*?)+)',
        # 模式 2: CLAIMS 開頭
        r'CLAIMS\s*(?:1\.\s*)([\s\S]*?(?:;\s*or\s*[\s\S]*?)+)',
        # 模式 3: 簡單數字開頭
        r'1\.\s+([\s\S]*?(?:;\s*or\s*[\s\S]*?)+)',
        # 模式 4: 到下一項為止
        r'WHAT IS CLAIMED IS:\s*1\.\s+([\s\S]*?(?=2\.|$))',
        # 模式 5: 最簡格式
        r'1\.\s+([\s\S]*?(?=2\.|$))'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            claim1 = match.group(1).strip()
            # 清理多餘空白
            claim1 = re.sub(r'\s+', ' ', claim1)
            if len(claim1) > 50:  # 合理長度
                return claim1
    
    return None


def extract_examples(text: str) -> List[str]:
    """提取實施例/實施方式"""
    examples = []
    
    # 模式 1: Example 1, Example 2...
    example_pattern = r'(?:Example|EXAMPLE)\s*\d+[:\.\s][\s\S]*?(?=(?:Example|EXAMPLE)\s*\d+|$)'
    matches = re.findall(example_pattern, text, re.IGNORECASE)
    if matches:
        examples.extend([m.strip() for m in matches])
    
    # 模式 2: Embodiment
    embodiment_pattern = r'(?:In an?|According to an?)(?:\s+)?(?:example|embodiment|implementation)[\s\S]*?(?=(?:In an?|According to an?)(?:\s+)?(?:example|embodiment|implementation)|$)'
    matches = re.findall(embodiment_pattern, text, re.IGNORECASE)
    if matches:
        examples.extend([m.strip() for m in matches])
    
    # 模式 3: 具體實施方式標題下
    section_pattern = r'(?:DETAILED DESCRIPTION|具體實施方式|實施例)[\s\S]*?(?=\b(?:WHAT IS CLAIMED|CLAIMS|摘要|ABSTRACT)\b|$)'
    match = re.search(section_pattern, text, re.IGNORECASE)
    if match:
        section_text = match.group(0)
        # 提取段落
        paragraphs = re.split(r'\n\s*\n', section_text)
        examples.extend([p.strip() for p in paragraphs if len(p.strip()) > 100])
    
    return examples[:10]  # 限制最多 10 個


def extract_patent_info(url: str, browser) -> Dict:
    """使用 Playwright 提取專利信息"""
    
    try:
        page = browser.new_page(
            user_agent='Mozilla/5.0 (Windows NT 110.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        
        # 訪問頁面
        page.goto(url, wait_until='domcontentloaded', timeout=60000)
        
        # 等待關鍵元素加載
        try:
            page.wait_for_selector('h1, .title', timeout=10000)
        except:
            pass  # 超時也繼續
        
        # 獲取頁面內容
        text = page.inner_text('body')
        title = page.title()
        
        # 提取信息
        patent_number = extract_patent_number(text, url)
        claim1 = extract_claim1(text)
        examples = extract_examples(text)
        
        # 提取日期
        pub_date_match = re.search(r'(?:Publication date|公開日期)[:\s]*(\d{4}-\d{2}-\d{2})', text)
        pub_date = pub_date_match.group(1) if pub_date_match else None
        
        return {
            'success': True,
            'url': url,
            'patent_number': patent_number,
            'title': title,
            'publication_date': pub_date,
            'claim1': claim1,
            'claim1_length': len(claim1) if claim1 else 0,
            'examples': examples,
            'example_count': len(examples),
            'raw_text_length': len(text)
        }
        
    except Exception as e:
        return {
            'success': False,
            'url': url,
            'error': str(e)
        }
    finally:
        try:
            page.close()
        except:
            pass


def batch_extract(input_file: str, output_file: str):
    """批量提取專利信息"""
    
    # 讀取輸入
    with open(input_file, 'r', encoding='utf-8') as f:
        patents = json.load(f)
    
    # 標準化輸入格式
    if isinstance(patents, dict):
        patents = [patents]
    
    print(f"讀取到 {len(patents)} 個專利")
    
    extracted = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-accelerated-2d-canvas',
                '--disable-gpu'
            ]
        )
        
        for i, patent in enumerate(patents, 1):
            url = patent.get('url') or patent.get('link')
            if not url:
                print(f"[{i}/{len(patents)}] 跳過：無 URL")
                continue
            
            print(f"\n[{i}/{len(patents)}] 提取：{url}")
            
            result = extract_patent_info(url, browser)
            
            if result['success']:
                print(f" ✓ 提取成功 - 專利號：{result.get('patent_number') or 'N/A'}")
                print(f"   Claim 1 長度：{result['claim1_length']} 字元")
                print(f"   實施例：{result['example_count']} 個")
            else:
                print(f" ✗ 提取失敗：{result.get('error', 'Unknown error')}")
            
            extracted.append(result)
            
            # 禮貌延遲
            time.sleep(1.5)
        
        browser.close()
    
    # 保存結果
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(extracted, f, ensure_ascii=False, indent=2)
    
    # 統計
    success_count = sum(1 for p in extracted if p['success'])
    claim1_count = sum(1 for p in extracted if p.get('claim1'))
    
    print("\n" + "="*80)
    print("提取統計")
    print("="*80)
    print(f" 總提取數量：{success_count}/{len(extracted)}")
    print(f" 有 Claim 1: {claim1_count}/{len(extracted)} ({claim1_count/len(extracted)*100:.1f}%)")
    print(f" 結果已保存：{output_file}")


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2]
    
    batch_extract(input_file, output_file)
