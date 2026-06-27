#!/usr/bin/env python3
"""
Merck KGaA 負介電液晶專利提取 v11 - 改進版

核心改進（相較 v10-A）：
1. 實施例定位與提取：
   - 從 Playwright 取得 FULL TEXT（無截斷），解決 v9/v10 description 被 50k 字截斷的問題
   - 實施例必定在專利後半段（段落編號通常 > 0150）
   - 關鍵字定位：Example / Embodiment / Working Example / Synthesis Example
   - 多級提取：先定位段落，再提取內容，最後評判品質
   - 每篇專利都必有實施例（專利法規範），抓取為 0 = 方法有問題

2. 介電常數 dielectric constant 正負值判斷：
   - 三級證據源：abstract > claims > examples
   - abstract 最權威（專利核心定性描述）
   - claims 次之（法律界定）
   - examples 提供量化佐證（Δε 實測值）
   - 避免 description 中上下文提及對比技術（positive DA）造成誤判
   - VA/IPS/FFS 顯示模式僅作輔助參考，不作為主要判斷依據

作者：Hermes Agent
版本：v11
日期：2026-06-03
"""

import re
import json
import time
from typing import Optional, List, Dict, Tuple
from playwright.sync_api import sync_playwright


# ============================================================
# Part 1: 全文提取（解決 description 截斷問題）
# ============================================================

def fetch_full_patent_text(url: str, max_scroll: int = 50) -> Dict[str, Any]:
    """
    使用 Playwright 獲取專利全文。
    
    關鍵改進：
    - 滾動載入完整頁面（Google Patents 懶加載）
    - 取得完整 body text（不限 50k/80k 字元）
    - 同時取得 HTML 用於結構化解析
    """
    from typing import Any
    
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
        
        page = browser.new_page(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        
        try:
            page.goto(url, wait_until='domcontentloaded', timeout=60000)
            
            # 等待主要內容載入
            try:
                page.wait_for_load_state('networkidle', timeout=15000)
            except:
                pass
            
            # 滾動頁面以觸發懶加載
            for i in range(max_scroll):
                page.evaluate('window.scrollBy(0, 3000)')
                time.sleep(0.3)
            
            # 滾回頂部
            page.evaluate('window.scrollTo(0, 0)')
            time.sleep(0.5)
            
            # 獲取完整文本和 HTML
            html = page.content()
            text = page.inner_text('body')
            title = page.title()
            
            return {
                'success': True,
                'url': url,
                'html': html,
                'text': text,
                'title': title,
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


# ============================================================
# Part 2: 實施例定位、提取與評判
# ============================================================

def locate_example_section(text: str) -> Dict[str, Any]:
    """
    定位實施例區段在全文中的位置。
    
    專利結構規律：
    - 前半段：Title, Abstract, Background, Summary, Description of Embodiments
    - 後半段：Examples (Working Examples, Synthesis Examples, Comparative Examples)
    - 末尾：Claims
    
    定位策略：
    1. 找 "Example" 關鍵字第一次出現的位置
    2. 找段落編號 > 0150 的區域（通常 examples 從高編號段落開始）
    3. 找 "Detailed Description" 之後的段落
    """
    result = {
        'example_section_start': None,
        'example_section_end': None,
        'relative_position': None,
        'locating_method': None,
        'section_preview': None
    }
    
    total_len = len(text)
    if total_len == 0:
        return result
    
    # 策略 1: 找 "Example 1" / "EXAMPLE 1" / "Working Example" / "Example I"
    # 重要：排除 "for example" 的日常用法（非專利實施例）
    # 專利實施例的 "Example" 特徵：
    #   - "Example 1"（數字編號，通常在句首或段落起始）
    #   - "Synthesis Example 1" / "Working Example 1" / "Comparative Example 1"
    #   - 位於專利後半段（relative position > 0.3）
    #   - 不是 "for example" / "such as, for example" 等插入語
    example_start_patterns = [
        # 帶類型前綴的實施例（最可靠）
        (r'(?<!for\s)(?<!for\s\s)(?<!such\sas\s)\b(?:Working\s+)?Example\s+1\b(?!\s+transistor)(?!\s+thin)', 'Example 1'),
        (r'(?<!for\s)(?<!such\sas\s)\b(?:WORKING\s+)?EXAMPLE\s+1\b', 'EXAMPLE 1'),
        (r'(?<!for\s)(?<!such\sas\s)\bExample\s+I\b', 'Example I'),
        (r'\bSynthesis\s+Example\s+1\b', 'Synthesis Example 1'),
        (r'\bFormulation\s+Example\s+1\b', 'Formulation Example 1'),
        (r'\bPreparation\s+Example\s+1\b', 'Preparation Example 1'),
        (r'\bComparative\s+Example\s+1\b', 'Comparative Example 1'),
        (r'\bApplication\s+Example\s+1\b', 'Application Example 1'),
    ]
    
    for pattern, method_name in example_start_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            pos = match.start()
            rel_pos = round(pos / total_len, 3)
            
            # 驗證：實施例應在後半段（> 0.4）
            if rel_pos >= 0.3:  # 放寬到 0.3，因為有些專利 description 較短
                result['example_section_start'] = pos
                result['relative_position'] = rel_pos
                result['locating_method'] = method_name
                
                # 找 section end（到 Claims 或文件結尾）
                claims_match = re.search(r'\b(?:WHAT IS CLAIMED IS|CLAIMS|申請專利範圍)\b', text[pos:])
                if claims_match:
                    result['example_section_end'] = pos + claims_match.start()
                else:
                    result['example_section_end'] = total_len
                
                # 預覽
                preview_start = max(0, pos - 50)
                preview_end = min(total_len, pos + 300)
                result['section_preview'] = text[preview_start:preview_end]
                
                return result
    
    # 策略 2: 找高段落編號區域（[0150] 之後）中的 example 關鍵字
    high_para_match = re.search(r'\[0(?:1[5-9]\d|2\d\d|3\d\d)\]', text)
    if high_para_match:
        search_from = high_para_match.start()
        # 在此位置之後找 "Example" 關鍵字
        example_match = re.search(r'\bExample\b', text[search_from:], re.IGNORECASE)
        if example_match:
            pos = search_from + example_match.start()
            result['example_section_start'] = pos
            result['relative_position'] = round(pos / total_len, 3)
            result['locating_method'] = 'high_paragraph_number'
            
            claims_match = re.search(r'\b(?:WHAT IS CLAIMED IS|CLAIMS)\b', text[pos:])
            result['example_section_end'] = pos + claims_match.start() if claims_match else total_len
            
            preview_start = max(0, pos - 50)
            preview_end = min(total_len, pos + 300)
            result['section_preview'] = text[preview_start:preview_end]
            
            return result
    
    # 策略 3: 在文本後 40% 找任何 "Example" 或 "embodiment" 關鍵字
    search_zone = text[int(total_len * 0.4):]
    zone_match = re.search(r'\b(?:Example|Embodiment)\b', search_zone, re.IGNORECASE)
    if zone_match:
        pos = int(total_len * 0.4) + zone_match.start()
        result['example_section_start'] = pos
        result['relative_position'] = round(pos / total_len, 3)
        result['locating_method'] = 'rear_zone_keyword'
        
        claims_match = re.search(r'\b(?:WHAT IS CLAIMED IS|CLAIMS)\b', text[pos:])
        result['example_section_end'] = pos + claims_match.start() if claims_match else total_len
        
        preview_start = max(0, pos - 50)
        preview_end = min(total_len, pos + 300)
        result['section_preview'] = text[preview_start:preview_end]
    
    return result


def extract_examples_v11(text: str) -> Dict[str, Any]:
    """
    v11 實施例提取：定位 + 提取 + 評判
    
    改進點：
    1. 先定位再提取，避免在全文中盲目搜索
    2. 多類型實施例識別（Working Example, Synthesis Example, Comparative Example 等）
    3. 提取每個 example 的標題 + 內容
    4. 評判：如果提取為 0，標記為 extraction_failure（因為每篇專利必有實施例）
    """
    result = {
        'examples': [],
        'example_count': 0,
        'example_types': [],
        'has_working_examples': False,
        'has_synthesis_examples': False,
        'has_comparative_examples': False,
        'extraction_quality': 'unknown',  # 'good', 'partial', 'failure'
        'max_example_number': 0,
        'section_location': None,
    }
    
    # Step 1: 定位實施例區段
    location = locate_example_section(text)
    result['section_location'] = location
    
    if location['example_section_start'] is None:
        result['extraction_quality'] = 'failure'
        # 即使定位失敗，仍嘗試在全文搜索（保底策略）
        example_section = text
    else:
        start = location['example_section_start']
        end = location['example_section_end'] or len(text)
        example_section = text[start:end]
    
    # Step 2: 提取各類實施例
    all_examples = []
    
    # 2a: Working / Application Examples（配方 + 物理參數表格）
    working_pattern = r'((?:Working\s+|Application\s+)?Example\s+(\d+)[\.:\s][\s\S]*?)(?=(?:Working\s+|Application\s+)?Example\s+\d+|Comparative\s+Example|Synthesis\s+Example|WHAT IS CLAIMED|CLAIMS|$)'
    working_matches = re.finditer(working_pattern, example_section, re.IGNORECASE)
    for match in working_matches:
        content = match.group(1).strip()
        num = int(match.group(2)) if match.group(2) else 0
        if len(content) > 30:
            all_examples.append({
                'type': 'working_example',
                'number': num,
                'content': content[:5000],  # 限制單個 example 長度
                'content_length': len(content),
                'has_table': bool(re.search(r'Δ[εn]|Clearing\s+point|γ1|K\d|V[0HV]', content)),
                'has_dielectric_value': bool(re.search(r'Δε|Δ[εε]|dielectric\s+anisotropy', content, re.IGNORECASE)),
            })
    
    # 2b: Comparative Examples
    comp_pattern = r'(Comparative\s+Example\s+(\d+)[\.:\s][\s\S]*?)(?=(?:Comparative\s+)?Example\s+\d+|WHAT IS CLAIMED|CLAIMS|$)'
    comp_matches = re.finditer(comp_pattern, example_section, re.IGNORECASE)
    for match in comp_matches:
        content = match.group(1).strip()
        num = int(match.group(2)) if match.group(2) else 0
        if len(content) > 30:
            all_examples.append({
                'type': 'comparative_example',
                'number': num,
                'content': content[:5000],
                'content_length': len(content),
                'has_table': bool(re.search(r'Δ[εn]|Clearing\s+point|γ1|K\d', content)),
                'has_dielectric_value': bool(re.search(r'Δε|Δ[εε]|dielectric\s+anisotropy', content, re.IGNORECASE)),
            })
    
    # 2c: Synthesis Examples（化合物合成步驟）
    synth_pattern = r'(Synthesis\s+Example\s+(\d+)[\.:\s][\s\S]*?)(?=Synthesis\s+Example\s+\d+|(?:Working\s+|Application\s+)?Example\s+\d+|WHAT IS CLAIMED|CLAIMS|$)'
    synth_matches = re.finditer(synth_pattern, example_section, re.IGNORECASE)
    for match in synth_matches:
        content = match.group(1).strip()
        num = int(match.group(2)) if match.group(2) else 0
        if len(content) > 30:
            all_examples.append({
                'type': 'synthesis_example',
                'number': num,
                'content': content[:5000],
                'content_length': len(content),
                'has_table': False,
                'has_dielectric_value': False,
            })
    
    # Step 3: 如果正則沒匹配到，使用段落分割保底
    if not all_examples and location['example_section_start'] is not None:
        # 按 "Example" 標題分割
        parts = re.split(r'\n(?=(?:Example|EXAMPLE)\s+\d+)', example_section)
        for part in parts[1:]:  # 跳過第一部分（可能是非 example 的過渡文字）
            part = part.strip()
            if len(part) > 50:
                num_match = re.search(r'(?:Example|EXAMPLE)\s+(\d+)', part)
                num = int(num_match.group(1)) if num_match else 0
                all_examples.append({
                    'type': 'example_fallback',
                    'number': num,
                    'content': part[:5000],
                    'content_length': len(part),
                    'has_table': bool(re.search(r'Δ[εn]|Clearing\s+point|γ1|K\d|V[0HV]', part)),
                    'has_dielectric_value': bool(re.search(r'Δε|Δ[εε]|dielectric\s+anisotropy', part, re.IGNORECASE)),
                })
    
    # Step 4: 統計與評判
    result['examples'] = all_examples
    result['example_count'] = len(all_examples)
    
    type_counts = {}
    for ex in all_examples:
        t = ex['type']
        type_counts[t] = type_counts.get(t, 0) + 1
    result['example_types'] = type_counts
    
    result['has_working_examples'] = type_counts.get('working_example', 0) > 0
    result['has_synthesis_examples'] = type_counts.get('synthesis_example', 0) > 0
    result['has_comparative_examples'] = type_counts.get('comparative_example', 0) > 0
    
    if all_examples:
        result['max_example_number'] = max(ex['number'] for ex in all_examples if ex['number'])
    
    # 評判品質
    if result['example_count'] == 0:
        result['extraction_quality'] = 'failure'  # 每篇專利必有實施例，0 = 方法有問題
    elif result['has_working_examples'] and result['example_count'] >= 2:
        result['extraction_quality'] = 'good'
    elif result['example_count'] >= 1:
        result['extraction_quality'] = 'partial'
    else:
        result['extraction_quality'] = 'failure'
    
    return result


# ============================================================
# Part 3: 介電常數正負值精準判斷
# ============================================================

def judge_dielectric_anisotropy(abstract: str, claim1: str, examples_data: Dict) -> Dict[str, Any]:
    """
    精準判斷液晶介電各向異性（Δε）的正負值。
    
    三級證據源（優先順序）：
    1. Abstract - 最權威（專利核心定性描述）
    2. Claims - 法律界定（Claim 1 是否明確說明）
    3. Examples - 量化佐證（Δε 實測值的正負）
    
    判斷規則：
    - abstract 明確說 "negative/positive dielectric anisotropy" → 直接判定
    - claim1 明確說 "having negative/positive dielectric anisotropy" → 直接判定
    - examples 中有 Δε 數值（如 Δε = -3.8）→ 量化佐證
    - description 中同時提及 negative 和 positive → 需分析上下文
      （可能是對比技術，而非本發明的特徵）
    
    避免誤判：
    - VA (Vertically Aligned) ≠ 一定 negative DA（positive VA 也存在）
    - IPS/FFS ≠ 一定 positive DA（negative DA 也可用於特殊 IPS）
    - description 中出現 positive DA 可能是描述對比技術
    - 應以 abstract/claims/examples 中的明確描述為準
    """
    result = {
        'is_negative_da': None,
        'confidence': 0.0,
        'evidence': [],
        'judgment_method': None,
        'warning': None,
    }
    
    # ===== Level 1: Abstract 判斷 =====
    abstract_evidence = []
    
    # 精確匹配 abstract 中的 "negative dielectric anisotropy"
    neg_da_abstract = re.findall(
        r'(?:having|with|of|comprising)\s+(?:a\s+)?negative\s+dielectric\s+anisotropy',
        abstract, re.IGNORECASE
    )
    if neg_da_abstract:
        abstract_evidence.append({
            'level': 'abstract',
            'sign': 'negative',
            'pattern': 'negative dielectric anisotropy',
            'count': len(neg_da_abstract),
            'context': neg_da_abstract[0][:200]
        })
    
    # 精確匹配 abstract 中的 "positive dielectric anisotropy"
    pos_da_abstract = re.findall(
        r'(?:having|with|of|comprising)\s+(?:a\s+)?positive\s+dielectric\s+anisotropy',
        abstract, re.IGNORECASE
    )
    if pos_da_abstract:
        abstract_evidence.append({
            'level': 'abstract',
            'sign': 'positive',
            'pattern': 'positive dielectric anisotropy',
            'count': len(pos_da_abstract),
            'context': pos_da_abstract[0][:200]
        })
    
    # Abstract 中的 Δε 符號
    neg_delta_abstract = re.findall(r'Δ[εε]\s*[<≤–\-]\s*0', abstract)
    pos_delta_abstract = re.findall(r'Δ[εε]\s*[>≥\+]\s*0', abstract)
    
    if neg_delta_abstract:
        abstract_evidence.append({
            'level': 'abstract',
            'sign': 'negative',
            'pattern': 'Δε < 0',
            'count': len(neg_delta_abstract),
            'context': neg_delta_abstract[0]
        })
    if pos_delta_abstract:
        abstract_evidence.append({
            'level': 'abstract',
            'sign': 'positive',
            'pattern': 'Δε > 0',
            'count': len(pos_delta_abstract),
            'context': pos_delta_abstract[0]
        })
    
    # Abstract 中的顯示模式（輔助參考，不作為主要判斷）
    abstract_display_modes = []
    if re.search(r'\bVA\b|vertically\s+aligned', abstract, re.IGNORECASE):
        # 注意：要區分 "VA" 和 "positive VA"
        if re.search(r'positive\s+VA|positive\s+PS-VA', abstract, re.IGNORECASE):
            abstract_display_modes.append('positive_VA')
        elif re.search(r'\bVA\b', abstract) and not re.search(r'positive\s+VA', abstract, re.IGNORECASE):
            abstract_display_modes.append('VA')
    if re.search(r'\bIPS\b|\bFFS\b', abstract, re.IGNORECASE):
        abstract_display_modes.append('IPS/FFS')
    
    result['evidence'].extend(abstract_evidence)
    
    # Abstract 判定
    abstract_neg = sum(1 for e in abstract_evidence if e['sign'] == 'negative')
    abstract_pos = sum(1 for e in abstract_evidence if e['sign'] == 'positive')
    
    if abstract_neg > 0 and abstract_pos == 0:
        result['is_negative_da'] = True
        result['confidence'] = 0.95
        result['judgment_method'] = 'abstract_explicit'
        result['evidence'].append({
            'level': 'judgment',
            'sign': 'negative',
            'method': 'abstract_explicit',
            'detail': f'Abstract explicitly states "negative dielectric anisotropy" ({abstract_neg} times), no positive DA mention'
        })
        return result
    elif abstract_pos > 0 and abstract_neg == 0:
        result['is_negative_da'] = False
        result['confidence'] = 0.95
        result['judgment_method'] = 'abstract_explicit'
        result['evidence'].append({
            'level': 'judgment',
            'sign': 'positive',
            'method': 'abstract_explicit',
            'detail': f'Abstract explicitly states "positive dielectric anisotropy" ({abstract_pos} times), no negative DA mention'
        })
        return result
    
    # ===== Level 2: Claims 判斷 =====
    claim_evidence = []
    
    # Claim 1 中的明確描述
    neg_da_claim = re.findall(
        r'(?:having|with|of|comprising)\s+(?:a\s+)?negative\s+dielectric\s+anisotropy',
        claim1, re.IGNORECASE
    )
    pos_da_claim = re.findall(
        r'(?:having|with|of|comprising)\s+(?:a\s+)?positive\s+dielectric\s+anisotropy',
        claim1, re.IGNORECASE
    )
    
    # 更寬鬆的匹配（claim1 可能只用 "negative dielectric" 不帶 "anisotropy"）
    if not neg_da_claim:
        neg_da_claim = re.findall(r'negative\s+dielectric', claim1, re.IGNORECASE)
    if not pos_da_claim:
        pos_da_claim = re.findall(r'positive\s+dielectric', claim1, re.IGNORECASE)
    
    if neg_da_claim:
        claim_evidence.append({
            'level': 'claim1',
            'sign': 'negative',
            'pattern': 'negative dielectric',
            'count': len(neg_da_claim),
            'context': neg_da_claim[0][:200]
        })
    if pos_da_claim:
        claim_evidence.append({
            'level': 'claim1',
            'sign': 'positive',
            'pattern': 'positive dielectric',
            'count': len(pos_da_claim),
            'context': pos_da_claim[0][:200]
        })
    
    result['evidence'].extend(claim_evidence)
    
    claim_neg = sum(1 for e in claim_evidence if e['sign'] == 'negative')
    claim_pos = sum(1 for e in claim_evidence if e['sign'] == 'positive')
    
    if claim_neg > 0 and claim_pos == 0:
        result['is_negative_da'] = True
        result['confidence'] = 0.90
        result['judgment_method'] = 'claim1_explicit'
        result['evidence'].append({
            'level': 'judgment',
            'sign': 'negative',
            'method': 'claim1_explicit',
            'detail': f'Claim 1 explicitly states "negative dielectric" ({claim_neg} times)'
        })
        return result
    elif claim_pos > 0 and claim_neg == 0:
        result['is_negative_da'] = False
        result['confidence'] = 0.90
        result['judgment_method'] = 'claim1_explicit'
        result['evidence'].append({
            'level': 'judgment',
            'sign': 'positive',
            'method': 'claim1_explicit',
            'detail': f'Claim 1 explicitly states "positive dielectric" ({claim_pos} times)'
        })
        return result
    
    # ===== Level 3: Examples 量化佐證 =====
    example_evidence = []
    
    for ex in examples_data.get('examples', []):
        content = ex.get('content', '')
        
        # 搜尋 Δε 數值（如 Δε = -3.8, Δε: -3.8, Δε [1 kHz, 20°C]: -3.8）
        delta_e_values = re.findall(
            r'Δ[εε]\s*(?:\[.*?\]\s*)?[=:]\s*([+-]?\s*\d+\.?\d*)',
            content
        )
        
        for val_str in delta_e_values:
            try:
                val = float(val_str.replace(' ', ''))
                sign = 'negative' if val < 0 else 'positive'
                example_evidence.append({
                    'level': 'example',
                    'sign': sign,
                    'value': val,
                    'example_type': ex.get('type', 'unknown'),
                    'example_number': ex.get('number', 0),
                    'context': f'Δε = {val}'
                })
            except ValueError:
                continue
    
    result['evidence'].extend(example_evidence)
    
    ex_neg = sum(1 for e in example_evidence if e['sign'] == 'negative')
    ex_pos = sum(1 for e in example_evidence if e['sign'] == 'positive')
    
    if ex_neg > 0 and ex_pos == 0:
        result['is_negative_da'] = True
        result['confidence'] = 0.85
        result['judgment_method'] = 'example_quantitative'
        result['evidence'].append({
            'level': 'judgment',
            'sign': 'negative',
            'method': 'example_quantitative',
            'detail': f'Examples show negative Δε values ({ex_neg} measurements), no positive Δε'
        })
        return result
    elif ex_pos > 0 and ex_neg == 0:
        result['is_negative_da'] = False
        result['confidence'] = 0.85
        result['judgment_method'] = 'example_quantitative'
        result['evidence'].append({
            'level': 'judgment',
            'sign': 'positive',
            'method': 'example_quantitative',
            'detail': f'Examples show positive Δε values ({ex_pos} measurements), no negative Δε'
        })
        return result
    
    # ===== 綜合判斷（多級證據衝突時） =====
    total_neg = abstract_neg + claim_neg + ex_neg
    total_pos = abstract_pos + claim_pos + ex_pos
    
    if total_neg > 0 and total_pos > 0:
        # 證據衝突：需要加權分析
        # Abstract 權重最高，其次是 claim，最後是 example
        weighted_neg = abstract_neg * 3 + claim_neg * 2 + ex_neg * 1
        weighted_pos = abstract_pos * 3 + claim_pos * 2 + ex_pos * 1
        
        if weighted_neg > weighted_pos:
            result['is_negative_da'] = True
            result['confidence'] = 0.70
            result['judgment_method'] = 'weighted_conflict'
            result['warning'] = f'Evidence conflict: neg={total_neg} pos={total_pos}, weighted: neg={weighted_neg} pos={weighted_pos}'
        elif weighted_pos > weighted_neg:
            result['is_negative_da'] = False
            result['confidence'] = 0.70
            result['judgment_method'] = 'weighted_conflict'
            result['warning'] = f'Evidence conflict: neg={total_neg} pos={total_pos}, weighted: neg={weighted_neg} pos={weighted_pos}'
        else:
            result['is_negative_da'] = None
            result['confidence'] = 0.0
            result['judgment_method'] = 'undetermined'
            result['warning'] = 'Equal evidence for both negative and positive DA'
    
    elif total_neg > 0:
        result['is_negative_da'] = True
        result['confidence'] = 0.80
        result['judgment_method'] = 'multi_level'
        result['evidence'].append({
            'level': 'judgment',
            'sign': 'negative',
            'method': 'multi_level',
            'detail': f'Combined evidence: neg={total_neg} pos={total_pos}'
        })
    elif total_pos > 0:
        result['is_negative_da'] = False
        result['confidence'] = 0.80
        result['judgment_method'] = 'multi_level'
        result['evidence'].append({
            'level': 'judgment',
            'sign': 'positive',
            'method': 'multi_level',
            'detail': f'Combined evidence: neg={total_neg} pos={total_pos}'
        })
    else:
        # 沒有任何直接證據，使用顯示模式推斷
        if 'VA' in abstract_display_modes:
            result['is_negative_da'] = True
            result['confidence'] = 0.60
            result['judgment_method'] = 'display_mode_inference'
            result['warning'] = 'Inferred from VA display mode, no explicit dielectric anisotropy statement'
        elif 'positive_VA' in abstract_display_modes:
            result['is_negative_da'] = False
            result['confidence'] = 0.65
            result['judgment_method'] = 'display_mode_inference'
            result['warning'] = 'Inferred from positive VA display mode'
        elif 'IPS/FFS' in abstract_display_modes:
            result['is_negative_da'] = False
            result['confidence'] = 0.55
            result['judgment_method'] = 'display_mode_inference'
            result['warning'] = 'Inferred from IPS/FFS display mode (usually positive DA), not conclusive'
        else:
            result['is_negative_da'] = None
            result['confidence'] = 0.0
            result['judgment_method'] = 'no_evidence'
            result['warning'] = 'No evidence found in abstract, claims, or examples to determine DA sign'
    
    return result


# ============================================================
# Part 4: Claim 1 提取（沿用 v9 的多模式匹配 + 改進）
# ============================================================

CLAIM1_PATTERNS = [
    (r'WHAT IS CLAIMED IS:\s*(?:1\.\s*)([\s\S]{50,}?(?:;\s*or\s*[\s\S]*?)*?(?=\n\n2\.|\n\nCLAIMS|\n\nABSTRACT|$))', "標準格式", 1.0),
    (r'CLAIMS\s*(?:1\.\s*)([\s\S]{50,}?(?=\n\n2\.|\n\nABSTRACT|$))', "CLAIMS 開頭", 0.9),
    (r'1\.\s+([^\n]{30,}?(?:\n[^\n]*){1,10}?(?=\n\n2\.|\n\n|\Z))', "寬鬆數字", 0.8),
    (r'申請專利範圍\s*1\.([\s\S]{30,}?(?=2\.|$))', "中文格式", 0.85),
    (r'(?:Claim 1|第 1 項)\s*[:\.\s]*([\s\S]{50,}?(?=2\.|摘要|ABSTRACT|$))', "WO 格式", 0.75),
    (r'1\.\s+([\s\S]{50,}?(?=\n\n2\.|\n\n|\Z))', "最簡保底", 0.7),
]


def extract_claim1_v11(text: str) -> Tuple[Optional[str], str, float]:
    """Claim 1 提取（多模式 + 置信度評分）"""
    results = []
    
    for pattern, pattern_name, base_confidence in CLAIM1_PATTERNS:
        try:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                claim1 = match.group(1).strip()
                claim1 = re.sub(r'\s+', ' ', claim1)
                
                if len(claim1) < 50:
                    continue
                
                confidence = base_confidence
                
                # 關鍵詞加分
                keywords = ['comprising', 'wherein', 'characterized by', '包括', '特徵在於']
                if any(kw in claim1.lower() for kw in keywords):
                    confidence += 0.15
                
                # 化學式加分
                if re.search(r'[A-Z]-\d-[A-Z]|wt%|molecular|formula', claim1, re.IGNORECASE):
                    confidence += 0.1
                
                # 長度適中加分
                if 100 <= len(claim1) <= 5000:
                    confidence += 0.05
                
                results.append((claim1, pattern_name, min(confidence, 1.0)))
        except Exception:
            continue
    
    if not results:
        return None, "無匹配", 0.0
    
    results.sort(key=lambda x: x[2], reverse=True)
    return results[0]


# ============================================================
# Part 5: 完整提取流程
# ============================================================

def extract_patent_full_v11(url: str) -> Dict:
    """
    v11 完整提取流程
    
    改進：
    1. 全文提取（解決截斷問題）
    2. 實施例定位 + 提取 + 評判
    3. 介電常數正負值精準判斷
    4. Claim 1 多模式匹配
    """
    
    # Step 1: 獲取全文
    page_data = fetch_full_patent_text(url)
    
    if not page_data['success']:
        return {
            'success': False,
            'url': url,
            'error': page_data.get('error', 'Unknown error'),
            'version': 'v11'
        }
    
    text = page_data['text']
    html = page_data['html']
    title = page_data['title']
    
    # Step 2: 提取 Claim 1
    claim1, claim1_pattern, claim1_confidence = extract_claim1_v11(text)
    
    # Step 3: 提取 Abstract
    abstract = ''
    abstract_match = re.search(r'Abstract\s*([\s\S]{50,}?)(?=\n\n(?:Description|Claims|TECHNICAL|BACKGROUND)|$)', text, re.IGNORECASE)
    if abstract_match:
        abstract = abstract_match.group(1).strip()
    else:
        # 備選：從 HTML meta 提取
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'lxml')
        meta_abstract = soup.find('meta', attrs={'name': 'citation_abstract'})
        if meta_abstract:
            abstract = meta_abstract.get('content', '')
    
    # Step 4: 提取實施例
    examples_result = extract_examples_v11(text)
    
    # Step 5: 判斷介電常數正負
    da_judgment = judge_dielectric_anisotropy(abstract, claim1 or '', examples_result)
    
    # Step 6: 提取專利號
    patent_number = None
    url_match = re.search(r'patent/([A-Z]{2,4}\d+[A-Z]?)', url)
    if url_match:
        patent_number = url_match.group(1)
    else:
        title_match = re.search(r'([A-Z]{2,4}\d+[A-Z]?)\s*[-–]', title)
        if title_match:
            patent_number = title_match.group(1)
    
    # Step 7: 提取日期（多格式）
    dates = {}
    for field, patterns in [
        ('publication_date', [
            r'(?:Publication date|公開日期)[:\s]*(\d{4}-\d{2}-\d{2})',
            r'(?:Publication date)[:\s]*(\d{1,2}/\d{1,2}/\d{4})',
        ]),
        ('filing_date', [
            r'(?:Filing date|申請日)[:\s]*(\d{4}-\d{2}-\d{2})',
            r'(?:Filing date)[:\s]*(\d{1,2}/\d{1,2}/\d{4})',
        ]),
        ('priority_date', [
            r'(?:Priority date|優先權日)[:\s]*(\d{4}-\d{2}-\d{2})',
        ]),
    ]:
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                dates[field] = match.group(1)
                break
    
    # Step 8: 從 HTML meta 提取日期（補充）
    if not dates.get('publication_date') or not dates.get('filing_date'):
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'lxml')
            meta_map = {
                'publication_date': 'citation_publication_date',
                'filing_date': 'citation_filing_date',
            }
            for target, meta_name in meta_map.items():
                if not dates.get(target):
                    meta = soup.find('meta', attrs={'name': meta_name})
                    if meta and meta.get('content'):
                        dates[target] = meta.get('content')
        except:
            pass
    
    return {
        'success': True,
        'url': url,
        'version': 'v11',
        'patent_number': patent_number,
        'title': title,
        'abstract': abstract[:3000],  # 限制長度
        'claim1': claim1,
        'claim1_pattern': claim1_pattern,
        'claim1_confidence': claim1_confidence,
        'claim1_length': len(claim1) if claim1 else 0,
        'dates': dates,
        'examples': examples_result,
        'dielectric_anisotropy_judgment': da_judgment,
        'is_negative_da': da_judgment['is_negative_da'],
        'da_confidence': da_judgment['confidence'],
        'da_judgment_method': da_judgment['judgment_method'],
        'text_length': len(text),
    }


def batch_extract_v11(urls: List[str], output_file: str, delay: float = 2.0) -> List[Dict]:
    """
    v11 批量提取
    
    Args:
        urls: 專利 URL 列表
        output_file: 輸出 JSON 路徑
        delay: 每個請求之間的延遲秒數
    """
    print("=" * 100)
    print("Merck KGaA 負介電液晶專利提取 v11（改進版）")
    print("核心改進：(1) 全文提取 (2) 實施例定位+評判 (3) Δε 正負精準判斷")
    print("=" * 100)
    
    extracted = []
    
    for i, url in enumerate(urls, 1):
        print(f"\n[{i}/{len(urls)}] 提取：{url}")
        
        result = extract_patent_full_v11(url)
        extracted.append(result)
        
        if result['success']:
            pid = result.get('patent_number', 'N/A')
            is_neg = result.get('is_negative_da')
            da_conf = result.get('da_confidence', 0)
            ex_count = result.get('examples', {}).get('example_count', 0)
            ex_quality = result.get('examples', {}).get('extraction_quality', 'unknown')
            claim1_len = result.get('claim1_length', 0)
            
            print(f"  ✓ 成功 - {pid}")
            print(f"    Claim 1: {claim1_len} 字元")
            print(f"    實施例: {ex_count} 個 (品質: {ex_quality})")
            print(f"    Δε 判定: {'negative' if is_neg else 'positive' if is_neg is False else 'undetermined'} (置信度: {da_conf:.2f})")
            print(f"    Δε 方法: {result.get('da_judgment_method', 'N/A')}")
            if result.get('dielectric_anisotropy_judgment', {}).get('warning'):
                print(f"    ⚠️  {result['dielectric_anisotropy_judgment']['warning']}")
        else:
            print(f"  ✗ 失敗 - {result.get('error', 'Unknown')}")
        
        if i < len(urls):
            time.sleep(delay)
    
    # 保存結果
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(extracted, f, ensure_ascii=False, indent=2)
    
    # 統計
    success_count = sum(1 for p in extracted if p['success'])
    claim1_count = sum(1 for p in extracted if p.get('claim1'))
    example_count = sum(1 for p in extracted if p.get('examples', {}).get('example_count', 0) > 0)
    neg_da_count = sum(1 for p in extracted if p.get('is_negative_da') == True)
    pos_da_count = sum(1 for p in extracted if p.get('is_negative_da') == False)
    undet_da_count = sum(1 for p in extracted if p.get('is_negative_da') is None)
    
    # 實施例品質統計
    good_examples = sum(1 for p in extracted if p.get('examples', {}).get('extraction_quality') == 'good')
    partial_examples = sum(1 for p in extracted if p.get('examples', {}).get('extraction_quality') == 'partial')
    failed_examples = sum(1 for p in extracted if p.get('examples', {}).get('extraction_quality') == 'failure')
    
    print("\n" + "=" * 100)
    print("提取統計（v11）")
    print("=" * 100)
    print(f"  總提取數量：{success_count}/{len(extracted)}")
    print(f"  Claim 1 提取：{claim1_count}/{len(extracted)} ({claim1_count/len(extracted)*100:.1f}%)")
    print(f"  實施例提取：{example_count}/{len(extracted)} ({example_count/len(extracted)*100:.1f}%)")
    print(f"    - 品質 good: {good_examples}")
    print(f"    - 品質 partial: {partial_examples}")
    print(f"    - 品質 failure: {failed_examples}")
    print(f"  Δε 判定：neg={neg_da_count} / pos={pos_da_count} / undet={undet_da_count}")
    print(f"  結果已保存：{output_file}")
    
    return extracted


# ============================================================
# Part 6: 基於現有 JSON 資料的離線改進分析
# ============================================================

def reanalyze_existing_data(json_file: str, output_file: str) -> Dict:
    """
    基於 final_18_merged.json 進行離線改進分析。
    
    不需要重新爬取網頁，直接對現有資料重新分析：
    1. 重新判斷 Δε 正負（使用 v11 的三級證據法）
    2. 評估現有 example_table_data 的品質
    3. 標記需要重新爬取全文的專利（description 截斷的）
    """
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    results = {}
    needs_full_text = []
    
    for pid, p in data.items():
        abstract = p.get('abstract', '')
        claim1 = p.get('claim1', '')
        desc = p.get('description', '')
        example_table = p.get('example_table_data', '')
        
        # 構建 examples_data 結構
        examples_data = {
            'examples': [],
            'example_count': 0,
        }
        
        # 如果有 example_table_data，解析為 examples 結構
        if example_table and len(example_table) > 10:
            # 按 Example 標題分割
            parts = re.split(r'\n(?=Example\s+\d+)', example_table)
            for part in parts:
                part = part.strip()
                if len(part) > 30:
                    num_match = re.search(r'Example\s+(\d+)', part)
                    examples_data['examples'].append({
                        'type': 'working_example',
                        'number': int(num_match.group(1)) if num_match else 0,
                        'content': part[:5000],
                        'content_length': len(part),
                        'has_table': bool(re.search(r'Δ[εn]|Clearing\s+point|γ1|K\d', part)),
                        'has_dielectric_value': bool(re.search(r'Δε|Δ[εε]', part, re.IGNORECASE)),
                    })
            examples_data['example_count'] = len(examples_data['examples'])
        
        # 使用 v11 方法重新判斷 Δε
        da_judgment = judge_dielectric_anisotropy(abstract, claim1, examples_data)
        
        # 檢查 description 是否截斷
        desc_truncated = False
        if desc:
            last_char = desc.rstrip()[-1] if desc else ''
            desc_truncated = last_char not in '.!?:]' and len(desc) >= 26693  # 最短的非截斷專利
        
        # 判斷是否需要重新爬取全文
        needs_refetch = False
        reasons = []
        
        # 如果實施例為 0 且 description 截斷，很可能是因為截斷遺失了 examples
        if examples_data['example_count'] == 0 and desc_truncated:
            needs_refetch = True
            reasons.append('description_truncated_examples_lost')
        
        # 如果 Δε 判斷有衝突或低置信度
        if da_judgment['confidence'] < 0.7:
            needs_refetch = True
            reasons.append('da_judgment_low_confidence')
        
        # 如果原有的 is_negative_da 與 v11 判斷不同
        original_is_neg = p.get('is_negative_da', None)
        new_is_neg = da_judgment['is_negative_da']
        judgment_changed = (original_is_neg != new_is_neg) and (original_is_neg is not None) and (new_is_neg is not None)
        
        if judgment_changed:
            reasons.append(f'da_judgment_changed_from_{original_is_neg}_to_{new_is_neg}')
        
        result = {
            'patent_id': pid,
            'original_is_negative_da': original_is_neg,
            'v11_is_negative_da': new_is_neg,
            'v11_da_confidence': da_judgment['confidence'],
            'v11_da_method': da_judgment['judgment_method'],
            'v11_da_warning': da_judgment.get('warning'),
            'v11_da_evidence': da_judgment['evidence'],
            'example_count': examples_data['example_count'],
            'description_truncated': desc_truncated,
            'description_length': len(desc),
            'needs_full_text_refetch': needs_refetch,
            'refetch_reasons': reasons,
            'judgment_changed': judgment_changed,
        }
        
        results[pid] = result
        
        if needs_refetch:
            needs_full_text.append({
                'patent_id': pid,
                'url': p.get('url', ''),
                'reasons': reasons
            })
    
    # 保存結果
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    # 統計
    total = len(data)
    changed = sum(1 for r in results.values() if r['judgment_changed'])
    needs_refetch = sum(1 for r in results.values() if r['needs_full_text_refetch'])
    no_examples = sum(1 for r in results.values() if r['example_count'] == 0)
    
    print(f"\n{'='*80}")
    print(f"離線改進分析結果（v11）")
    print(f"{'='*80}")
    print(f"  總專利數：{total}")
    print(f"  Δε 判定變更：{changed} 篇")
    print(f"  需要重新爬取全文：{needs_refetch} 篇")
    print(f"  無實施例資料：{no_examples} 篇")
    
    print(f"\n--- Δε 判定變更明細 ---")
    for pid, r in results.items():
        if r['judgment_changed']:
            print(f"  {pid}: {r['original_is_negative_da']} -> {r['v11_is_negative_da']} "
                  f"(method: {r['v11_da_method']}, confidence: {r['v11_da_confidence']:.2f})")
            if r['v11_da_warning']:
                print(f"    ⚠️  {r['v11_da_warning']}")
    
    print(f"\n--- 需要重新爬取 ---")
    for item in needs_full_text:
        print(f"  {item['patent_id']}: {item['reasons']}")
    
    return {
        'results': results,
        'needs_full_text': needs_full_text,
        'summary': {
            'total': total,
            'da_judgment_changed': changed,
            'needs_refetch': needs_refetch,
            'no_examples': no_examples,
        }
    }


# ============================================================
# Main
# ============================================================

if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == '--reanalyze':
        # 離線分析模式：對現有 JSON 重新分析
        json_file = sys.argv[2] if len(sys.argv) > 2 else '/tmp/final_18_merged.json'
        output_file = sys.argv[3] if len(sys.argv) > 3 else '/tmp/v11_reanalysis_results.json'
        reanalyze_existing_data(json_file, output_file)
    
    elif len(sys.argv) > 1 and sys.argv[1] == '--batch':
        # 批量爬取模式
        urls_file = sys.argv[2] if len(sys.argv) > 2 else '/tmp/patent_urls.json'
        output_file = sys.argv[3] if len(sys.argv) > 3 else '/tmp/v11_extracted_patents.json'
        
        with open(urls_file, 'r', encoding='utf-8') as f:
            urls_data = json.load(f)
        
        if isinstance(urls_data, list):
            urls = [u if isinstance(u, str) else u.get('url', '') for u in urls_data]
        elif isinstance(urls_data, dict):
            urls = [p.get('url', '') for p in urls_data.values()]
        else:
            urls = []
        
        urls = [u for u in urls if u]
        batch_extract_v11(urls, output_file)
    
    else:
        print("用法:")
        print("  python patent_extract_v11_improved.py --reanalyze [input.json] [output.json]")
        print("  python patent_extract_v11_improved.py --batch [urls.json] [output.json]")
        print()
        print("  --reanalyze: 對現有 JSON 資料重新分析（離線，不需爬取）")
        print("  --batch:     批量爬取並提取（需要 Playwright）")
