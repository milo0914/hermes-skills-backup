#!/usr/bin/env python3
"""
報告結構驗證腳本 — 寬鬆匹配版
驗證進步性評判報告的完整性，避免格式微小差異導致假陽性失敗

使用方式:
  python verify_report_structure.py <report.md> [--patent-count 18]

驗證項目:
  1. 報告行數（應 > 基準值）
  2. 每篇專利 ID 存在
  3. 七欄位進步性評判各出現 N 次
  4. 星級評級數量與分佈
  5. 原有主要區段保留
  6. 評判區塊順序正確（技術要點 < 進步性評判 < ---分隔）
"""

import re
import sys
import argparse

def verify_report(filepath, expected_patents=18):
    with open(filepath, 'r', encoding='utf-8') as f:
        md = f.read()
    
    lines = md.split('\n')
    total_lines = len(lines)
    
    results = []
    
    # 1. 行數檢查
    min_lines = expected_patents * 60  # 每篇至少 60 行
    results.append(('報告總行數 > {}'.format(min_lines), total_lines > min_lines))
    
    # 2. 專利 ID 存在（寬鬆匹配：只要 ID 出現在文本中即可）
    patent_ids = [
        'EP4400561A1', 'EP4553132A1', 'EP4680691A1', 'EP4685208A1',
        'US12163081B2', 'US12305103B2', 'US12404452B2', 'US12612551B2',
        'US20240360362A1', 'US20250085595A1', 'US20250101305A1',
        'US20250136868A1', 'US20250189829A1', 'US20250197723A1',
        'US20250207032A1', 'US20250215323A1', 'US20250284151A1',
        'US20250361444A1',
    ]
    for pid in patent_ids:
        results.append(('專利 {} 存在'.format(pid), pid in md))
    
    # 3. 七欄位計數（寬鬆匹配：只計數欄位名稱出現次數）
    fields = ['技術問題', '先前技術阻礙', '非常規方案', '實施例驗證', '協同效應', '進步性強度', '核心洞見']
    for field in fields:
        count = md.count(field)
        results.append(('「{}」出現次數={}'.format(field, expected_patents), count == expected_patents))
    
    # 4. 星級評級（逐行 search，避免 findall 拆解問題，見陷阱 34）
    star_ratings = {}
    for line in lines:
        m = re.search(r'進步性強度[^⭐]*(⭐+)', line)
        if m:
            star_str = m.group(1)
            star_count = len(star_str)
            star_ratings[star_count] = star_ratings.get(star_count, 0) + 1
    
    total_stars = sum(star_ratings.values())
    results.append(('進步性強度評級數量={}'.format(expected_patents), total_stars == expected_patents))
    
    # 5. 原有區段保留
    sections = ['一、專利總覽', '二、各專利詳細分析', '三、跨專利技術趨勢分析', '四、參數數據總表', '五、調研方法論', '六、免責聲明']
    for section in sections:
        results.append(('原有區段「{}」保留'.format(section), section in md))
    
    # 6. 評判區塊數量（無重複）
    assessment_count = len(re.findall(r'### 進步性評判', md))
    results.append(('進步性評判區塊數量={}（無重複）'.format(expected_patents), assessment_count == expected_patents))
    
    # 7. 每篇專利的結構順序（技術要點 < 進步性評判 < ---）
    for pid in patent_ids:
        pid_pos = md.find(pid)
        tech_pos = md.find('技術要點', pid_pos) if pid_pos >= 0 else -1
        assess_pos = md.find('進步性評判', tech_pos) if tech_pos >= 0 else -1
        sep_pos = md.find('---', assess_pos) if assess_pos >= 0 else -1
        correct = pid_pos >= 0 and tech_pos > pid_pos and assess_pos > tech_pos and sep_pos > assess_pos
        results.append(('{}: 技術要點<進步性評判<---'.format(pid), correct))
    
    # 統計
    passed = sum(1 for _, ok in results if ok)
    failed = sum(1 for _, ok in results if not ok)
    
    print('=' * 60)
    print('驗證結果')
    print('=' * 60)
    for desc, ok in results:
        mark = '✓' if ok else '✗'
        print(' {} {}: {}'.format(mark, desc, ok))
    
    print()
    print('通過: {}/{}, 失敗: {}/{}'.format(passed, len(results), failed, len(results)))
    
    if star_ratings:
        print()
        print('進步性強度分佈:')
        for star_count in sorted(star_ratings.keys()):
            print('  {}⭐: {} 篇'.format(star_count, star_ratings[star_count]))
    
    return failed == 0

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='驗證專利報告結構完整性')
    parser.add_argument('report', help='報告 Markdown 檔案路徑')
    parser.add_argument('--patent-count', type=int, default=18, help='預期專利數量（預設 18）')
    args = parser.parse_args()
    
    ok = verify_report(args.report, args.patent_count)
    sys.exit(0 if ok else 1)
