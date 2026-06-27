#!/usr/bin/env python3
"""
專利提取結果驗證腳本 — 檢查 Claim1、日期範圍、實施例完整性
使用方式：python validate_extraction_results.py <extracted.json> [--start-year 2020] [--end-year 2026]

驗證項目：
1. 日期範圍（預設 2020-2026）
2. Claim 1 完整性（非空且長度 >=50 字元）
3. 實施例完整性（example_count > 0 或 examples 非空）
4. 專利號有效性
5. 輸出結構一致性（{"results": [...]} 或直接列表）
"""

import json
import re
import sys
import argparse


def load_results(filepath):
    """載入提取結果，自動處理包裹格式"""
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if isinstance(data, dict) and 'results' in data:
        return data['results'], 'wrapped'
    elif isinstance(data, list):
        return data, 'flat'
    else:
        print(f"❌ 無法解析的 JSON 結構: {type(data)}")
        sys.exit(1)


def validate_date_range(patents, start_year, end_year):
    """驗證日期範圍"""
    ok = 0
    fail = 0
    missing = 0
    details = []

    for p in patents:
        dates = p.get('dates', {})
        filing = dates.get('filing_date', '')
        pub = dates.get('publication_date', '')

        pn = p.get('patent_number', '?')

        fm = re.search(r'(\d{4})', str(filing))
        filing_year = int(fm.group(1)) if fm else None

        if filing_year and start_year <= filing_year <= end_year:
            status = f"申請日 {filing} OK"
            ok += 1
        elif filing_year:
            status = f"申請日 {filing} FAIL (year {filing_year} out of range)"
            fail += 1
        else:
            status = f"申請日 MISSING"
            missing += 1

        pm = re.search(r'(\d{4})', str(pub))
        if pm and start_year <= int(pm.group(1)) <= end_year:
            status += f" | 公開日 {pub} OK"
        elif pm:
            status += f" | 公開日 {pub} WARN (year {pm.group(1)})"

        details.append(f"  {pn}: {status}")

    return ok, fail, missing, details


def validate_claim1(patents):
    """驗證 Claim 1 完整性"""
    ok = 0
    short = 0
    missing = 0
    details = []

    for p in patents:
        c1 = p.get('claim_1', '') or p.get('claim1', '')
        pn = p.get('patent_number', '?')

        if not c1:
            details.append(f"  {pn}: MISSING")
            missing += 1
        elif len(c1) < 50:
            details.append(f"  {pn}: SHORT ({len(c1)} chars)")
            short += 1
        else:
            details.append(f"  {pn}: OK ({len(c1)} chars)")
            ok += 1

    return ok, short, missing, details


def validate_examples(patents):
    """驗證實施例完整性"""
    ok = 0
    missing = 0
    details = []

    for p in patents:
        ex_count = p.get('example_count', 0)
        examples = p.get('examples', [])
        pn = p.get('patent_number', '?')
        title = p.get('title', '')

        actual = max(ex_count, len(examples))
        if actual > 0:
            details.append(f"  {pn}: OK ({actual} examples)")
            ok += 1
        else:
            details.append(f"  {pn}: MISSING ({title[:60]})")
            missing += 1

    return ok, missing, details


def validate_patent_numbers(patents):
    """驗證專利號有效性"""
    ok = 0
    missing = 0
    details = []

    for p in patents:
        pn = p.get('patent_number', '')
        if pn and re.match(r'[A-Z]{2}\d{5,}', pn):
            ok += 1
        else:
            missing += 1
            details.append(f"  INVALID: '{pn}'")

    return ok, missing, details


def main():
    parser = argparse.ArgumentParser(description='Validate patent extraction results')
    parser.add_argument('json_file', help='Path to extracted JSON file')
    parser.add_argument('--start-year', type=int, default=2020, help='Start year for date range')
    parser.add_argument('--end-year', type=int, default=2026, help='End year for date range')
    parser.add_argument('--claim1-threshold', type=int, default=50, help='Min Claim1 length (chars)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Show per-patent details')
    args = parser.parse_args()

    patents, fmt = load_results(args.json_file)
    total = len(patents)

    print("=" * 60)
    print(f"Patent Extraction Validation: {args.json_file}")
    print(f"Total patents: {total} (format: {fmt})")
    print(f"Date range: {args.start_year}-{args.end_year}")
    print("=" * 60)

    # 1. Date range
    date_ok, date_fail, date_missing, date_details = validate_date_range(
        patents, args.start_year, args.end_year)
    date_pct = date_ok / total * 100 if total else 0
    print(f"\n[1] Date Range ({args.start_year}-{args.end_year})")
    print(f"    OK: {date_ok}/{total} = {date_pct:.0f}%")
    print(f"    Out of range: {date_fail}, Missing: {date_missing}")
    if args.verbose:
        for d in date_details:
            print(d)

    # 2. Claim 1
    c1_ok, c1_short, c1_missing, c1_details = validate_claim1(patents)
    c1_pct = c1_ok / total * 100 if total else 0
    print(f"\n[2] Claim 1 Completeness")
    print(f"    OK: {c1_ok}/{total} = {c1_pct:.0f}%")
    print(f"    Too short (<{args.claim1_threshold}): {c1_short}, Missing: {c1_missing}")
    if args.verbose:
        for d in c1_details:
            print(d)

    # 3. Examples
    ex_ok, ex_missing, ex_details = validate_examples(patents)
    ex_pct = ex_ok / total * 100 if total else 0
    print(f"\n[3] Examples Completeness")
    print(f"    OK: {ex_ok}/{total} = {ex_pct:.0f}%")
    print(f"    Missing: {ex_missing}")
    if args.verbose:
        for d in ex_details:
            print(d)

    # 4. Patent numbers
    pn_ok, pn_missing, pn_details = validate_patent_numbers(patents)
    pn_pct = pn_ok / total * 100 if total else 0
    print(f"\n[4] Patent Number Validity")
    print(f"    OK: {pn_ok}/{total} = {pn_pct:.0f}%")
    print(f"    Invalid/Missing: {pn_missing}")
    if args.verbose and pn_details:
        for d in pn_details:
            print(d)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    all_pass = True
    targets = [
        ("Date Range", date_pct, 80),
        ("Claim 1", c1_pct, 80),
        ("Examples", ex_pct, 50),
        ("Patent Numbers", pn_pct, 95),
    ]
    for name, pct, target in targets:
        status = "PASS" if pct >= target else "FAIL"
        if status == "FAIL":
            all_pass = False
        print(f"  {name}: {pct:.0f}% (target >= {target}%) [{status}]")

    print()
    if all_pass:
        print("ALL CHECKS PASSED")
    else:
        print("SOME CHECKS FAILED — see details above")

    return 0 if all_pass else 1


if __name__ == '__main__':
    sys.exit(main())
