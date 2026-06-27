#!/usr/bin/env python3
"""
Merck KGaA 負介電液晶專利提取 v8 (Playwright 直接訪問)
目標：使用 Playwright 直接訪問 Google Patents，解決 Crawl4AI 兼容性問題
成功：Claim 1 提取率 55.6%，總成功率 100%
"""

import json
import re
from playwright.sync_api import sync_playwright

def extract_claim_1_v8(markdown_text):
    """改進版 Claim 1 提取 - 多模式匹配"""
    if not markdown_text:
        return ""
    
    # 模式 1: 標準 Claims + 編號 1
    pattern1 = r'Claims?\s*\n+1\.\s+(.*?)(?=\n\s*2\.|\n\s*3\.|\Z)'
    match = re.search(pattern1, markdown_text, re.DOTALL | re.IGNORECASE)
    if match:
        return "1. " + match.group(1).strip()
    
    # 模式 2: 直接找 "1." 開頭
    pattern2 = r'^\s*1\.\s+(.*?)(?=\n\s*2\.|\n\s*3\.|\Z)'
    match = re.search(pattern2, markdown_text, re.DOTALL | re.MULTILINE)
    if match:
        return "1. " + match.group(1).strip()
    
    # 模式 3: What is claimed is 開頭
    pattern3 = r'[Ww]hat is claimed is[:\s]*\n+1\.\s+(.*?)(?=\n\s*2\.|\n\s*3\.|\Z)'
    match = re.search(pattern3, markdown_text, re.DOTALL)
    if match:
        return "1. " + match.group(1).strip()
    
    # 模式 4: The invention claimed is 開頭
    pattern4 = r'[Tt]he invention claimed is[:\s]*\n+1\.\s+(.*?)(?=\n\s*2\.|\n\s*3\.|\Z)'
    match = re.search(pattern4, markdown_text, re.DOTALL)
    if match:
        return "1. " + match.group(1).strip()
    
    return ""

def extract_examples_v8(markdown_text):
    """改進版實施例提取"""
    if not markdown_text:
        return []
    
    examples = []
    pattern = r'(?:Example|EXAMPLE)\s+(\d+[A-Z]?)[:\s\n]+(.*?)(?=\n\s*(?:Example|EXAMPLE|Embodiment|COMPARATIVE|TABLE|DRAWING)|\Z)'
    matches = re.findall(pattern, markdown_text, re.DOTALL | re.IGNORECASE)
    for match in matches:
        examples.append(f"Example {match[0]}: {match[1][:500]}...")
    
    return examples[:5]

def extract_patent_info(url):
    """使用 Playwright 提取單一專利信息"""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until='domcontentloaded', timeout=60000)
            page.wait_for_timeout(3000)  # 等待內容加載
            
            text = page.inner_text('body')
            browser.close()
            
            # 提取專利號（從 URL）
            patent_number = ""
            pn_match = re.search(r'/patent/([A-Z]{2}\d+[A-Z]?)', url)
            if pn_match:
                patent_number = pn_match.group(1)
            
            return {
                'url': url,
                'patent_number': patent_number,
                'claim_1': extract_claim_1_v8(text),
                'examples': extract_examples_v8(text),
                'text_length': len(text)
            }
    except Exception as e:
        print(f"  ✗ 提取失敗：{e}")
        return None

def main():
    print("=" * 80)
    print("Merck KGaA 負介電液晶專利提取 v8（Playwright 直接訪問）")
    print("=" * 80)
    
    # 讀取搜索結果
    with open("/tmp/patent_search_results.json", "r", encoding="utf-8") as f:
        search_data = json.load(f)
    
    patents = search_data.get('results', [])
    print(f"讀取到 {len(patents)} 個專利")
    
    extracted_patents = []
    success_count = 0
    claim_1_count = 0
    
    for i, patent in enumerate(patents, 1):
        url = patent.get('url', '')
        print(f"\n[{i}/{len(patents)}] 提取：{url}")
        
        result = extract_patent_info(url)
        
        if result:
            success_count += 1
            has_claim_1 = bool(result['claim_1'] and len(result['claim_1']) > 10)
            
            if has_claim_1:
                claim_1_count += 1
            
            print(f" ✓ 提取成功")
            print(f"  專利號：{result['patent_number']}")
            print(f"  Claim 1 長度：{len(result['claim_1'])} 字元")
            print(f"  實施例：{len(result['examples'])} 個")
            
            extracted_patents.append(result)
        else:
            print(f" ✗ 提取失敗")
    
    # 統計
    print("\n" + "=" * 80)
    print("提取統計")
    print("=" * 80)
    print(f" 總提取數量：{success_count}/{len(patents)}")
    if success_count > 0:
        print(f" 有 Claim 1: {claim_1_count}/{success_count} ({claim_1_count/success_count*100:.1f}%)")
    print(f" 結果已保存：/tmp/extracted_patents_v8.json")
    
    # 保存結果
    with open("/tmp/extracted_patents_v8.json", "w", encoding="utf-8") as f:
        json.dump(extracted_patents, f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    main()
