#!/usr/bin/env python3
"""
端到端重現性驗證腳本 — 對同一組專利跑兩次提取，比對結果一致性

使用方式：
  python e2e_reproducibility_test.py <patent_urls.json> [--output-dir /tmp]

patent_urls.json 格式：
  [{"url": "https://patents.google.com/patent/USXXXXXXX/en"}, ...]

驗證邏輯：
  1. 用 v11.1 腳本提取第一遍 → run1.json
  2. 用 v11.1 腳本提取第二遍 → run2.json
  3. 逐專利比對：patent_number, claim_1, dates, examples
  4. 輸出一致性報告

生產驗證（2026-05-21）：Merck KGaA 10 篇液晶專利 10/10 一致
"""

import json
import sys
import os
import argparse
import subprocess
import tempfile
import re


def run_extraction(url_file, output_file, script_path=None):
    """執行一次 v11.1 提取"""
    if script_path is None:
        skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        script_path = os.path.join(skill_dir, 'scripts', 'patent_extract_v11_1_improved.py')

    cmd = [sys.executable, script_path, url_file, output_file]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        print(f"提取失敗: {result.stderr[:500]}")
        return None

    with open(output_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def normalize_claim1(text):
    """正規化 Claim1 以便比對（去除空白差異）"""
    if not text:
        return ''
    return re.sub(r'\s+', ' ', text.strip())


def compare_patents(run1, run2):
    """比對兩次提取結果"""
    by_pn1 = {p.get('patent_number', ''): p for p in run1 if p.get('patent_number')}
    by_pn2 = {p.get('patent_number', ''): p for p in run2 if p.get('patent_number')}

    all_pns = sorted(set(by_pn1.keys()) | set(by_pn2.keys()))
    results = []

    for pn in all_pns:
        p1 = by_pn1.get(pn, {})
        p2 = by_pn2.get(pn, {})

        # Claim 1 比對
        c1_1 = normalize_claim1(p1.get('claim_1', ''))
        c1_2 = normalize_claim1(p2.get('claim_1', ''))
        claim1_match = c1_1 == c1_2 and len(c1_1) > 0

        # 日期比對
        d1 = p1.get('dates', {})
        d2 = p2.get('dates', {})
        filing_match = d1.get('filing_date', '') == d2.get('filing_date', '') and bool(d1.get('filing_date'))
        pub_match = d1.get('publication_date', '') == d2.get('publication_date', '') and bool(d1.get('publication_date'))

        # 實施例數量比對
        ex1 = max(p1.get('example_count', 0), len(p1.get('examples', [])))
        ex2 = max(p2.get('example_count', 0), len(p2.get('examples', [])))
        examples_match = ex1 == ex2

        all_match = claim1_match and filing_match and pub_match and examples_match

        results.append({
            'patent_number': pn,
            'claim1_match': claim1_match,
            'filing_date_match': filing_match,
            'publication_date_match': pub_match,
            'examples_match': examples_match,
            'all_match': all_match,
            'run1_claim1_len': len(c1_1),
            'run2_claim1_len': len(c1_2),
            'run1_examples': ex1,
            'run2_examples': ex2,
        })

    return results


def main():
    parser = argparse.ArgumentParser(description='E2E reproducibility test for patent extraction')
    parser.add_argument('url_file', help='JSON file with patent URLs')
    parser.add_argument('--output-dir', default='/tmp', help='Directory for run outputs')
    parser.add_argument('--script', default=None, help='Path to v11.1 extraction script')
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    run1_file = os.path.join(args.output_dir, 'e2e_run1.json')
    run2_file = os.path.join(args.output_dir, 'e2e_run2.json')

    print("=" * 60)
    print("端到端重現性驗證")
    print("=" * 60)

    # Run 1
    print("\n[1/3] 第一次提取...")
    data1 = run_extraction(args.url_file, run1_file, args.script)
    if data1 is None:
        print("第一次提取失敗，中止")
        return 1

    # Run 2
    print("\n[2/3] 第二次提取...")
    data2 = run_extraction(args.url_file, run2_file, args.script)
    if data2 is None:
        print("第二次提取失敗，中止")
        return 1

    # Compare
    print("\n[3/3] 比對結果...")
    patents1 = data1 if isinstance(data1, list) else data1.get('results', [])
    patents2 = data2 if isinstance(data2, list) else data2.get('results', [])

    comparison = compare_patents(patents1, patents2)

    print("\n" + "=" * 60)
    print("重現性驗證結果")
    print("=" * 60)

    all_match_count = 0
    for r in comparison:
        pn = r['patent_number']
        status = "✅ 一致" if r['all_match'] else "❌ 不一致"
        if r['all_match']:
            all_match_count += 1
        details = []
        if not r['claim1_match']:
            details.append(f"Claim1 ({r['run1_claim1_len']} vs {r['run2_claim1_len']})")
        if not r['filing_date_match']:
            details.append("申請日")
        if not r['publication_date_match']:
            details.append("公開日")
        if not r['examples_match']:
            details.append(f"實施例({r['run1_examples']} vs {r['run2_examples']})")

        detail_str = f" — 差異: {', '.join(details)}" if details else ""
        print(f"  {pn}: {status}{detail_str}")

    total = len(comparison)
    pct = all_match_count / total * 100 if total else 0
    print(f"\n一致性: {all_match_count}/{total} = {pct:.0f}%")

    if pct == 100:
        print("✅ 端到端重現性驗證通過")
        return 0
    else:
        print("⚠️ 存在不一致，請檢查上述差異")
        return 1


if __name__ == '__main__':
    sys.exit(main())
