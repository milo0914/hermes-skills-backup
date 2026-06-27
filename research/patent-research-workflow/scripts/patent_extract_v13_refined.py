#!/usr/bin/env python3
"""
Patent Extract v13 — 四層 Δε 分類器 + 雙軌實施例提取 + Claim1 品質驗證

基於 v11 實作基礎 + v12 架構改進：
  1. 四層 Δε 分類器：Abstract(0.95) → Claim1(0.90) → Example Table(0.85) → Desc Tail(0.60)
  2. 雙軌實施例提取：Track1 結構化欄位 + Track2 Tail-Emergency 掃描
  3. Claim1 品質評分（多模式匹配 + 關鍵詞/化學式加分）
  4. 離線分析模式 (--reanalyze) 不需 Playwright
  5. 線上批量模式 (--batch) 需 Playwright 全文提取

Date: 2026-06-04
Author: Hermes Agent (v13 refined)
"""

import re
import json
import time
import os
from typing import Dict, List, Tuple, Optional, Any

# ============================================================
# Part 1: 四層 Δε 分類器 (v12 architecture → v13 implementation)
# ============================================================

# 分類結果常數
CLASS_CONFIRMED_NEG = 'confirmed_neg'
CLASS_CONFIRMED_POS = 'confirmed_pos'
CLASS_LIKELY_NEG = 'likely_neg'
CLASS_LIKELY_POS = 'likely_pos'
CLASS_AMBIGUOUS = 'ambiguous'

# 置信度映射
LAYER_CONFIDENCE = {
    'abstract': 0.95,
    'claim1': 0.90,
    'example_table_data': 0.85,
    'desc_tail': 0.60,
    'none': 0.0,
}


def _extract_da_sign_from_text(text: str, source: str) -> Dict[str, Any]:
    """
    從一段文本中提取 negative/positive dielectric anisotropy 證據。
    
    Args:
        text: 待分析文本
        source: 來源標記 ('abstract', 'claim1', 'desc_tail')
    
    Returns:
        dict with 'neg_evidence', 'pos_evidence', 'delta_values'
    """
    result = {
        'neg_evidence': [],
        'pos_evidence': [],
        'delta_values': [],
    }
    
    if not text or len(text) < 10:
        return result
    
    # Pattern 1: "having/with/of/comprising [a] negative/positive dielectric anisotropy"
    neg_phrases = re.findall(
        r'(?:having|with|of|comprising|comprises|containing|contains)\s+(?:a\s+)?negative\s+dielectric\s+anisotropy',
        text, re.IGNORECASE
    )
    pos_phrases = re.findall(
        r'(?:having|with|of|comprising|comprises|containing|contains)\s+(?:a\s+)?positive\s+dielectric\s+anisotropy',
        text, re.IGNORECASE
    )
    
    # Pattern 2: "negative/positive dielectric anisotropy" 單獨出現（較寬鬆）
    if not neg_phrases:
        neg_phrases = re.findall(r'negative\s+dielectric\s+anisotropy', text, re.IGNORECASE)
    if not pos_phrases:
        pos_phrases = re.findall(r'positive\s+dielectric\s+anisotropy', text, re.IGNORECASE)
    
    for p in neg_phrases:
        result['neg_evidence'].append({'source': source, 'pattern': p[:200]})
    for p in pos_phrases:
        result['pos_evidence'].append({'source': source, 'pattern': p[:200]})
    
    # Pattern 3: Δε 符號明確標示 (Δε < 0, Δε > 0, Δε = -X.X)
    neg_symbol = re.findall(r'Δ[εé]\s*[<≤–\-]\s*0', text)
    pos_symbol = re.findall(r'Δ[εé]\s*[>≥\+]\s*0', text)
    for s in neg_symbol:
        result['neg_evidence'].append({'source': source, 'pattern': s})
    for s in pos_symbol:
        result['pos_evidence'].append({'source': source, 'pattern': s})
    
    # Pattern 4: Δε = -X.X / Δε = +X.X 數值
    delta_values = re.findall(
        r'Δ[εé]\s*(?:\[.*?\]\s*)?[=:]\s*([+-]?\s*\d+\.?\d*)',
        text
    )
    for val_str in delta_values:
        try:
            val = float(val_str.replace(' ', ''))
            sign = 'negative' if val < 0 else 'positive'
            result['delta_values'].append({
                'source': source,
                'value': val,
                'sign': sign,
                'context': f'Δε = {val}'
            })
        except ValueError:
            continue
    
    return result


def classify_delta_epsilon_v13(patent_data: Dict) -> Dict[str, Any]:
    """
    v13 四層 Δε 分類器（含 Layer 1b 顯示模式縮寫 + Layer 4b 語義模式）。

    優先順序：
    Layer 1a: Abstract — "negative/positive dielectric anisotropy" 完整詞組 (0.95)
    Layer 1b: Abstract — 顯示模式縮寫 "positive/negative VA/PS-VA/IPS/FFS" (0.80)
    Layer 2:  Claim 1 (0.90)
    Layer 3:  example_table_data (0.85)
    Layer 4a: Description tail — last 20% only (0.60)
    Layer 4b: Description — "instead of" 語義模式 (0.70)

    NEVER use display mode (FFS/IPS/VA) as primary classifier.
    Layer 1b 僅作為 fallback，當 Layer 1a 完整詞組匹配失敗時使用。

    Args:
        patent_data: 專利數據 dict，需含 abstract, claim1, description,
                     example_table_data 等欄位

    Returns:
        dict with 'classification', 'confidence', 'layer', 'evidence',
        'is_negative_da' (bool|None), 'warnings'
    """
    result = {
        'classification': CLASS_AMBIGUOUS,
        'confidence': 0.0,
        'layer': 'none',
        'evidence': [],
        'is_negative_da': None,
        'warnings': [],
    }

    abstract = patent_data.get('abstract', '')
    claim1 = patent_data.get('claim1', '')
    description = patent_data.get('description', '')
    example_table_data = patent_data.get('example_table_data', '')

    # ===== Layer 1a: Abstract — 完整詞組匹配 (confidence 0.95) =====
    if abstract:
        abs_ev = _extract_da_sign_from_text(abstract, 'abstract')
        result['evidence'].extend(
            abs_ev['neg_evidence'] + abs_ev['pos_evidence'] + abs_ev['delta_values']
        )

        abs_neg = len(abs_ev['neg_evidence'])
        abs_pos = len(abs_ev['pos_evidence'])

        if abs_neg > 0 and abs_pos == 0:
            result['classification'] = CLASS_CONFIRMED_NEG
            result['confidence'] = 0.95
            result['layer'] = 'abstract'
            result['is_negative_da'] = True
            result['evidence'].append({
                'source': 'judgment',
                'detail': f'Layer 1a (abstract): {abs_neg}x "negative DA", 0x "positive DA"'
            })
            return result

        if abs_pos > 0 and abs_neg == 0:
            result['classification'] = CLASS_CONFIRMED_POS
            result['confidence'] = 0.95
            result['layer'] = 'abstract'
            result['is_negative_da'] = False
            result['evidence'].append({
                'source': 'judgment',
                'detail': f'Layer 1a (abstract): {abs_pos}x "positive DA", 0x "negative DA"'
            })
            return result

    # ===== Layer 1b: Abstract — 顯示模式縮寫匹配 (confidence 0.80) =====
    # 捕獲 "positive VA", "negative PS-VA" 等縮寫
    # 重要：單獨的 "VA" 不可靠（positive VA 也存在），必須有 positive/negative 修飾
    # 陷阱：EP4400561A1 是 FFS + negative DA，所以 FFS 不等於 positive DA
    #       但 "positive FFS" 明確代表 positive DA
    if abstract:
        abs_neg_mode = re.findall(
            r'negative\s+(?:VA|PS-VA|IPS|FFS|TN|ECB)\b', abstract, re.IGNORECASE
        )
        abs_pos_mode = re.findall(
            r'positive\s+(?:VA|PS-VA|IPS|FFS|TN|ECB)\b', abstract, re.IGNORECASE
        )

        if abs_neg_mode and not abs_pos_mode:
            result['classification'] = CLASS_LIKELY_NEG
            result['confidence'] = 0.80
            result['layer'] = 'abstract_mode'
            result['is_negative_da'] = True
            result['evidence'].append({
                'source': 'judgment',
                'detail': f'Layer 1b (abstract mode): neg_mode={abs_neg_mode}, no pos_mode'
            })
            result['warnings'].append(
                'Layer 1b inference — display mode abbreviation in abstract. '
                'Full "dielectric anisotropy" text preferred for confirmation.'
            )
            return result

        if abs_pos_mode and not abs_neg_mode:
            result['classification'] = CLASS_LIKELY_POS
            result['confidence'] = 0.80
            result['layer'] = 'abstract_mode'
            result['is_negative_da'] = False
            result['evidence'].append({
                'source': 'judgment',
                'detail': f'Layer 1b (abstract mode): pos_mode={abs_pos_mode}, no neg_mode'
            })
            result['warnings'].append(
                'Layer 1b inference — display mode abbreviation in abstract. '
                'Full "dielectric anisotropy" text preferred for confirmation.'
            )
            return result

    # ===== Layer 2: Claim 1 (法律界定, confidence 0.90) =====
    if claim1:
        clm_ev = _extract_da_sign_from_text(claim1, 'claim1')
        result['evidence'].extend(
            clm_ev['neg_evidence'] + clm_ev['pos_evidence'] + clm_ev['delta_values']
        )

        clm_neg = len(clm_ev['neg_evidence'])
        clm_pos = len(clm_ev['pos_evidence'])

        if clm_neg > 0 and clm_pos == 0:
            result['classification'] = CLASS_CONFIRMED_NEG
            result['confidence'] = 0.90
            result['layer'] = 'claim1'
            result['is_negative_da'] = True
            result['evidence'].append({
                'source': 'judgment',
                'detail': f'Layer 2 (claim1): {clm_neg}x "negative DA", 0x "positive DA"'
            })
            return result

        if clm_pos > 0 and clm_neg == 0:
            result['classification'] = CLASS_CONFIRMED_POS
            result['confidence'] = 0.90
            result['layer'] = 'claim1'
            result['is_negative_da'] = False
            result['evidence'].append({
                'source': 'judgment',
                'detail': f'Layer 2 (claim1): {clm_pos}x "positive DA", 0x "negative DA"'
            })
            return result

    # ===== Layer 3: example_table_data (量化佐證, confidence 0.85) =====
    if example_table_data and len(example_table_data) > 10:
        etd_ev = _extract_da_sign_from_text(example_table_data, 'example_table_data')
        result['evidence'].extend(
            etd_ev['neg_evidence'] + etd_ev['pos_evidence'] + etd_ev['delta_values']
        )

        # 優先看 Δε 數值
        etd_neg_vals = [v for v in etd_ev['delta_values'] if v['sign'] == 'negative']
        etd_pos_vals = [v for v in etd_ev['delta_values'] if v['sign'] == 'positive']

        if etd_neg_vals and not etd_pos_vals:
            result['classification'] = CLASS_CONFIRMED_NEG
            result['confidence'] = 0.85
            result['layer'] = 'example_table_data'
            result['is_negative_da'] = True
            result['evidence'].append({
                'source': 'judgment',
                'detail': f'Layer 3 (ETD): Δε values all negative ({len(etd_neg_vals)} measurements)'
            })
            return result

        if etd_pos_vals and not etd_neg_vals:
            result['classification'] = CLASS_CONFIRMED_POS
            result['confidence'] = 0.85
            result['layer'] = 'example_table_data'
            result['is_negative_da'] = False
            result['evidence'].append({
                'source': 'judgment',
                'detail': f'Layer 3 (ETD): Δε values all positive ({len(etd_pos_vals)} measurements)'
            })
            return result

        # ETD 中無 Δε 數值，但有 negative/positive DA 文字
        etd_neg_text = len(etd_ev['neg_evidence'])
        etd_pos_text = len(etd_ev['pos_evidence'])

        if etd_neg_text > 0 and etd_pos_text == 0:
            result['classification'] = CLASS_CONFIRMED_NEG
            result['confidence'] = 0.85
            result['layer'] = 'example_table_data'
            result['is_negative_da'] = True
            return result

        if etd_pos_text > 0 and etd_neg_text == 0:
            result['classification'] = CLASS_CONFIRMED_POS
            result['confidence'] = 0.85
            result['layer'] = 'example_table_data'
            result['is_negative_da'] = False
            return result

    # ===== Layer 4a: Description tail — 最後 20% (confidence 0.60) =====
    # 重要：只用最後 20%，因為前 80% 常含對比技術 (prior art) 引用
    if description and len(description) > 500:
        tail_start = int(len(description) * 0.80)
        tail = description[tail_start:]

        tail_ev = _extract_da_sign_from_text(tail, 'desc_tail')

        tail_neg = len(tail_ev['neg_evidence'])
        tail_pos = len(tail_ev['pos_evidence'])

        # Δε 數值在 tail 中
        tail_neg_vals = [v for v in tail_ev['delta_values'] if v['sign'] == 'negative']
        tail_pos_vals = [v for v in tail_ev['delta_values'] if v['sign'] == 'positive']

        tail_neg_total = tail_neg + len(tail_neg_vals)
        tail_pos_total = tail_pos + len(tail_pos_vals)

        if tail_neg_total > tail_pos_total:
            result['classification'] = CLASS_LIKELY_NEG
            result['confidence'] = 0.60
            result['layer'] = 'desc_tail'
            result['is_negative_da'] = True
            result['evidence'].extend(
                tail_ev['neg_evidence'] + tail_ev['pos_evidence'] + tail_ev['delta_values']
            )
            result['evidence'].append({
                'source': 'judgment',
                'detail': f'Layer 4a (desc_tail): neg={tail_neg_total}, pos={tail_pos_total}'
            })
            result['warnings'].append(
                'Layer 4a inference only — description tail weighted count. '
                'Full-text extraction recommended for confirmation.'
            )
            return result

        if tail_pos_total > tail_neg_total:
            result['classification'] = CLASS_LIKELY_POS
            result['confidence'] = 0.60
            result['layer'] = 'desc_tail'
            result['is_negative_da'] = False
            result['evidence'].extend(
                tail_ev['neg_evidence'] + tail_ev['pos_evidence'] + tail_ev['delta_values']
            )
            result['evidence'].append({
                'source': 'judgment',
                'detail': f'Layer 4a (desc_tail): neg={tail_neg_total}, pos={tail_pos_total}'
            })
            result['warnings'].append(
                'Layer 4a inference only — description tail weighted count. '
                'Full-text extraction recommended for confirmation.'
            )
            return result

    # ===== Layer 4b: Description — "instead of" 語義模式 (confidence 0.70) =====
    # 捕獲 "negative dielectric anisotropy instead of positive" 等語義轉換
    # 這類語句明確表示本發明使用的是前者而非後者
    # 例：EP4400561A1 "negative dielectric anisotropy instead of positive"
    if description:
        # Pattern: "[neg/pos] dielectric anisotropy instead of [pos/neg]"
        # 重要：中間可能有 "an LC medium with" 等間隙文字（最多 40 字元）
        # 例："neg DA instead of an LC medium with pos DA"
        instead_neg = re.findall(
            r'negative\s+dielectric\s+anisotropy\s+instead\s+of\s+.{0,40}?positive',
            description, re.IGNORECASE
        )
        instead_pos = re.findall(
            r'positive\s+dielectric\s+anisotropy\s+instead\s+of\s+.{0,40}?negative',
            description, re.IGNORECASE
        )

        if instead_neg and not instead_pos:
            result['classification'] = CLASS_LIKELY_NEG
            result['confidence'] = 0.70
            result['layer'] = 'desc_instead_of'
            result['is_negative_da'] = True
            result['evidence'].append({
                'source': 'judgment',
                'detail': f'Layer 4b (desc instead_of): {len(instead_neg)}x "negative DA instead of positive"'
            })
            result['warnings'].append(
                'Layer 4b — "instead of" semantic pattern. '
                'Confidence higher than pure count (Layer 4a) but below claim-level.'
            )
            return result

        if instead_pos and not instead_neg:
            result['classification'] = CLASS_LIKELY_POS
            result['confidence'] = 0.70
            result['layer'] = 'desc_instead_of'
            result['is_negative_da'] = False
            result['evidence'].append({
                'source': 'judgment',
                'detail': f'Layer 4b (desc instead_of): {len(instead_pos)}x "positive DA instead of negative"'
            })
            result['warnings'].append(
                'Layer 4b — "instead of" semantic pattern. '
                'Confidence higher than pure count (Layer 4a) but below claim-level.'
            )
            return result

    # ===== 完全無法判定 =====
    result['classification'] = CLASS_AMBIGUOUS
    result['confidence'] = 0.0
    result['layer'] = 'none'
    result['is_negative_da'] = None
    result['warnings'].append(
        'No conclusive evidence found in any layer. '
        'Manual review or full-text extraction required.'
    )
    return result


# ============================================================
# Part 2: 雙軌實施例提取
# ============================================================

# 實施例關鍵字模式（排除 "for example" 日常用法）
EXAMPLE_PATTERNS = [
    # 有編號的 Example（專利實施例）
    (r'(?:Working\s+Example|Synthesis\s+Example|Comparative\s+Example|Preparative\s+Example|Application\s+Example)\s*#?\s*(\d+)', 'typed_example'),
    (r'(?:EXAMPLE|Example)\s*#?\s*(\d+)\s*[:.\-—]', 'numbered_example'),
    (r'(?:EXAMPLE|Example)\s+(\d+)\s*(?:\n|$)', 'bare_numbered_example'),
]

# "for example" 排除模式
FOR_EXAMPLE_EXCLUDE = re.compile(r'(?:for\s+example|such\s+as\s+for\s+example)', re.IGNORECASE)


def extract_examples_track1(patent_data: Dict) -> Dict[str, Any]:
    """
    Track 1: 從結構化欄位提取實施例。
    
    檢查 example_table_data, example_details, description 中
    已有的結構化實施例資料。
    
    Returns:
        dict with 'examples', 'example_count', 'source', 'quality'
    """
    result = {
        'examples': [],
        'example_count': 0,
        'source': 'structured',
        'quality': 'unknown',
    }
    
    # 優先從 example_table_data 提取
    etd = patent_data.get('example_table_data', '')
    if etd and len(etd) > 10:
        # 按 Example 標題分割
        parts = re.split(r'\n(?=(?:Example|EXAMPLE)\s+?\d+)', etd)
        for part in parts:
            part = part.strip()
            if len(part) > 30:
                num_match = re.search(r'(?:Example|EXAMPLE)\s+?#?\s*(\d+)', part)
                num = int(num_match.group(1)) if num_match else 0
                
                # 分類
                if re.search(r'Comparative|COMPARATIVE', part, re.IGNORECASE):
                    ex_type = 'comparative_example'
                elif re.search(r'Synthesis|SYNTHESIS|Preparative', part, re.IGNORECASE):
                    ex_type = 'synthesis_example'
                else:
                    ex_type = 'working_example'
                
                has_table = bool(re.search(r'Δ[εén]|Clearing\s+point|γ1|K\d|V[HV]', part))
                has_delta = bool(re.search(r'Δ[εé]|dielectric\s+anisotropy', part, re.IGNORECASE))
                
                result['examples'].append({
                    'type': ex_type,
                    'number': num,
                    'content': part[:5000],
                    'content_length': len(part),
                    'has_table': has_table,
                    'has_dielectric_value': has_delta,
                })
    
    # 如果 example_table_data 為空，嘗試從 description 中定位
    desc = patent_data.get('description', '')
    if not result['examples'] and desc:
        result = _extract_examples_from_desc(desc)
        result['source'] = 'structured_desc_fallback'
    
    result['example_count'] = len(result['examples'])
    
    # 品質評判
    if result['example_count'] == 0:
        result['quality'] = 'failure'
    elif any(ex.get('has_table') for ex in result['examples']) and result['example_count'] >= 2:
        result['quality'] = 'good'
    elif result['example_count'] >= 1:
        result['quality'] = 'partial'
    else:
        result['quality'] = 'failure'
    
    return result


def _extract_examples_from_desc(text: str) -> Dict[str, Any]:
    """
    從 description 文本中提取實施例（v11 三級定位策略）。
    
    策略 1: 正則匹配 "Example 1" / "Synthesis Example 1" 等編號關鍵字
    策略 2: 高段落編號區域 ([0150]+) 之後的 Example 關鍵字
    策略 3: 文本後 40% 搜索 Example/Embodiment 關鍵字
    """
    result = {
        'examples': [],
        'example_count': 0,
        'source': 'structured',
        'quality': 'unknown',
        'location_info': {},
    }
    
    # ===== 策略 1: 正則匹配編號 Example =====
    example_section_start = None
    
    # 找第一個 Example 1 的位置
    for pattern_str, _ in EXAMPLE_PATTERNS:
        match = re.search(pattern_str, text)
        if match:
            # 確認不是 "for example"
            start = max(0, match.start() - 20)
            prefix = text[start:match.start()]
            if not FOR_EXAMPLE_EXCLUDE.search(prefix):
                example_section_start = match.start()
                break
    
    # ===== 策略 2: 高段落編號 =====
    if example_section_start is None:
        high_para_match = re.search(r'\[\d{4,}\]', text)
        if high_para_match:
            para_num = int(high_para_match.group()[1:-1])
            if para_num >= 150:
                # 在此段落之後搜尋 Example
                after = text[high_para_match.start():]
                ex_match = re.search(r'(?:Example|EXAMPLE)\s+#?\s*(\d+)', after)
                if ex_match and not FOR_EXAMPLE_EXCLUDE.search(after[:ex_match.start()][-20:]):
                    example_section_start = high_para_match.start() + ex_match.start()
    
    # ===== 策略 3: 後 40% =====
    if example_section_start is None:
        tail_start = int(len(text) * 0.60)
        tail = text[tail_start:]
        ex_match = re.search(r'(?:Example|EXAMPLE)\s+#?\s*(\d+)', tail)
        if ex_match and not FOR_EXAMPLE_EXCLUDE.search(tail[:ex_match.start()][-20:]):
            example_section_start = tail_start + ex_match.start()
    
    result['location_info']['example_section_start'] = example_section_start
    result['location_info']['relative_position'] = (
        example_section_start / len(text) if (example_section_start and text) else None
    )
    
    if example_section_start is None:
        return result
    
    # 提取 example section
    example_section = text[example_section_start:]
    
    # 按 Example 標題分割
    parts = re.split(r'\n(?=(?:Example|EXAMPLE|Working|Synthesis|Comparative)\s+#?\s*\d+)', example_section)
    
    for part in parts[1:]:  # 跳過第一部分（過渡文字）
        part = part.strip()
        if len(part) < 50:
            continue
        
        num_match = re.search(r'(?:Example|EXAMPLE)?\s*#?\s*(\d+)', part)
        num = int(num_match.group(1)) if num_match else 0
        
        if re.search(r'Comparative|COMPARATIVE', part, re.IGNORECASE):
            ex_type = 'comparative_example'
        elif re.search(r'Synthesis|SYNTHESIS|Preparative', part, re.IGNORECASE):
            ex_type = 'synthesis_example'
        elif re.search(r'Working|WORKING', part, re.IGNORECASE):
            ex_type = 'working_example'
        else:
            ex_type = 'example_generic'
        
        has_table = bool(re.search(r'Δ[εén]|Clearing\s+point|γ1|K\d|V[HV]', part))
        has_delta = bool(re.search(r'Δ[εé]|dielectric\s+anisotropy', part, re.IGNORECASE))
        
        result['examples'].append({
            'type': ex_type,
            'number': num,
            'content': part[:5000],
            'content_length': len(part),
            'has_table': has_table,
            'has_dielectric_value': has_delta,
        })
    
    # 保底：段落分割
    if not result['examples']:
        parts2 = re.split(r'\n(?=(?:Example|EXAMPLE)\s+\d+)', example_section)
        for part in parts2[1:]:
            part = part.strip()
            if len(part) > 50:
                num_match = re.search(r'(?:Example|EXAMPLE)\s+(\d+)', part)
                num = int(num_match.group(1)) if num_match else 0
                result['examples'].append({
                    'type': 'example_fallback',
                    'number': num,
                    'content': part[:5000],
                    'content_length': len(part),
                    'has_table': bool(re.search(r'Δ[εén]|Clearing\s+point|γ1|K\d|V[HV]', part)),
                    'has_dielectric_value': bool(re.search(r'Δ[εé]|dielectric\s+anisotropy', part, re.IGNORECASE)),
                })
    
    result['example_count'] = len(result['examples'])
    return result


def extract_examples_track2(patent_data: Dict) -> Dict[str, Any]:
    """
    Track 2: Tail-Emergency 實施例提取。
    
    當 Track 1 結構化欄位為空時，掃描 description 最後 20%，
    尋找任何 Example 關鍵字（排除 "for example" 誤匹配）。
    
    Returns:
        dict with 'found', 'matches', 'recovery_source'
    """
    desc = patent_data.get('description', '')
    
    result = {
        'found': False,
        'matches': [],
        'recovery_source': 'failed',
    }
    
    if not desc or len(desc) < 500:
        return result
    
    # 掃描最後 20%
    tail_start = int(len(desc) * 0.80)
    tail = desc[tail_start:]
    
    for pattern_str, pattern_type in EXAMPLE_PATTERNS:
        matches = re.findall(pattern_str, tail)
        for m in matches:
            num = int(m) if m.isdigit() else 0
            # 排除 "for example"
            # 找到這個匹配的上下文
            match_obj = re.search(pattern_str.replace(r'(\d+)', str(num)), tail)
            if match_obj:
                start = max(0, match_obj.start() - 30)
                prefix = tail[start:match_obj.start()]
                if FOR_EXAMPLE_EXCLUDE.search(prefix):
                    continue
            
            result['matches'].append({
                'type': pattern_type,
                'number': num,
                'relative_position_in_tail': match_obj.start() / len(tail) if match_obj else None,
            })
    
    if result['matches']:
        result['found'] = True
        result['recovery_source'] = 'tail_emergency'
    else:
        # 嘗試 Embodiment 關鍵字
        embodiment_matches = re.findall(
            r'(?:Embodiment|EMBODIMENT)\s*#?\s*(\d+)', tail
        )
        for num_str in embodiment_matches:
            result['matches'].append({
                'type': 'embodiment',
                'number': int(num_str),
            })
        
        if result['matches']:
            result['found'] = True
            result['recovery_source'] = 'tail_emergency_embodiment'
    
    return result


def extract_examples_dual_track(patent_data: Dict) -> Dict[str, Any]:
    """
    雙軌實施例提取：Track 1 優先，Track 2 補救。
    
    Returns:
        dict with 'examples', 'example_count', 'quality',
                  'recovery_source', 'track1', 'track2'
    """
    # Track 1: 結構化提取
    track1 = extract_examples_track1(patent_data)
    
    # Track 2: Tail-Emergency
    track2 = extract_examples_track2(patent_data)
    
    # 決定使用哪個軌道
    if track1['example_count'] > 0:
        # Track 1 成功
        return {
            'examples': track1['examples'],
            'example_count': track1['example_count'],
            'quality': track1['quality'],
            'recovery_source': 'structured',
            'location_info': track1.get('location_info', {}),
            'track1': track1,
            'track2': track2,
        }
    elif track2['found']:
        # Track 1 失敗但 Track 2 找到痕跡
        # 將 track2 的匹配轉換為 example 格式
        examples = []
        for m in track2['matches']:
            examples.append({
                'type': m['type'],
                'number': m.get('number', 0),
                'content': f"[Tail-emergency detection: {m['type']} #{m.get('number', '?')}]",
                'content_length': 0,
                'has_table': False,
                'has_dielectric_value': False,
            })
        
        return {
            'examples': examples,
            'example_count': len(examples),
            'quality': 'tail_emergency_partial',
            'recovery_source': 'tail_emergency',
            'location_info': {},
            'track1': track1,
            'track2': track2,
        }
    else:
        # 雙軌均失敗
        return {
            'examples': [],
            'example_count': 0,
            'quality': 'failure',
            'recovery_source': 'failed',
            'location_info': {},
            'track1': track1,
            'track2': track2,
        }


# ============================================================
# Part 3: Claim 1 多模式匹配 + 品質評分
# ============================================================

CLAIM1_PATTERNS = [
    (r'WHAT IS CLAIMED IS:\s*(?:1\.\s*)([\s\S]{50,}?(?:;\s*or\s*[\s\S]*?)*?(?=\n\n2\.|\n\nCLAIMS|\n\nABSTRACT|$))',
     "WHAT_IS_CLAIMED", 1.0),
    (r'CLAIMS\s*(?:1\.\s*)([\s\S]{50,}?(?=\n\n2\.|\n\nABSTRACT|$))',
     "CLAIMS_HEADER", 0.9),
    (r'(?:Claim\s+1|第\s*1\s*項)\s*[:.\s]*([\s\S]{50,}?(?=2\.|摘要|ABSTRACT|$))',
     "CLAIM_1_HEADER", 0.85),
    (r'1\.\s+([^\n]{30,}?(?:\n[^\n]*){1,10}?(?=\n\n2\.|\n\n|\Z))',
     "LOOSE_NUMBERED", 0.8),
    (r'申請專利範圍\s*1\.([\s\S]{30,}?(?=2\.|$))',
     "CHINESE_FORMAT", 0.85),
    (r'1\.\s+([\s\S]{50,}?(?=\n\n2\.|\n\n|\Z))',
     "MINIMAL_FALLBACK", 0.7),
]


def extract_claim1_v13(text: str) -> Dict[str, Any]:
    """
    v13 Claim 1 提取：多模式匹配 + 品質評分。
    
    Returns:
        dict with 'claim1', 'pattern_name', 'confidence', 'quality_flags'
    """
    if not text:
        return {'claim1': None, 'pattern_name': 'no_input', 'confidence': 0.0, 'quality_flags': []}
    
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
                quality_flags = []
                
                # 關鍵詞加分
                keywords = ['comprising', 'wherein', 'characterized by', '包括', '特徵在於',
                           'consisting of', 'composition', 'compound', 'liquid crystal']
                found_kw = [kw for kw in keywords if kw.lower() in claim1.lower()]
                if found_kw:
                    confidence += 0.15
                    quality_flags.append(f'keywords:{len(found_kw)}')
                
                # 化學式/物理參數加分
                if re.search(r'[A-Z]-\d-[A-Z]|wt%|molecular|formula|Δ[εé]|dielectric', claim1, re.IGNORECASE):
                    confidence += 0.10
                    quality_flags.append('has_technical_terms')
                
                # 長度適中加分
                if 100 <= len(claim1) <= 5000:
                    confidence += 0.05
                    quality_flags.append('length_appropriate')
                
                # 警告：過長可能是錯誤匹配
                if len(claim1) > 5000:
                    confidence -= 0.20
                    quality_flags.append('WARNING_overly_long')
                
                # 警告：看起來像 description 而非 claim
                if re.search(r'(?:background|prior art|field of invention)', claim1, re.IGNORECASE):
                    confidence -= 0.30
                    quality_flags.append('WARNING_looks_like_description')
                
                results.append({
                    'claim1': claim1,
                    'pattern_name': pattern_name,
                    'confidence': min(max(confidence, 0.0), 1.0),
                    'quality_flags': quality_flags,
                })
        except Exception:
            continue
    
    if not results:
        return {'claim1': None, 'pattern_name': 'no_match', 'confidence': 0.0, 'quality_flags': []}
    
    results.sort(key=lambda x: x['confidence'], reverse=True)
    return results[0]


# ============================================================
# Part 4: Description 截斷檢測
# ============================================================

def detect_truncation(description: str) -> Dict[str, Any]:
    """
    檢測 description 是否被截斷。
    
    Google Patents 頁面截斷特徵：
    - 長度精確為 50000 或 80000 字元
    - 結尾不完整（非句號/問號/感歎號/右括號結束）
    - 實施例區段 (relative position > 0.80) 缺失
    
    Returns:
        dict with 'is_truncated', 'confidence', 'evidence', 'likely_lost_examples'
    """
    result = {
        'is_truncated': False,
        'confidence': 0.0,
        'evidence': [],
        'likely_lost_examples': False,
    }
    
    if not description:
        return result
    
    desc_len = len(description)
    
    # 特徵 1: 長度精確匹配截斷閾值
    if desc_len in (50000, 80000):
        result['evidence'].append(f'Length exactly {desc_len} (truncation threshold)')
        result['is_truncated'] = True
        result['confidence'] = 0.90
    
    # 特徵 2: 長度接近截斷閾值（±200）
    if 49800 <= desc_len <= 50200 or 79800 <= desc_len <= 80200:
        if not result['is_truncated']:
            result['evidence'].append(f'Length near truncation threshold: {desc_len}')
            result['is_truncated'] = True
            result['confidence'] = max(result['confidence'], 0.80)
    
    # 特徵 3: 結尾不完整
    last_char = description.rstrip()[-1] if description else ''
    if last_char not in '.!?:;]\'")' and desc_len > 10000:
        result['evidence'].append(f'Ends with incomplete character: "{last_char}"')
        if not result['is_truncated']:
            result['is_truncated'] = True
            result['confidence'] = max(result['confidence'], 0.60)
    
    # 特徵 4: 無 Example 關鍵字在後 20%
    if desc_len > 1000:
        tail = description[int(desc_len * 0.80):]
        if not re.search(r'(?:Example|EXAMPLE|Embodiment)\s+#?\s*\d+', tail):
            result['evidence'].append('No numbered examples in last 20% of description')
            result['likely_lost_examples'] = True
            if result['is_truncated']:
                result['confidence'] = min(result['confidence'] + 0.05, 1.0)
    
    return result


# ============================================================
# Part 5: 線上全文提取 (需 Playwright)
# ============================================================

def fetch_full_patent_text(url: str) -> Dict[str, Any]:
    """
    使用 Playwright 獲取專利全文（解決截斷問題）。
    
    關鍵：滾動頁面載入完整內容，避免 50k/80k 截斷。
    
    Args:
        url: Google Patents URL
    
    Returns:
        dict with 'success', 'text', 'html', 'title', 'error'
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {
            'success': False,
            'error': 'playwright not installed. Run: pip install playwright && playwright install chromium',
        }
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until='domcontentloaded', timeout=60000)
            
            # 滾動載入完整內容
            page.evaluate("""
                async () => {
                    const delay = ms => new Promise(r => setTimeout(r, ms));
                    for (let i = 0; i < 30; i++) {
                        window.scrollBy(0, 2000);
                        await delay(1500);
                    }
                    window.scrollTo(0, 0);
                    await delay(2000);
                }
            """)
            
            page.wait_for_timeout(3000)
            
            text = page.inner_text('body')
            html = page.content()
            title = page.title()
            
            browser.close()
            
            return {
                'success': True,
                'text': text,
                'html': html,
                'title': title,
                'text_length': len(text),
            }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
        }


# ============================================================
# Part 6: 完整專利提取 (線上模式)
# ============================================================

def extract_patent_full_v13(url: str) -> Dict[str, Any]:
    """
    v13 完整提取流程（線上，需 Playwright）。
    
    Steps:
    1. 全文獲取 (Playwright + 滾動)
    2. Claim 1 多模式匹配 + 品質評分
    3. Abstract 提取
    4. 雙軌實施例提取
    5. 四層 Δε 分類
    6. 截斷檢測
    7. 日期提取
    """
    # Step 1: 全文獲取
    page_data = fetch_full_patent_text(url)
    
    if not page_data.get('success'):
        return {
            'success': False,
            'url': url,
            'error': page_data.get('error', 'Unknown error'),
            'version': 'v13',
        }
    
    text = page_data['text']
    html = page_data['html']
    title = page_data['title']
    
    # Step 2: Claim 1
    claim1_result = extract_claim1_v13(text)
    
    # Step 3: Abstract
    abstract = ''
    abstract_match = re.search(
        r'Abstract\s*([\s\S]{50,}?)(?=\n\n(?:Description|Claims|TECHNICAL|BACKGROUND)|$)',
        text, re.IGNORECASE
    )
    if abstract_match:
        abstract = abstract_match.group(1).strip()
    else:
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'lxml')
            meta_abstract = soup.find('meta', attrs={'name': 'citation_abstract'})
            if meta_abstract:
                abstract = meta_abstract.get('content', '')
        except ImportError:
            pass
    
    # Step 4: 構建 patent_data 供雙軌提取和 Δε 分類使用
    patent_data = {
        'abstract': abstract,
        'claim1': claim1_result.get('claim1', ''),
        'description': text,  # Playwright 取得全文
        'example_table_data': '',
    }
    
    # Step 5: 雙軌實施例提取
    examples_result = extract_examples_dual_track(patent_data)
    
    # Step 6: 四層 Δε 分類
    # 把 examples 中的 Δε 數值注入 example_table_data 供 Layer 3 使用
    if examples_result['examples']:
        delta_contents = []
        for ex in examples_result['examples']:
            if ex.get('has_dielectric_value') or ex.get('has_table'):
                delta_contents.append(ex.get('content', ''))
        patent_data['example_table_data'] = '\n'.join(delta_contents)
    
    da_result = classify_delta_epsilon_v13(patent_data)
    
    # Step 7: 截斷檢測
    truncation = detect_truncation(patent_data.get('description', ''))
    
    # Step 8: 專利號
    patent_number = None
    url_match = re.search(r'patent/([A-Z]{2,4}\d+[A-Z]?)', url)
    if url_match:
        patent_number = url_match.group(1)
    else:
        title_match = re.search(r'([A-Z]{2,4}\d+[A-Z]?)\s*[-–]', title)
        if title_match:
            patent_number = title_match.group(1)
    
    # Step 9: 日期提取
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
    
    return {
        'success': True,
        'url': url,
        'version': 'v13',
        'patent_number': patent_number,
        'title': title,
        'abstract': abstract[:3000],
        'claim1': claim1_result.get('claim1'),
        'claim1_pattern': claim1_result.get('pattern_name'),
        'claim1_confidence': claim1_result.get('confidence', 0.0),
        'claim1_quality_flags': claim1_result.get('quality_flags', []),
        'claim1_length': len(claim1_result.get('claim1') or ''),
        'dates': dates,
        'examples': examples_result,
        'dielectric_anisotropy': da_result,
        'is_negative_da': da_result['is_negative_da'],
        'da_classification': da_result['classification'],
        'da_confidence': da_result['confidence'],
        'da_layer': da_result['layer'],
        'da_warnings': da_result.get('warnings', []),
        'truncation': truncation,
        'text_length': len(text),
    }


# ============================================================
# Part 7: 離線改進分析 (--reanalyze 模式)
# ============================================================

def reanalyze_existing_data_v13(json_file: str, output_file: str) -> Dict[str, Any]:
    """
    v13 離線分析：對 final_18_merged.json 重新判定 Δε 和實施例。
    
    不需要 Playwright，直接對現有資料重新分析：
    1. 四層 Δε 分類器重新判定
    2. 雙軌實施例提取（Track 1 結構化 + Track 2 tail-emergency）
    3. 截斷檢測
    4. Claim1 品質評估
    5. 生成改進建議
    
    Args:
        json_file: 輸入 JSON 路徑 (final_18_merged.json)
        output_file: 輸出 JSON 路徑
    
    Returns:
        dict with 'results', 'summary'
    """
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    results = {}
    
    for pid, p in data.items():
        # ===== Δε 四層分類 =====
        da_result = classify_delta_epsilon_v13(p)
        
        # ===== 雙軌實施例提取 =====
        examples_result = extract_examples_dual_track(p)
        
        # ===== 截斷檢測 =====
        truncation = detect_truncation(p.get('description', ''))
        
        # ===== Claim1 品質評估 =====
        claim1_text = p.get('claim1', '')
        claim1_quality = {
            'length': len(claim1_text),
            'has_keywords': any(kw in claim1_text.lower() for kw in 
                              ['comprising', 'wherein', 'characterized', '包括', '特徵在於']),
            'has_technical_terms': bool(re.search(
                r'dielectric|anisotrop|liquid\s+crystal|compound|composition', claim1_text, re.I)),
            'needs_reextract': p.get('claim1_needs_reextract', False),
        }
        
        # ===== 比較新舊判定 =====
        original_is_neg = p.get('is_negative_da')
        new_is_neg = da_result['is_negative_da']
        judgment_changed = (
            (original_is_neg is not None) and (new_is_neg is not None) and
            (original_is_neg != new_is_neg)
        )
        
        # ===== 改進建議 =====
        recommendations = []
        
        if truncation['is_truncated']:
            recommendations.append({
                'action': 'refetch_full_text',
                'reason': f'Description truncated (len={len(p.get("description",""))}, '
                         f'confidence={truncation["confidence"]:.2f})',
                'priority': 'high',
            })
        
        if examples_result['quality'] == 'failure':
            recommendations.append({
                'action': 'refetch_for_examples',
                'reason': 'No examples found (likely due to truncation)',
                'priority': 'high',
            })
        
        if judgment_changed:
            recommendations.append({
                'action': 'update_da_judgment',
                'reason': f'Δε changed: {original_is_neg} -> {new_is_neg} '
                         f'(layer={da_result["layer"]}, confidence={da_result["confidence"]:.2f})',
                'priority': 'critical',
            })
        
        if da_result['classification'] in (CLASS_LIKELY_NEG, CLASS_LIKELY_POS):
            recommendations.append({
                'action': 'confirm_da_with_full_text',
                'reason': f'Δε only inferred from Layer 4 (desc_tail), confidence={da_result["confidence"]:.2f}',
                'priority': 'medium',
            })
        
        if claim1_quality['needs_reextract'] or claim1_quality['length'] < 100:
            recommendations.append({
                'action': 'reextract_claim1',
                'reason': f'Claim1 quality issue (len={claim1_quality["length"]}, '
                         f'needs_reextract={claim1_quality["needs_reextract"]})',
                'priority': 'medium',
            })
        
        results[pid] = {
            'patent_id': pid,
            # Δε 判定
            'original_is_negative_da': original_is_neg,
            'v13_is_negative_da': new_is_neg,
            'v13_da_classification': da_result['classification'],
            'v13_da_confidence': da_result['confidence'],
            'v13_da_layer': da_result['layer'],
            'v13_da_warnings': da_result.get('warnings', []),
            'v13_da_evidence': da_result['evidence'],
            'judgment_changed': judgment_changed,
            # 實施例
            'example_count': examples_result['example_count'],
            'example_quality': examples_result['quality'],
            'example_recovery_source': examples_result['recovery_source'],
            'examples_summary': [
                {'type': ex['type'], 'number': ex['number'],
                 'has_table': ex.get('has_table', False),
                 'has_delta': ex.get('has_dielectric_value', False)}
                for ex in examples_result.get('examples', [])[:10]
            ],
            # 截斷
            'description_truncated': truncation['is_truncated'],
            'truncation_confidence': truncation['confidence'],
            'truncation_evidence': truncation['evidence'],
            'likely_lost_examples': truncation['likely_lost_examples'],
            # Claim1 品質
            'claim1_quality': claim1_quality,
            # 改進建議
            'recommendations': recommendations,
        }
    
    # 保存結果
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    # 統計
    total = len(data)
    changed = sum(1 for r in results.values() if r['judgment_changed'])
    truncated = sum(1 for r in results.values() if r['description_truncated'])
    no_examples = sum(1 for r in results.values() if r['example_count'] == 0)
    has_examples = sum(1 for r in results.values() if r['example_count'] > 0)
    tail_recovered = sum(1 for r in results.values() if r['example_recovery_source'] == 'tail_emergency')
    layer_counts = {}
    for r in results.values():
        layer = r['v13_da_layer']
        layer_counts[layer] = layer_counts.get(layer, 0) + 1
    
    critical_recs = sum(1 for r in results.values() 
                       if any(rec['priority'] == 'critical' for rec in r['recommendations']))
    high_recs = sum(1 for r in results.values() 
                   if any(rec['priority'] == 'high' for rec in r['recommendations']))
    
    summary = {
        'total': total,
        'da_judgment_changed': changed,
        'da_layer_distribution': layer_counts,
        'description_truncated': truncated,
        'no_examples': no_examples,
        'has_examples': has_examples,
        'tail_emergency_recovered': tail_recovered,
        'critical_recommendations': critical_recs,
        'high_recommendations': high_recs,
    }
    
    print(f"\n{'='*80}")
    print(f"v13 離線改進分析結果")
    print(f"{'='*80}")
    print(f" 總專利數：{total}")
    print(f" Δε 判定變更：{changed} 篇")
    print(f" Δε 判定層級分佈：{layer_counts}")
    print(f" Description 截斷：{truncated}/{total}")
    print(f" 實施例：有 {has_examples} / 無 {no_examples} / tail-emergency {tail_recovered}")
    print(f" 改進建議：critical={critical_recs}, high={high_recs}")
    
    if changed > 0:
        print(f"\n--- Δε 判定變更明細 ---")
        for pid, r in results.items():
            if r['judgment_changed']:
                orig = r['original_is_negative_da']
                new = r['v13_is_negative_da']
                layer = r['v13_da_layer']
                conf = r['v13_da_confidence']
                print(f"  {pid}: {'neg' if orig else 'pos'} -> {'neg' if new else 'pos'} "
                      f"(Layer: {layer}, confidence: {conf:.2f})")
    
    print(f"\n--- 各專利詳細 ---")
    for pid in sorted(results.keys()):
        r = results[pid]
        da_str = r['v13_da_classification']
        ex_count = r['example_count']
        ex_src = r['example_recovery_source']
        trunc = 'TRUNC' if r['description_truncated'] else 'ok'
        rec_count = len(r['recommendations'])
        print(f"  {pid}: Δε={da_str}({r['v13_da_confidence']:.2f}) "
              f"ex={ex_count}({ex_src}) desc={trunc} recs={rec_count}")
    
    print(f"\n結果已保存：{output_file}")
    
    return {'results': results, 'summary': summary}


# ============================================================
# Part 8: 批量線上提取 (--batch 模式)
# ============================================================

def batch_extract_v13(urls: List[str], output_file: str, delay: float = 2.0) -> List[Dict]:
    """
    v13 批量線上提取（需 Playwright）。
    
    Args:
        urls: 專利 URL 列表
        output_file: 輸出 JSON 路徑
        delay: 請求間延遲秒數
    """
    print("=" * 100)
    print("Patent Extract v13 — 四層 Δε 分類器 + 雙軌實施例提取")
    print("核心改進：(1) 四層 Δε 分類 (2) 雙軌實施例 (3) Claim1 品質評分 (4) 截斷檢測")
    print("=" * 100)
    
    extracted = []
    
    for i, url in enumerate(urls, 1):
        print(f"\n[{i}/{len(urls)}] 提取：{url}")
        
        result = extract_patent_full_v13(url)
        extracted.append(result)
        
        if result['success']:
            pid = result.get('patent_number', 'N/A')
            da_class = result.get('da_classification', 'N/A')
            da_conf = result.get('da_confidence', 0)
            da_layer = result.get('da_layer', 'N/A')
            ex_count = result.get('examples', {}).get('example_count', 0)
            ex_quality = result.get('examples', {}).get('quality', 'unknown')
            claim1_len = result.get('claim1_length', 0)
            trunc = 'TRUNC' if result.get('truncation', {}).get('is_truncated') else 'ok'
            
            print(f"  ✓ {pid}")
            print(f"  Claim1: {claim1_len} chars (pattern: {result.get('claim1_pattern', 'N/A')})")
            print(f"  Examples: {ex_count} (quality: {ex_quality})")
            print(f"  Δε: {da_class} (confidence: {da_conf:.2f}, layer: {da_layer})")
            print(f"  Truncation: {trunc}")
            
            if result.get('da_warnings'):
                for w in result['da_warnings']:
                    print(f"  ⚠️ {w}")
        else:
            print(f"  ✗ 失敗 — {result.get('error', 'Unknown')}")
        
        if i < len(urls):
            time.sleep(delay)
    
    # 保存
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(extracted, f, ensure_ascii=False, indent=2)
    
    # 統計
    success = sum(1 for p in extracted if p['success'])
    claim1_ok = sum(1 for p in extracted if p.get('claim1'))
    ex_ok = sum(1 for p in extracted if p.get('examples', {}).get('example_count', 0) > 0)
    neg_count = sum(1 for p in extracted if p.get('is_negative_da') == True)
    pos_count = sum(1 for p in extracted if p.get('is_negative_da') == False)
    undet_count = sum(1 for p in extracted if p.get('is_negative_da') is None)
    trunc_count = sum(1 for p in extracted if p.get('truncation', {}).get('is_truncated'))
    
    print(f"\n{'='*100}")
    print(f"v13 批量提取統計")
    print(f"{'='*100}")
    print(f" 成功：{success}/{len(extracted)}")
    print(f" Claim1：{claim1_ok}/{len(extracted)}")
    print(f" 實施例：{ex_ok}/{len(extracted)}")
    print(f" Δε：neg={neg_count} / pos={pos_count} / undet={undet_count}")
    print(f" 截斷：{trunc_count}/{len(extracted)}")
    print(f" 保存：{output_file}")
    
    return extracted


# ============================================================
# Main
# ============================================================

if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == '--reanalyze':
        # 離線分析模式
        json_file = sys.argv[2] if len(sys.argv) > 2 else '/tmp/final_18_merged.json'
        output_file = sys.argv[3] if len(sys.argv) > 3 else '/tmp/v13_reanalysis_results.json'
        reanalyze_existing_data_v13(json_file, output_file)
    
    elif len(sys.argv) > 1 and sys.argv[1] == '--batch':
        # 批量線上提取模式
        urls_file = sys.argv[2] if len(sys.argv) > 2 else '/tmp/patent_urls.json'
        output_file = sys.argv[3] if len(sys.argv) > 3 else '/tmp/v13_extracted_patents.json'
        
        with open(urls_file, 'r', encoding='utf-8') as f:
            urls_data = json.load(f)
        
        if isinstance(urls_data, list):
            urls = [u if isinstance(u, str) else u.get('url', '') for u in urls_data]
        elif isinstance(urls_data, dict):
            urls = [p.get('url', '') for p in urls_data.values()]
        else:
            urls = []
        
        urls = [u for u in urls if u]
        batch_extract_v13(urls, output_file)
    
    else:
        print("Patent Extract v13 — 四層 Δε 分類器 + 雙軌實施例提取")
        print()
        print("用法：")
        print("  python patent_extract_v13_refined.py --reanalyze [input.json] [output.json]")
        print("  python patent_extract_v13_refined.py --batch [urls.json] [output.json]")
        print()
        print("  --reanalyze: 離線分析現有 JSON 資料（不需 Playwright）")
        print("  --batch: 線上批量提取（需 Playwright）")
        print()
        print("四層 Δε 分類器：")
        print("  Layer 1: Abstract (0.95)")
        print("  Layer 2: Claim 1 (0.90)")
        print("  Layer 3: Example Table Data (0.85)")
        print("  Layer 4: Description Tail — last 20% only (0.60)")
        print()
        print("雙軌實施例提取：")
        print("  Track 1: 結構化欄位 (example_table_data / description)")
        print("  Track 2: Tail-Emergency (最後 20% 掃描)")
