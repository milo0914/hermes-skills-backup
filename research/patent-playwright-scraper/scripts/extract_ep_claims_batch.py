#!/usr/bin/env python3
"""
提取 EP 類專利的 Claims — 使用改進的 JS 策略
EP 類專利的 Claims 使用 <ol class="claims"><li class="claim"> 結構
"""
import json
import sys
import os
import subprocess
import time

SKILL_DIR = '/data/.hermes/skills/research/patent-playwright-scraper'
REPORTS_DIR = os.path.join(SKILL_DIR, 'reports')

EP_PATENTS = [
    'EP4400561A1', 'EP4702104A1', 'EP4720219A1', 'EP4502108A1',
    'EP4538349A1', 'EP4563675', 'EP4733370A1'
]

# 獨立提取腳本
EXTRACT_SCRIPT = os.path.join(SKILL_DIR, 'scripts', '_extract_ep_claims.py')


def main():
    with open(os.path.join(REPORTS_DIR, 'contrast_final_list.json'), 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    patents_list = data.get('final_patents', [])
    patent_map = {p.get('patent_id', ''): p for p in patents_list}
    
    for pid in EP_PATENTS:
        url = patent_map.get(pid, {}).get('url', '')
        if not url:
            print(f"⚠️  {pid}: no URL found", flush=True)
            continue
        
        print(f"\nExtracting EP claims for {pid}...", flush=True)
        
        try:
            result = subprocess.run(
                [sys.executable, EXTRACT_SCRIPT, url, pid],
                capture_output=True, text=True, timeout=90
            )
            if result.returncode != 0:
                print(f"  ❌ {pid} failed: {result.stderr[:300]}", flush=True)
                continue
            
            # 找 JSON 輸出
            lines = result.stdout.strip().split('\n')
            new_data = None
            for line in reversed(lines):
                line = line.strip()
                if line.startswith('{') and line.endswith('}'):
                    try:
                        new_data = json.loads(line)
                        break
                    except json.JSONDecodeError:
                        continue
            
            if not new_data:
                print(f"  ❌ {pid}: no JSON in output", flush=True)
                continue
            
            c1_len = len(new_data.get('claim_1', ''))
            c2_len = len(new_data.get('claim_2', ''))
            print(f"  {pid}: c1={c1_len} c2={c2_len}", flush=True)
            
            # 合併到現有 sections
            section_path = os.path.join(REPORTS_DIR, f'sections_{pid}.json')
            if os.path.exists(section_path):
                with open(section_path, 'r', encoding='utf-8') as f:
                    existing = json.load(f)
            else:
                existing = {}
            
            updated = []
            for key in ['claim_1', 'claim_2', 'claim_3']:
                new_val = new_data.get(key, '')
                if isinstance(new_val, str) and len(new_val) > len(existing.get(key, '')):
                    existing[key] = new_val
                    updated.append("{}={}".format(key, len(new_val)))
            
            with open(section_path, 'w', encoding='utf-8') as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)
            print(f"  ✅ Updated: {', '.join(updated) if updated else 'no improvements'}", flush=True)
            
        except subprocess.TimeoutExpired:
            print(f"  ⏰ {pid}: timeout", flush=True)
        except Exception as e:
            print(f"  ❌ {pid}: {e}", flush=True)
        
        time.sleep(1)
    
    print("\n" + "=" * 60)
    print("EP claims extraction complete")


if __name__ == '__main__':
    main()
