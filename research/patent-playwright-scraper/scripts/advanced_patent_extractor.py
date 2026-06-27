#!/usr/bin/env python3
"""
進階 Playwright 專利提取腳本
特點：
- 支持並發提取（多瀏覽器實例）
- 自動重試機制
- 進度保存（中斷後可繼續）
- 詳細的錯誤報告

用法：
    python advanced_patent_extractor.py <input_json> <output_json> [--workers 3] [--retries 2]
"""

import sys
import json
import time
import argparse
from pathlib import Path
from typing import Optional, List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed
from playwright.sync_api import sync_playwright


def extract_patent_number(text: str, url: str) -> Optional[str]:
    """提取專利號"""
    url_patterns = [
        r'patents\.google\.com/patent/([A-Z]{2,4}\d+[A-Z]?(?:\d{0,2})?)',
        r'uspto\.gov/patent/([A-Z]{2}\d+)',
    ]
    
    for pattern in url_patterns:
        match = re.search(pattern, url, re.IGNORECASE)
        if match:
            return match.group(1).upper()
    
    text_patterns = [
        r'(?:Patent number|US Patent|專利號)[:\s]*([A-Z]{2,4}\d+[A-Z]?(?:\d{0,2})?)',
    ]
    
    for pattern in text_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).upper()
    
    return None


def extract_claim1(text: str) -> Optional[str]:
    """多模式匹配 Claim 1"""
    patterns = [
        r'WHAT IS CLAIMED IS:\s*(?:1\.\s*)([\s\S]*?(?:;\s*or\s*[\s\S]*?)+)',
        r'CLAIMS\s*(?:1\.\s*)([\s\S]*?(?:;\s*or\s*[\s\S]*?)+)',
        r'1\.\s+([\s\S]*?(?:;\s*or\s*[\s\S]*?)+)',
        r'WHAT IS CLAIMED IS:\s*1\.\s+([\s\S]*?(?=2\.|$))',
        r'1\.\s+([\s\S]*?(?=2\.|$))'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            claim1 = match.group(1).strip()
            claim1 = re.sub(r'\s+', ' ', claim1)
            if len(claim1) > 50:
                return claim1
    
    return None


def extract_examples(text: str) -> List[str]:
    """提取實施例"""
    examples = []
    
    # Example 模式
    example_pattern = r'(?:Example|EXAMPLE)\s*\d+[:\.\s][\s\S]*?(?=(?:Example|EXAMPLE)\s*\d+|$)'
    matches = re.findall(example_pattern, text, re.IGNORECASE)
    if matches:
        examples.extend([m.strip() for m in matches])
    
    # Embodiment 模式
    embodiment_pattern = r'(?:In an?|According to an?)(?:\s+)?(?:example|embodiment|implementation)[\s\S]*?(?=(?:In an?|According to an?)(?:\s+)?(?:example|embodiment|implementation)|$)'
    matches = re.findall(embodiment_pattern, text, re.IGNORECASE)
    if matches:
        examples.extend([m.strip() for m in matches])
    
    return examples[:10]


def extract_single(url: str, max_retries: int = 2) -> Dict:
    """提取單一專利（含重試機制）"""
    
    for attempt in range(max_retries + 1):
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=['--no-sandbox', '--disable-setuid-sandbox']
                )
                
                try:
                    page = browser.new_page(
                        user_agent='Mozilla/5.0 (Windows NT 110.0; Win64; x64) AppleWebKit/537.36'
                    )
                    
                    page.goto(url, wait_until='domcontentloaded', timeout=60000)
                    
                    try:
                        page.wait_for_selector('h1', timeout=10000)
                    except:
                        pass
                    
                    text = page.inner_text('body')
                    title = page.title()
                    
                    patent_number = extract_patent_number(text, url)
                    claim1 = extract_claim1(text)
                    examples = extract_examples(text)
                    
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
                        'attempts': attempt + 1
                    }
                    
                finally:
                    browser.close()
                    
        except Exception as e:
            if attempt == max_retries:
                return {
                    'success': False,
                    'url': url,
                    'error': str(e),
                    'attempts': attempt + 1
                }
            time.sleep(2 ** attempt)  # 指數退避
    
    return {'success': False, 'url': url, 'error': 'Max retries exceeded'}


def batch_extract_advanced(input_file: str, output_file: str, workers: int = 3, retries: int = 2):
    """批量提取（進階版：並發 + 重試 + 進度保存）"""
    
    # 讀取輸入
    with open(input_file, 'r', encoding='utf-8') as f:
        patents = json.load(f)
    
    if isinstance(patents, dict):
        patents = [patents]
    
    # 檢查進度
    progress_file = output_file + '.progress'
    completed_urls = set()
    
    if Path(progress_file).exists():
        with open(progress_file, 'r', encoding='utf-8') as f:
            progress_data = json.load(f)
            completed_urls = {p['url'] for p in progress_data if p.get('success')}
        print(f"載入進度：{len(completed_urls)} 個已完成")
    
    # 過濾已完成的
    pending = [p for p in patents if (p.get('url') or p.get('link')) not in completed_urls]
    already_done = len(patents) - len(pending)
    
    print(f"讀取到 {len(patents)} 個專利")
    print(f"待處理：{len(pending)} 個 (已完成 {already_done} 個)")
    
    extracted = []
    
    # 載入已完成的
    if completed_urls:
        with open(progress_file, 'r', encoding='utf-8') as f:
            extracted = json.load(f)
    
    # 並發提取
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {}
        
        for i, patent in enumerate(pending):
            url = patent.get('url') or patent.get('link')
            if not url:
                continue
            
            future = executor.submit(extract_single, url, retries)
            futures[future] = url
        
        for i, future in enumerate(as_completed(futures), 1):
            url = futures[future]
            result = future.result()
            
            if result['success']:
                print(f"[{i}/{len(pending)}] ✓ {url} - 專利號：{result.get('patent_number') or 'N/A'}")
            else:
                print(f"[{i}/{len(pending)}] ✗ {url} - {result.get('error', 'Unknown')}")
            
            extracted.append(result)
            
            # 保存進度
            with open(progress_file, 'w', encoding='utf-8') as f:
                json.dump(extracted, f, ensure_ascii=False, indent=2)
            
            time.sleep(0.5)  # 延遲
    
    # 最終保存
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(extracted, f, ensure_ascii=False, indent=2)
    
    # 清理進度文件
    if Path(progress_file).exists():
        Path(progress_file).unlink()
    
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
    parser = argparse.ArgumentParser(description='進階專利提取工具')
    parser.add_argument('input', help='輸入 JSON 文件')
    parser.add_argument('output', help='輸出 JSON 文件')
    parser.add_argument('--workers', type=int, default=3, help='並發 worker 數量')
    parser.add_argument('--retries', type=int, default=2, help='重試次數')
    
    args = parser.parse_args()
    
    batch_extract_advanced(args.input, args.output, args.workers, args.retries)
