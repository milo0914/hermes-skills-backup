#!/usr/bin/env python3
"""
合併補充 sections 數據 + 組裝 tech feature prompt + 生成技術要點
從 contrast_final_list.json 補充 claim1/abstract 到 sections
然後用 build_tech_feature_prompt 組裝 prompt，保存供 LLM 調用
"""
import json
import os
import sys

REPORTS_DIR = '/data/.hermes/skills/research/patent-playwright-scraper/reports'
SKILL_DIR = '/data/.hermes/skills/research/patent-playwright-scraper'

def main():
    sys.path.insert(0, os.path.join(SKILL_DIR, 'scripts'))
    from tech_feature_generator import build_tech_feature_prompt
    
    # 讀取對比最終清單
    with open(os.path.join(REPORTS_DIR, 'contrast_final_list.json'), 'r', encoding='utf-8') as f:
        final_data = json.load(f)
    
    patents = final_data.get('final_patents', [])
    # 建立 patent_id -> patent_data 映射
    patent_map = {}
    for p in patents:
        pid = p.get('patent_id', p.get('patent_number', ''))
        patent_map[pid] = p
    
    results = {}
    
    for p in patents:
        pid = p.get('patent_id', p.get('patent_number', ''))
        section_path = os.path.join(REPORTS_DIR, f'sections_{pid}.json')
        
        if not os.path.exists(section_path):
            print(f"⚠️  {pid}: no sections file, skipping")
            continue
        
        with open(section_path, 'r', encoding='utf-8') as f:
            sec = json.load(f)
        
        # 補充 claim1: sections 中的 claim1 優先，fallback 到 contrast_final_list
        if not sec.get('claim_1') or len(sec.get('claim_1', '')) < 50:
            c1_from_list = patent_map.get(pid, {}).get('claim1', '')
            if c1_from_list and len(c1_from_list) > 50:
                sec['claim_1'] = c1_from_list
                print(f"  {pid}: claim1 supplemented from contrast_final_list ({len(c1_from_list)} chars)")
        
        # 補充 abstract
        if not sec.get('abstract') or len(sec.get('abstract', '')) < 50:
            ab_from_list = patent_map.get(pid, {}).get('abstract', '')
            if ab_from_list and len(ab_from_list) > 50:
                sec['abstract'] = ab_from_list
                print(f"  {pid}: abstract supplemented from contrast_final_list ({len(ab_from_list)} chars)")
        
        # 補充 claim2: 嘗試從 sections 中提取（如果之前沒有）
        # 無法從 contrast_final_list 補充 claim2（那裡沒有）
        
        # 組裝 prompt
        prompt = build_tech_feature_prompt(sec)
        sec['prompt'] = prompt
        
        # 保存更新後的 sections
        with open(section_path, 'w', encoding='utf-8') as f:
            json.dump(sec, f, ensure_ascii=False, indent=2)
        
        # 統計
        bg = len(sec.get('background', ''))
        sm = len(sec.get('summary', ''))
        c1 = len(sec.get('claim_1', ''))
        c2 = len(sec.get('claim_2', ''))
        ex = len(sec.get('examples', []))
        ab = len(sec.get('abstract', ''))
        
        quality = "GOOD" if (bg > 100 or sm > 100) and c1 > 50 else ("PARTIAL" if (bg > 100 or sm > 100 or c1 > 50) else "POOR")
        
        results[pid] = {
            'bg_len': bg, 'sum_len': sm, 'c1_len': c1, 'c2_len': c2,
            'ex_count': ex, 'abs_len': ab, 'quality': quality,
            'prompt_len': len(prompt)
        }
        
        print(f"  {pid}: bg={bg} sum={sm} c1={c1} c2={c2} ex={ex} abs={ab} | {quality} | prompt={len(prompt)}")
    
    # 保存彙總
    summary_path = os.path.join(REPORTS_DIR, 'sections_supplemented_summary.json')
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    good = sum(1 for r in results.values() if r['quality'] == 'GOOD')
    partial = sum(1 for r in results.values() if r['quality'] == 'PARTIAL')
    poor = sum(1 for r in results.values() if r['quality'] == 'POOR')
    
    print(f"\n{'='*60}")
    print(f"補充完成: {len(results)} 篇 | GOOD={good} | PARTIAL={partial} | POOR={poor}")

if __name__ == '__main__':
    main()
