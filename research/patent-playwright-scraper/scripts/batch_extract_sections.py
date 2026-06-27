#!/usr/bin/env python3
"""
批量提取專利結構化段落（Background/Summary/Claim1/Claim2/Examples）
每篇專利在獨立進程中提取，避免 sync_playwright asyncio 衝突。
輸出: sections_batch_N.json
"""
import json
import sys
import os
import subprocess
import time

SKILL_DIR = '/data/.hermes/skills/research/patent-playwright-scraper'
REPORTS_DIR = os.path.join(SKILL_DIR, 'reports')
EXTRACTOR = os.path.join(SKILL_DIR, 'scripts', 'tech_feature_generator.py')

# 獨立進程提取單篇專利的內聯腳本
INLINE_SCRIPT = '''
import sys
import json
sys.path.insert(0, "{skill_dir}/scripts")
from tech_feature_generator import extract_patent_sections, build_tech_feature_prompt

url = sys.argv[1]
pid = sys.argv[2]

print(f"  Extracting sections for {{pid}}...", flush=True)
sections = extract_patent_sections(url)

# 統計
bg_len = len(sections.get('background', ''))
sum_len = len(sections.get('summary', ''))
c1_len = len(sections.get('claim_1', ''))
c2_len = len(sections.get('claim_2', ''))
ex_count = len(sections.get('examples', []))
desc_len = sections.get('description_len', 0)
abs_len = len(sections.get('abstract', ''))

print(f"  {{pid}}: desc={{desc_len}} bg={{bg_len}} sum={{sum_len}} c1={{c1_len}} c2={{c2_len}} ex={{ex_count}} abs={{abs_len}}", flush=True)

# 組裝 prompt
prompt = build_tech_feature_prompt(sections)
sections['prompt'] = prompt

# 輸出 JSON
print(json.dumps(sections, ensure_ascii=False))
'''.format(skill_dir=SKILL_DIR)


def extract_single(url, pid, timeout=90):
    """用獨立進程提取單篇專利段落"""
    try:
        result = subprocess.run(
            [sys.executable, '-c', INLINE_SCRIPT, url, pid],
            capture_output=True, text=True, timeout=timeout
        )
        if result.returncode != 0:
            print(f"  ❌ {pid} failed: {result.stderr[:200]}", flush=True)
            return None
        
        # 找最後一行 JSON
        lines = result.stdout.strip().split('\n')
        for line in reversed(lines):
            line = line.strip()
            if line.startswith('{') and line.endswith('}'):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        
        print(f"  ❌ {pid}: no JSON in output", flush=True)
        return None
    except subprocess.TimeoutExpired:
        print(f"  ⏰ {pid}: timeout ({timeout}s)", flush=True)
        return None
    except Exception as e:
        print(f"  ❌ {pid}: {e}", flush=True)
        return None


def main():
    batch_num = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    batch_size = int(sys.argv[2]) if len(sys.argv) > 2 else 7
    
    # 讀取專利清單
    with open(os.path.join(REPORTS_DIR, 'contrast_final_list.json'), 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    patents = data.get('final_patents', [])
    start = (batch_num - 1) * batch_size
    end = min(start + batch_size, len(patents))
    batch = patents[start:end]
    
    print(f"Batch {batch_num}: patents [{start}:{end}] ({len(batch)} patents)", flush=True)
    
    results = {}
    for i, p in enumerate(batch):
        pid = p.get('patent_id', p.get('patent_number', 'N/A'))
        url = p.get('url', '')
        print(f"\n[{i+1}/{len(batch)}] {pid} - {url}", flush=True)
        
        sections = extract_single(url, pid)
        if sections:
            results[pid] = sections
            # 即時保存
            out_path = os.path.join(REPORTS_DIR, f'sections_{pid}.json')
            with open(out_path, 'w', encoding='utf-8') as f:
                json.dump(sections, f, ensure_ascii=False, indent=2)
            print(f"  ✅ Saved to {out_path}", flush=True)
        else:
            print(f"  ❌ Failed to extract {pid}", flush=True)
        
        time.sleep(1)
    
    # 批次摘要
    print(f"\n{'='*60}", flush=True)
    print(f"Batch {batch_num} complete: {len(results)}/{len(batch)} successful", flush=True)
    
    # 保存批次結果
    batch_path = os.path.join(REPORTS_DIR, f'sections_batch_{batch_num}.json')
    with open(batch_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"Batch saved to {batch_path}", flush=True)


if __name__ == '__main__':
    main()
