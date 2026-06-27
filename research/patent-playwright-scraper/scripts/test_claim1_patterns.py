#!/usr/bin/env python3
"""
測試方案 A：改進 Claim 1 正則表達式
測試 6 種不同正則模式 + 寬鬆匹配策略
"""

import re
import json
from typing import Optional, List, Tuple

# 6 種 Claim 1 正則模式
CLAIM1_PATTERNS = [
    # 模式 1: 標準 Google Patents 格式 (WHAT IS CLAIMED IS:)
    (r'WHAT IS CLAIMED IS:\s*(?:1\.\s*)([\s\S]*?(?:;\s*or\s*[\s\S]*?)+)', "標準格式 (WHAT IS CLAIMED)"),
    
    # 模式 2: CLAIMS 開頭
    (r'CLAIMS\s*(?:1\.\s*)([\s\S]*?(?:;\s*or\s*[\s\S]*?)+)', "CLAIMS 開頭"),
    
    # 模式 3: 簡單數字開頭 (寬鬆版，到分號或換行)
    (r'1\.\s+([^\n;]+(?:;[^\n;]+)*)', "簡單數字開頭 (寬鬆)"),
    
    # 模式 4: 到下一項為止 (使用 2. 作為邊界)
    (r'WHAT IS CLAIMED IS:\s*1\.\s+([\s\S]*?(?=2\.|$))', "到下一項為止"),
    
    # 模式 5: 最簡格式 (使用 2. 作為邊界)
    (r'1\.\s+([\s\S]*?(?=2\.|$))', "最簡格式"),
    
    # 模式 6: WO 格式 (針對 WO 專利的特殊格式)
    (r'(?:Claim 1|第 1 項|1\.)\s*[:\.\s]*([\s\S]*?(?:wherein|comprising|characterized by|包括 | 特徵在於)[\s\S]*?(?=2\.|$|摘要|ABSTRACT))', "WO 特殊格式"),
]

def extract_claim1_v1(text: str) -> Tuple[Optional[str], str, int]:
    """
    方案 A: 6 種模式多輪匹配
    返回：(claim1_text, pattern_name, confidence_score)
    """
    results = []
    
    for pattern, pattern_name in CLAIM1_PATTERNS:
        try:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                claim1 = match.group(1).strip()
                # 清理多餘空白
                claim1 = re.sub(r'\s+', ' ', claim1)
                
                # 計算置信度分數
                confidence = 0
                if len(claim1) > 100:
                    confidence += 40
                elif len(claim1) > 50:
                    confidence += 20
                
                # 檢查是否包含關鍵詞
                keywords = ['comprising', 'wherein', 'characterized by', '包括', '特徵在於', 'selected from']
                for kw in keywords:
                    if kw.lower() in claim1.lower():
                        confidence += 10
                        break
                
                # 檢查是否有化學式或專利術語
                if re.search(r'[A-Z]-\d-[A-Z]|wt%|molecular formula', claim1, re.IGNORECASE):
                    confidence += 15
                
                results.append((claim1, pattern_name, min(confidence, 100)))
        except Exception as e:
            continue
    
    if not results:
        return None, "無匹配", 0
    
    # 選擇置信度最高的結果
    results.sort(key=lambda x: x[2], reverse=True)
    best_claim, best_pattern, best_score = results[0]
    
    return best_claim, best_pattern, best_score


def test_on_sample_patents(sample_file: str = '/tmp/extracted_patents_v8.json'):
    """在樣本專利上測試 Claim 1 提取"""
    
    # 讀取樣本
    with open(sample_file, 'r', encoding='utf-8') as f:
        patents = json.load(f)
    
    print("=" * 100)
    print("方案 A 測試：改進 Claim 1 正則表達式 (6 種模式)")
    print("=" * 100)
    
    results = []
    
    for i, patent in enumerate(patents, 1):
        url = patent.get('url', '')
        old_claim1 = patent.get('claim_1', '')
        
        # 獲取完整文本 (如果有)
        text_file = '/tmp/patent_texts.json'  # 假設有完整文本存儲
        
        # 模擬測試
        result = {
            'url': url,
            'old_claim1_len': len(old_claim1) if old_claim1 else 0,
            'old_has_claim1': bool(old_claim1),
            'new_claim1': None,
            'new_pattern': None,
            'new_confidence': 0,
            'improved': False
        }
        
        results.append(result)
        
        status = "✓" if result['new_has_claim1'] else "✗"
        improvement = ""
        if result['old_has_claim1'] == False and result['new_has_claim1']:
            improvement = " [改進!]"
            result['improved'] = True
        
        print(f"\n[{i}/{len(patents)}] {url}")
        print(f"  舊版：{'有' if result['old_has_claim1'] else '無'} (長度：{result['old_claim1_len']})")
        print(f"  新版：{'有' if result['new_has_claim1'] else '無'} (模式：{result['new_pattern'] or '無'}, 置信度：{result['new_confidence']}){improvement}")
    
    # 統計
    old_success = sum(1 for r in results if r['old_has_claim1'])
    new_success = sum(1 for r in results if r['new_has_claim1'])
    improved_count = sum(1 for r in results if r['improved'])
    
    print("\n" + "=" * 100)
    print("統計結果")
    print("=" * 100)
    print(f"  舊版成功：{old_success}/{len(results)} ({old_success/len(results)*100:.1f}%)")
    print(f"  新版成功：{new_success}/{len(results)} ({new_success/len(results)*100:.1f}%)")
    print(f"  改進數量：{improved_count}")
    print(f"  改進幅度：+{improved_count/len(results)*100:.1f}%")
    
    return results


if __name__ == '__main__':
    # 測試用範例文本
    test_text_1 = """
    WHAT IS CLAIMED IS:
    1. A liquid crystal composition comprising:
       a) a first component selected from at least one compound represented by general formula (I);
       b) a second component selected from at least one compound represented by general formula (II);
       wherein the composition has negative dielectric anisotropy.
    2. The composition according to claim 1, further comprising...
    """
    
    test_text_2 = """
    CLAIMS
    1. An electro-optical display device comprising:
       (a) a liquid crystal layer having negative dielectric anisotropy;
       (b) an electrode structure for generating an electric field;
       wherein said liquid crystal molecules have an orientation angle βo.
    2. The device according to claim 1...
    """
    
    test_text_3 = """
    申請專利範圍
    1. 一種負介電液晶材料，其包含：
       a) 至少一種通式 (I) 所示之化合物；
       b) 至少一種通式 (II) 所示之化合物；
       其中該等材料具有負介電各向異性。
    2. 如申請專利範圍第 1 項所述之材料...
    """
    
    print("測試範例文本：")
    print("-" * 80)
    
    for i, text in enumerate([test_text_1, test_text_2, test_text_3], 1):
        claim1, pattern, confidence = extract_claim1_v1(text)
        print(f"\n範例 {i}:")
        print(f"  匹配模式：{pattern}")
        print(f"  置信度：{confidence}")
        print(f"  Claim 1 長度：{len(claim1) if claim1 else 0}")
        if claim1:
            print(f"  預覽：{claim1[:100]}...")
    
    print("\n" + "=" * 100)
    print("方案 A 測試完成")
    print("=" * 100)
