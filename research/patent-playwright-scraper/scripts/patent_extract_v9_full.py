#!/usr/bin/env python3
"""
Merck KGaA 負介電液晶專利提取 v9 - 完整改進版
測試所有改進方案：
- 方案 A: 6 種 Claim 1 正則模式 + 置信度評分
- 方案 B: 多策略實施例提取
- 方案 C: 多格式日期解析
"""

import re
import json
import time
from typing import Optional, List, Dict, Tuple
from playwright.sync_api import sync_playwright


# ========== 方案 A: 改進 Claim 1 提取 ==========

CLAIM1_PATTERNS = [
    # 模式 1: 標準 Google Patents 格式
    (r'WHAT IS CLAIMED IS:\s*(?:1\.\s*)([\s\S]{50,}?(?:;\s*or\s*[\s\S]*?)*?(?=\n\n2\.|\n\nCLAIMS|\n\nABSTRACT|$))', "標準格式", 1.0),
    
    # 模式 2: CLAIMS 開頭
    (r'(?<!WHAT IS CLAIMED IS:\s*)CLAIMS\s*(?:1\.\s*)([\s\S]{50,}?(?=\n\n2\.|\n\nABSTRACT|$))', "CLAIMS 開頭", 0.9),
    
    # 模式 3: 寬鬆數字開頭 (到 2. 或合理長度)
    (r'1\.\s+([^\n]{30,}?(?:\n[^\n]*){1,10}?(?=\n\n2\.|\n\n|\Z))', "寬鬆數字", 0.8),
    
    # 模式 4: 中文專利格式
    (r'申請專利範圍\s*1\.([\s\S]{30,}?(?=2\.|$))', "中文格式", 0.85),
    
    # 模式 5: WO 格式
    (r'(?:Claim 1|第 1 項)\s*[:\.\s]*([\s\S]{50,}?(?=2\.|摘要|ABSTRACT|$))', "WO 格式", 0.75),
    
    # 模式 6: 最簡格式 (保底)
    (r'1\.\s+([\s\S]{50,}?(?=\n\n2\.|\n\n|\Z))', "最簡保底", 0.7),
]

def extract_claim1_v9(text: str) -> Tuple[Optional[str], str, float]:
    """方案 A: 6 種模式 + 置信度評分"""
    results = []
    
    for pattern, pattern_name, base_confidence in CLAIM1_PATTERNS:
        try:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                claim1 = match.group(1).strip()
                claim1 = re.sub(r'\s+', ' ', claim1)
                
                # 長度篩選 (至少 50 字元)
                if len(claim1) < 50:
                    continue
                
                # 置信度調整
                confidence = base_confidence
                
                # 關鍵詞加分
                keywords = ['comprising', 'wherein', 'characterized by', '包括', '特徵在於']
                if any(kw in claim1.lower() for kw in keywords):
                    confidence += 0.15
                
                # 化學式加分
                if re.search(r'[A-Z]-\d-[A-Z]|wt%|molecular', claim1, re.IGNORECASE):
                    confidence += 0.1
                
                # 長度適中加分 (100-2000 字元)
                if 100 <= len(claim1) <= 2000:
                    confidence += 0.05
                
                results.append((claim1, pattern_name, min(confidence, 1.0)))
        except Exception:
            continue
    
    if not results:
        return None, "無匹配", 0.0
    
    # 選擇置信度最高
    results.sort(key=lambda x: x[2], reverse=True)
    return results[0]


# ========== 方案 B: 改進實施例提取 ==========

def extract_examples_v9(text: str) -> List[str]:
    """方案 B: 多策略實施例提取"""
    examples = []
    
    # 策略 1: Example 標題 + 表格格式
    example_pattern = r'(?:Example|EXAMPLE)\s*\d+[:\.\s][\s\S]{50,}?(?=(?:Example|EXAMPLE)\s*\d+|$)'
    matches = re.findall(example_pattern, text, re.IGNORECASE)
    if matches:
        examples.extend([m.strip() for m in matches if len(m.strip()) > 50])
    
    # 策略 2: 實施例段落
    embodiment_pattern = r'(?:In an?|According to an?)(?:\s+)?(?:example|embodiment|implementation)[\s\S]{100,}?(?=(?:In an?|According to an?))'
    matches = re.findall(embodiment_pattern, text, re.IGNORECASE)
    if matches:
        examples.extend([m.strip() for m in matches])
    
    # 策略 3: 表格格式實施例
    table_pattern = r'(?:Table|TABLE)\s*\d+[:\.\s][\s\S]{100,}?(?=(?:Table|TABLE)\s*\d+|$)'
    matches = re.findall(table_pattern, text, re.IGNORECASE)
    if matches:
        examples.extend([m.strip() for m in matches])
    
    # 策略 4: 具體實施方式
    section_pattern = r'(?:DETAILED DESCRIPTION|具體實施方式|實施例)[\s\S]{500,}?(?=\b(?:WHAT IS CLAIMED|CLAIMS|摘要|ABSTRACT)\b|$)'
    match = re.search(section_pattern, text, re.IGNORECASE)
    if match:
        section_text = match.group(0)
        paragraphs = re.split(r'\n\s*\n', section_text)
        examples.extend([p.strip() for p in paragraphs if 100 < len(p.strip()) < 5000])
    
    # 去重並限制數量
    seen = set()
    unique_examples = []
    for ex in examples:
        if ex not in seen and len(ex) > 50:
            seen.add(ex)
            unique_examples.append(ex)
    
    return unique_examples[:10]


# ========== 方案 C: 改進日期提取 ==========

def extract_dates_v9(text: str) -> Dict[str, str]:
    """方案 C: 多格式日期解析"""
    dates = {}
    
    # 公開日
    pub_patterns = [
        r'(?:Publication date|公開日期|公告日)[:\s]*(\d{4}-\d{2}-\d{2})',
        r'(?:Publication date|公開日期|公告日)[:\s]*(\d{1,2}/\d{1,2}/\d{4})',
        r'(\d{4}年\d{1,2}月\d{1,2}日)',
    ]
    
    for pattern in pub_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            dates['publication_date'] = match.group(1)
            break
    
    # 申請日
    filing_patterns = [
        r'(?:Filing date|申請日|出願日)[:\s]*(\d{4}-\d{2}-\d{2})',
        r'(?:Filing date|申請日|出願日)[:\s]*(\d{1,2}/\d{1,2}/\d{4})',
        r'申請日[:\s]*(\d{4}年\d{1,2}月\d{1,2}日)',
    ]
    
    for pattern in filing_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            dates['filing_date'] = match.group(1)
            break
    
    # 優先權日
    priority_patterns = [
        r'(?:Priority date|優先權日)[:\s]*(\d{4}-\d{2}-\d{2})',
        r'(?:Priority date|優先權日)[:\s]*(\d{1,2}/\d{1,2}/\d{4})',
    ]
    
    for pattern in priority_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            dates['priority_date'] = match.group(1)
            break
    
    return dates


# ========== 完整提取流程 ==========

def extract_patent_v9(url: str) -> Dict:
    """完整提取流程 v9"""
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        try:
            # 訪問頁面
            page.goto(url, wait_until='domcontentloaded', timeout=60000)
            
            # 等待頁面加載 (使用更寬鬆的條件)
            try:
                page.wait_for_load_state('networkidle', timeout=10000)
            except:
                pass  # 超時也繼續
            
            text = page.inner_text('body')
            title = page.title()
            
            # 方案 A: Claim 1 提取
            claim1, pattern_name, confidence = extract_claim1_v9(text)
            
            # 方案 B: 實施例提取
            examples = extract_examples_v9(text)
            
            # 方案 C: 日期提取
            dates = extract_dates_v9(text)
            
            # 專利號提取
            patent_num_match = re.search(r'([A-Z]{2,4}\d+[A-Z]?)', title)
            patent_number = patent_num_match.group(1) if patent_num_match else None
            
            return {
                'success': True,
                'url': url,
                'patent_number': patent_number,
                'title': title,
                'claim_1': claim1,
                'claim_1_pattern': pattern_name,
                'claim_1_confidence': confidence,
                'claim_1_length': len(claim1) if claim1 else 0,
                'examples': examples,
                'example_count': len(examples),
                'dates': dates,
                'text_length': len(text)
            }
            
        except Exception as e:
            return {
                'success': False,
                'url': url,
                'error': str(e)
            }
        finally:
            browser.close()


def batch_extract_v9(search_file: str, output_file: str):
    """批量提取 v9"""
    
    with open(search_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 兼容兩種格式
    if isinstance(data, list):
        patents = data
    elif isinstance(data, dict) and 'results' in data:
        patents = data['results']
    else:
        patents = [data]
    
    print("=" * 100)
    print("Merck KGaA 負介電液晶專利提取 v9 (完整改進版)")
    print("測試方案：A(Claim1 正則) + B(實施例) + C(日期)")
    print("=" * 100)
    
    extracted = []
    
    for i, patent in enumerate(patents, 1):
        # 兼容兩種格式
        if isinstance(patent, str):
            url = patent
        elif isinstance(patent, dict):
            url = patent.get('url') or patent.get('link')
        else:
            continue
        
        if not url:
            continue
        
        print(f"\n[{i}/{len(patents)}] 提取：{url}")
        
        result = extract_patent_v9(url)
        
        if result['success']:
            print(f"  ✓ 提取成功")
            print(f"    專利號：{result['patent_number'] or 'N/A'}")
            print(f"    Claim 1: {result['claim_1_length']} 字元 (模式：{result['claim_1_pattern']}, 置信度：{result['claim_1_confidence']:.2f})")
            print(f"    實施例：{result['example_count']} 個")
            print(f"    日期：{result['dates']}")
        else:
            print(f"  ✗ 提取失敗：{result.get('error', 'Unknown')}")
        
        extracted.append(result)
        time.sleep(1.5)  # 禮貌延遲
    
    # 保存結果
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(extracted, f, ensure_ascii=False, indent=2)
    
    # 統計
    success_count = sum(1 for p in extracted if p['success'])
    claim1_count = sum(1 for p in extracted if p.get('claim_1'))
    example_count = sum(1 for p in extracted if p.get('example_count', 0) > 0)
    
    print("\n" + "=" * 100)
    print("提取統計")
    print("=" * 100)
    print(f"  總提取數量：{success_count}/{len(extracted)}")
    print(f"  Claim 1 提取：{claim1_count}/{len(extracted)} ({claim1_count/len(extracted)*100:.1f}%)")
    print(f"  實施例提取：{example_count}/{len(extracted)} ({example_count/len(extracted)*100:.1f}%)")
    print(f"  結果已保存：{output_file}")
    
    return extracted


if __name__ == '__main__':
    import sys
    
    search_file = sys.argv[1] if len(sys.argv) > 1 else '/tmp/patent_search_results.json'
    output_file = sys.argv[2] if len(sys.argv) > 2 else '/tmp/extracted_patents_v9.json'
    
    batch_extract_v9(search_file, output_file)
