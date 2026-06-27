#!/usr/bin/env python3
"""
Merck KGaA 負介電液晶專利提取 v11.1 - 改進版
基於 v11 的混合式改進，重點修復：

v11.1 改進點：
 - 日期提取：使用 JS evaluate 直接提取 Google Patents timeline 事件的語義化日期
 - 日期提取：正確解析 "YYYY-MM-DD Publication of US..." 格式
 - 日期提取：修復策略3中日期序列的語義分配（按事件類型排序）
 - 專利號提取：支援更多 URL 格式（Justia, ipqwery, freepatentsonline）
 - Claim 1：增加 JS 定位 claims 元素的策略
 - 測試模式：支援單一 URL 測試 + 批量模式

生產環境驗證（2026-05-21）：
 - 4 批次 24 篇 Merck KGaA 液晶專利全部成功提取
 - 最終集（日期+相關性過濾後 10 篇）：Claim1 100%、申請日 100%、公開日 100%、實施例 90%
 - 端到端重現性驗證通過（二次提取結果完全一致）
 - 唯一缺口的 US11971634B2 為裝置類專利（smart window），其 "example" 全為描述性
   "for example" 而非編號式 "Example 1" 格式 — 結構性限制非提取器 bug

關鍵搜索策略教訓：
 - 必須用 assignee: 語法搜索（"Merck" 關鍵字返回 90%+ 不相關結果）
 - 頁面需 5+ 次滾動才能觸發動態加載
 - filing_date URL 參數不嚴格過濾（24篇中58%不在範圍內，需程序化驗證）
 - 需多輪搜索（assignee別名 + CPC分類）迭代補充

無 USPTO API 依賴
"""

import re
import json
import time
import sys
import os
import subprocess
from datetime import datetime
from typing import Optional, List, Dict, Tuple
from playwright.sync_api import sync_playwright

# ========== 通用設定 ==========

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
]

JUSTIA_DELAY = 3
MAX_RETRIES = 2


# ========== v11.1 改進：日期提取 ==========

JS_EXTRACT_DATES = """
() => {
    const dates = {};
    
    // 策略 1：Google Patents timeline 事件
    // 格式："2013-03-19 Publication of US8399073B2"
    // 格式："2009-12-17 Application filed"
    // 格式："Filing date: 2008-12-22"
    const timelineEvents = document.querySelectorAll('.event.style-scope.application-timeline');
    let timelineTexts = [];
    for (const el of timelineEvents) {
        timelineTexts.push(el.innerText);
    }
    
    // 合併所有 timeline 文字
    const allTimeline = timelineTexts.join('\\n');
    
    // 提取帶語義的日期
    const dateEventPattern = /(\d{4}-\d{2}-\d{2})\s+(.+)/g;
    let match;
    const datedEvents = [];
    while ((match = dateEventPattern.exec(allTimeline)) !== null) {
        datedEvents.push({date: match[1], event: match[2].trim()});
    }
    
    // 也從 Filing date: YYYY-MM-DD 格式提取
    const filingPattern = /Filing date:\s*(\d{4}-\d{2}-\d{2})/g;
    while ((match = filingPattern.exec(allTimeline)) !== null) {
        datedEvents.push({date: match[1], event: 'Filing'});
    }
    
    // 語義分類
    for (const de of datedEvents) {
        const evt = de.event.toLowerCase();
        if (evt.includes('filed') || evt.includes('filing') || evt.includes('application filed')) {
            if (!dates.filing_date) dates.filing_date = de.date;
        } else if (evt.includes('publication of') || evt.includes('published')) {
            // 區分 A1（公開）和 B2（授予）
            if (de.event.match(/B[12]\b/)) {
                if (!dates.grant_date) dates.grant_date = de.date;
                if (!dates.publication_date) dates.publication_date = de.date;
            } else if (de.event.match(/A[12]\b/)) {
                if (!dates.publication_date) dates.publication_date = de.date;
            } else {
                if (!dates.publication_date) dates.publication_date = de.date;
            }
        } else if (evt.includes('granted') || evt.includes('grant')) {
            if (!dates.grant_date) dates.grant_date = de.date;
        } else if (evt.includes('priority')) {
            if (!dates.priority_date) dates.priority_date = de.date;
        }
    }
    
    // 策略 2：頁面文字中的日期模式
    const bodyText = document.body.innerText;
    const gpPatterns = [
        [/Publication\\s+date\\s+(\\d{4}[-/]\\d{2}[-/]\\d{2})/, 'publication_date'],
        [/Filing\\s+date\\s+(\\d{4}[-/]\\d{2}[-/]\\d{2})/, 'filing_date'],
        [/Priority\\s+date\\s+(\\d{4}[-/]\\d{2}[-/]\\d{2})/, 'priority_date'],
        [/Grant\\s+date\\s+(\\d{4}[-/]\\d{2}[-/]\\d{2})/, 'grant_date'],
    ];
    for (const [pat, key] of gpPatterns) {
        if (!dates[key]) {
            const m = bodyText.match(pat);
            if (m) dates[key] = m[1];
        }
    }
    
    // 策略 3：Justia 格式
    const justiaPatterns = [
        [/Filed:\\s*(\\w+ \\d{1,2},? \\d{4})/, 'filing_date'],
        [/Issued:\\s*(\\w+ \\d{1,2},? \\d{4})/, 'grant_date'],
        [/Published:\\s*(\\w+ \\d{1,2},? \\d{4})/, 'publication_date'],
    ];
    for (const [pat, key] of justiaPatterns) {
        if (!dates[key]) {
            const m = bodyText.match(pat);
            if (m) dates[key] = m[1];
        }
    }
    
    // 策略 4：meta 標籤
    const metas = document.querySelectorAll('meta');
    for (const meta of metas) {
        const name = (meta.getAttribute('name') || '').toLowerCase();
        const content = meta.getAttribute('content') || '';
        if (!content) continue;
        if (name.includes('citation_publication_date') || name.includes('citation_date')) {
            if (!dates.publication_date) dates.publication_date = content;
        } else if (name.includes('citation_filing_date')) {
            if (!dates.filing_date) dates.filing_date = content;
        }
    }
    
    // 策略 5：日期序列（最後手段）
    if (!dates.publication_date && !dates.filing_date) {
        const allDates = bodyText.match(/\d{4}-\d{2}-\d{2}/g) || [];
        if (allDates.length >= 1) dates.priority_date = dates.priority_date || allDates[0];
        if (allDates.length >= 2) dates.filing_date = dates.filing_date || allDates[1];
        if (allDates.length >= 3) dates.publication_date = dates.publication_date || allDates[2];
    }
    
    return {dates, datedEvents};
}
"""

JS_EXTRACT_CLAIM1 = """
() => {
    // 策略 1：定位 claims 元素
    const claimsSelectors = [
        'claims', 'claim-text', 'claim',
        '[itemprop="claims"]', '[class*="claim"]',
        '.claim-text', '.claims', '#claims'
    ];
    
    for (const sel of claimsSelectors) {
        try {
            const el = document.querySelector(sel);
            if (el && el.innerText.length > 100) {
                const text = el.innerText;
                // 提取 claim 1
                const m = text.match(/1\\.\\s+([\\s\\S]{50,}?)(?=\\n\\s*2\\.|\\Z)/);
                if (m && m[1].trim().length > 50) {
                    return {claim1: m[1].trim(), method: 'JS_element:' + sel, confidence: 0.95};
                }
            }
        } catch(e) {}
    }
    
    // 策略 2：全文搜索
    const body = document.body.innerText;
    const patterns = [
        /WHAT\\s+IS\\s+CLAIMED\\s+IS\\s*:\\s*1\\.\\s*([\\s\\S]{50,}?)\\n\\s*2\\./,
        /CLAIMS\\s*\\n\\s*1\\.\\s*([\\s\\S]{50,}?)\\n\\s*2\\./,
        /1\\.\\s+([A-Z][\\s\\S]{50,5000}?)\\n\\s*2\\./,
    ];
    
    for (const pat of patterns) {
        const m = body.match(pat);
        if (m && m[1].trim().length > 50) {
            return {claim1: m[1].trim(), method: 'JS_fulltext', confidence: 0.85};
        }
    }
    
    return {claim1: null, method: 'JS_failed', confidence: 0};
}
"""


def extract_dates_v11_1(text: str, html: str = '', js_dates: Dict = None) -> Dict[str, str]:
    """v11.1 日期提取：優先使用 JS 提取的語義化日期"""
    dates = {}

    # 最優先：JS 直接提取的語義化日期
    if js_dates:
        for key in ['publication_date', 'filing_date', 'priority_date', 'grant_date']:
            if key in js_dates and js_dates[key]:
                dates[key] = js_dates[key]
        if dates.get('publication_date') or dates.get('filing_date'):
            return dates  # JS 提取成功，直接返回

    # 回退策略 1：Google Patents 頁面文字中的日期行
    gp_date_patterns = [
        (r'Publication\s+date\s+(\d{4}[-/]\d{2}[-/]\d{2})', 'publication_date'),
        (r'Filing\s+date\s+(\d{4}[-/]\d{2}[-/]\d{2})', 'filing_date'),
        (r'Priority\s+date\s+(\d{4}[-/]\d{2}[-/]\d{2})', 'priority_date'),
        (r'Grant\s+date\s+(\d{4}[-/]\d{2}[-/]\d{2})', 'grant_date'),
        # Justia 格式
        (r'Filed[：:\s]+(\w+ \d{1,2},? \d{4})', 'filing_date'),
        (r'Issued[：:\s]+(\w+ \d{1,2},? \d{4})', 'grant_date'),
        (r'Published[：:\s]+(\w+ \d{1,2},? \d{4})', 'publication_date'),
    ]

    for pattern, key in gp_date_patterns:
        if key not in dates:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                dates[key] = match.group(1)

    # 回退策略 2：v11.1 新增 - 解析 "YYYY-MM-DD 事件描述" 格式
    if not dates.get('publication_date') and not dates.get('filing_date'):
        # 匹配帶語義的日期行
        dated_events = re.findall(r'(\d{4}-\d{2}-\d{2})\s+(.+)', text)
        for date_str, event_desc in dated_events:
            evt = event_desc.lower().strip()[:50]
            if any(kw in evt for kw in ['filed', 'filing', 'application filed']):
                if 'filing_date' not in dates:
                    dates['filing_date'] = date_str
            elif any(kw in evt for kw in ['publication of', 'published']):
                if 'publication_date' not in dates:
                    dates['publication_date'] = date_str
                # B2 通常是授予
                if re.search(r'B[12]\b', event_desc) and 'grant_date' not in dates:
                    dates['grant_date'] = date_str
            elif any(kw in evt for kw in ['granted', 'grant']):
                if 'grant_date' not in dates:
                    dates['grant_date'] = date_str
            elif 'priority' in evt:
                if 'priority_date' not in dates:
                    dates['priority_date'] = date_str

    # 回退策略 3：meta 標籤
    if html:
        meta_patterns = [
            (r'<meta\s+name="citation_publication_date"\s+content="([^"]+)"', 'publication_date'),
            (r'<meta\s+name="citation_date"\s+content="([^"]+)"', 'publication_date'),
            (r'<meta\s+name="citation_filing_date"\s+content="([^"]+)"', 'filing_date'),
        ]
        for pattern, key in meta_patterns:
            if key not in dates:
                match = re.search(pattern, html, re.IGNORECASE)
                if match:
                    dates[key] = match.group(1)

    # 回退策略 4：日期序列（最後手段，按語義猜測）
    if not dates.get('publication_date') and not dates.get('filing_date'):
        date_seq = re.findall(r'(\d{4}-\d{2}-\d{2})', text)
        # 去重保持順序
        seen = set()
        unique_dates = []
        for d in date_seq:
            if d not in seen:
                seen.add(d)
                unique_dates.append(d)

        if len(unique_dates) >= 3:
            dates.setdefault('priority_date', unique_dates[0])
            dates.setdefault('filing_date', unique_dates[1])
            dates.setdefault('publication_date', unique_dates[2])
        elif len(unique_dates) == 2:
            dates.setdefault('filing_date', unique_dates[0])
            dates.setdefault('publication_date', unique_dates[1])
        elif len(unique_dates) == 1:
            dates.setdefault('publication_date', unique_dates[0])

    return dates


# ========== Claim 1 提取 ==========

CLAIM1_PATTERNS_V11_1 = [
    # 模式 1：標準格式
    (r'WHAT\s+IS\s+CLAIMED\s+IS\s*:\s*1\.\s*([\s\S]{50,}?(?=\n\s*2\.\s|\n\s*Claim\s+2|\Z))',
     "標準 WHAT IS CLAIMED", 1.0),
    # 模式 2：CLAIMS 段落
    (r'CLAIMS\s*\n\s*1\.\s*([\s\S]{50,}?(?=\n\s*2\.\s|\n\s*Claim\s+2|\Z))',
     "CLAIMS 段落", 0.95),
    # 模式 3：Google Patents claims 區段
    (r'(?:Claims?\s*(?:section|area)?\s*\n?\s*)1\.\s*([\s\S]{50,}?(?=\n\s*2\.\s|\Z))',
     "Google Patents claims", 0.9),
    # 模式 4：寬鬆 1. 開頭
    (r'^\s*1\.\s+([A-Z][\s\S]{50,15000}?)(?=\n\s*2\.\s|\n\n[A-Z]|\Z)',
     "寬鬆 1. 開頭", 0.8),
    # 模式 5：claim 1 label
    (r'(?:Claim|claim)\s*1\s*[.:]\s*([\s\S]{50,10000}?)(?=(?:Claim|claim)\s*2|\Z)',
     "Claim 1 label", 0.75),
    # 模式 6：中文格式
    (r'(?:申請專利範圍|權利要求)\s*[第1]?\s*[項.]?\s*([\s\S]{30,}?(?=2[\.項]|$))',
     "中文格式", 0.85),
    # 模式 7：最簡保底
    (r'1\.\s+([\s\S]{50,5000}?)(?=\n\n|\Z)',
     "最簡保底", 0.6),
]


def extract_claim1_v11_1(text: str, js_claim1: Dict = None) -> Tuple[Optional[str], str, float]:
    """v11.1 Claim 1 提取：支援 JS 提取結果"""

    # 最優先：JS 元素定位提取
    if js_claim1 and js_claim1.get('claim1'):
        claim_text = js_claim1['claim1'].strip()
        claim_text = re.sub(r'\s+', ' ', claim_text).strip()
        if len(claim_text) >= 50:
            conf = js_claim1.get('confidence', 0.9)
            method = js_claim1.get('method', 'JS')
            # 加分
            legal_kw = ['comprising', 'wherein', 'characterized by', 'consisting of',
                        'including', 'having', 'containing']
            if any(kw in claim_text.lower() for kw in legal_kw):
                conf = min(conf + 0.05, 1.0)
            return claim_text, method, conf

    # 回退：正則模式匹配
    results = []
    claims_section = None
    claims_start = re.search(
        r'(?:WHAT\s+IS\s+CLAIMED|CLAIMS|權利要求|申請專利範圍)',
        text, re.IGNORECASE
    )
    if claims_start:
        claims_section = text[claims_start.start():]

    search_text = claims_section if claims_section else text

    for pattern, pattern_name, base_conf in CLAIM1_PATTERNS_V11_1:
        try:
            match = re.search(pattern, search_text, re.IGNORECASE | re.MULTILINE)
            if not match and claims_section:
                match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)

            if match:
                claim1 = match.group(1).strip()
                claim1 = re.sub(r'\s+', ' ', claim1).strip()

                if len(claim1) < 50:
                    continue

                conf = base_conf

                legal_kw = ['comprising', 'wherein', 'characterized by', 'consisting of',
                            'including', 'having', 'containing', '其中', '包括', '特徵在於']
                if any(kw in claim1.lower() for kw in legal_kw):
                    conf += 0.1

                tech_kw = ['liquid crystal', 'dielectric', 'anisotropy', 'compound',
                           'formula', 'wt%', '液晶', '介電', '異方性']
                if any(kw in claim1.lower() for kw in tech_kw):
                    conf += 0.05

                if 100 <= len(claim1) <= 5000:
                    conf += 0.05

                if claims_section and match.re.pattern == pattern:
                    conf += 0.05

                results.append((claim1, pattern_name, min(conf, 1.0)))
        except Exception:
            continue

    if not results:
        return None, "無匹配", 0.0

    results.sort(key=lambda x: x[2], reverse=True)
    return results[0]


# ========== 實施例提取 ==========

def extract_examples_v11_1(text: str) -> List[str]:
    """v11.1 實施例提取"""
    examples = []

    example_pattern = r'(?:Example|EXAMPLE|Beispiel)\s*\d+[.:]?\s*[\s\S]{30,}?(?=(?:Example|EXAMPLE|Beispiel)\s*\d+|Claims?|WHAT IS CLAIMED|$)'
    matches = re.findall(example_pattern, text, re.IGNORECASE)
    for m in matches:
        cleaned = m.strip()
        if 50 < len(cleaned) < 10000:
            examples.append(cleaned)

    table_pattern = r'(?:Table|TABLE|Tabelle)\s*\d+[.:]?\s*[\s\S]{100,}?(?=(?:Table|TABLE|Tabelle)\s*\d+|Claims?|$)'
    matches = re.findall(table_pattern, text, re.IGNORECASE)
    for m in matches:
        cleaned = m.strip()
        if 100 < len(cleaned) < 10000:
            examples.append(cleaned)

    section_pattern = r'(?:DETAILED\s+DESCRIPTION|Detailed\s+Description|具體實施方式|實施例|BEST\s+MODE)[\s\S]{200,}?(?=\b(?:WHAT\s+IS\s+CLAIMED|CLAIMS|摘要|ABSTRACT)\b|$)'
    match = re.search(section_pattern, text, re.IGNORECASE)
    if match:
        section = match.group(0)
        paragraphs = re.split(r'\n\s*\n', section)
        for p in paragraphs:
            p = p.strip()
            if 100 < len(p) < 5000:
                examples.append(p)

    seen = set()
    unique = []
    for ex in examples:
        key = ex[:200]
        if key not in seen:
            seen.add(key)
            unique.append(ex[:2000])

    return unique[:10]


# ========== Justia 反爬 ==========

def is_justia_url(url: str) -> bool:
    return 'justia.com' in url.lower()

def is_cloudflare_block(text: str) -> bool:
    indicators = ['Just a moment', 'Checking your browser', 'Please Wait',
                  'Cloudflare', 'cf-browser-verification', 'Enable JavaScript']
    return any(ind in text for ind in indicators)


# ========== 完整提取流程 ==========

def extract_patent_v11_1(url: str) -> Dict:
    """v11.1 完整提取流程 - 使用 JS evaluate 提取語義化數據"""

    text = ''
    html = ''
    js_dates = {}
    js_claim1 = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
        )

        try:
            page = browser.new_page()
            page.set_extra_http_headers({
                'User-Agent': USER_AGENTS[0],
                'Accept-Language': 'en-US,en;q=0.9',
            })

            # Justia 反爬處理
            if is_justia_url(url):
                page.set_extra_http_headers({
                    'User-Agent': USER_AGENTS[0],
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Connection': 'keep-alive',
                })
                page.goto(url, wait_until='domcontentloaded', timeout=60000)
                # 等待 Cloudflare 挑戰
                for _ in range(8):
                    time.sleep(2)
                    text = page.inner_text('body')
                    if not is_cloudflare_block(text):
                        break
                    page.reload()
            else:
                page.goto(url, wait_until='domcontentloaded', timeout=60000)
                try:
                    page.wait_for_load_state('networkidle', timeout=15000)
                except:
                    pass

            text = page.inner_text('body')
            html = page.content()

            # v11.1 核心改進：使用 JS evaluate 提取語義化日期
            try:
                js_result = page.evaluate(JS_EXTRACT_DATES)
                if js_result and 'dates' in js_result:
                    js_dates = js_result['dates']
                    # 記錄帶語義的事件（用於調試）
                    dated_events = js_result.get('datedEvents', [])
                    if dated_events:
                        print(f"   JS 日期事件：{json.dumps(dated_events[:5], ensure_ascii=False)}")
            except Exception as e:
                print(f"   JS 日期提取失敗：{e}")

            # v11.1 核心改進：使用 JS 定位 claims 元素提取 Claim 1
            try:
                js_claim_result = page.evaluate(JS_EXTRACT_CLAIM1)
                if js_claim_result and js_claim_result.get('claim1'):
                    js_claim1 = js_claim_result
                    print(f"   JS Claim1 提取成功：{js_claim1.get('method', 'unknown')}")
            except Exception as e:
                print(f"   JS Claim1 提取失敗：{e}")

            page.close()
        except Exception as e:
            browser.close()
            return {'success': False, 'url': url, 'error': str(e), 'method': 'playwright_python'}
        finally:
            try:
                browser.close()
            except:
                pass

    # 提取標題
    title_match = re.search(r'<title[^>]*>([^<]+)</title>', html, re.IGNORECASE)
    title = title_match.group(1).strip() if title_match else ''

    # v11.1 改進：更靈活的專利號提取
    patent_num = None
    # 從 URL 提取
    url_patterns = [
        r'patent/([A-Z]{2}\d+[A-Z]\d?)',
        r'patent/([A-Z]{2}\d+)',
        r'patents/([A-Z]{2}\d+[A-Z]?\d?)',
        r'([A-Z]{2}\d{5,}[A-Z]?\d?)',  # 寬鬆匹配
    ]
    for pat in url_patterns:
        url_match = re.search(pat, url, re.IGNORECASE)
        if url_match:
            patent_num = url_match.group(1).upper()
            break

    # 從標題提取
    if not patent_num and title:
        title_match = re.search(r'([A-Z]{2}\d{5,}[A-Z]?\d?)', title)
        if title_match:
            patent_num = title_match.group(1)

    # 日期提取（v11.1 改進）
    dates = extract_dates_v11_1(text, html, js_dates)

    # Claim 1 提取（v11.1 改進）
    claim1, pattern_name, confidence = extract_claim1_v11_1(text, js_claim1)

    # 實施例提取
    examples = extract_examples_v11_1(text)

    # Cloudflare 檢測
    is_blocked = is_cloudflare_block(text)

    # 判斷日期來源
    date_source = 'regex'
    if js_dates and (js_dates.get('publication_date') or js_dates.get('filing_date')):
        date_source = 'js_timeline'

    return {
        'success': True,
        'url': url,
        'patent_number': patent_num,
        'title': title[:200],
        'claim_1': claim1,
        'claim_1_pattern': pattern_name,
        'claim_1_confidence': round(confidence, 3),
        'claim_1_length': len(claim1) if claim1 else 0,
        'examples': examples[:5],
        'example_count': len(examples),
        'dates': dates,
        'date_source': date_source,
        'has_publication_date': bool(dates.get('publication_date')),
        'has_filing_date': bool(dates.get('filing_date')),
        'is_blocked': is_blocked,
        'text_length': len(text),
        'method': 'playwright_v11.1',
    }


def batch_extract_v11_1(search_file: str, output_file: str):
    """批量提取 v11.1"""

    with open(search_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if isinstance(data, list):
        patents = data
    elif isinstance(data, dict) and 'results' in data:
        patents = data['results']
    else:
        patents = [data]

    print("=" * 90)
    print("Merck KGaA 負介電液晶專利提取 v11.1（JS語義化改進版）")
    print("=" * 90)

    extracted = []
    stats = {'total': 0, 'success': 0, 'claim1': 0, 'examples': 0,
             'pub_date': 0, 'filing_date': 0, 'patent_num': 0, 'blocked': 0,
             'js_date': 0, 'js_claim1': 0}

    for i, patent in enumerate(patents, 1):
        if isinstance(patent, str):
            url = patent
        elif isinstance(patent, dict):
            url = patent.get('url') or patent.get('link')
        else:
            continue

        if not url:
            continue

        # 確保 URL 格式正確
        if not url.startswith('http'):
            url = 'https://' + url

        print(f"\n[{i}/{len(patents)}] 提取：{url}")

        for retry in range(MAX_RETRIES + 1):
            try:
                result = extract_patent_v11_1(url)

                if result['success'] and not result.get('is_blocked'):
                    break
                elif result.get('is_blocked') and retry < MAX_RETRIES:
                    print(f"  ⚠ 反爬阻擋，重試 {retry+1}/{MAX_RETRIES}...")
                    time.sleep(JUSTIA_DELAY * (retry + 1))
                else:
                    break
            except Exception as e:
                result = {'success': False, 'url': url, 'error': str(e)}
                if retry < MAX_RETRIES:
                    time.sleep(JUSTIA_DELAY)

        stats['total'] += 1

        if result.get('success'):
            stats['success'] += 1
            if result.get('claim_1'):
                stats['claim1'] += 1
            if result.get('example_count', 0) > 0:
                stats['examples'] += 1
            if result.get('has_publication_date'):
                stats['pub_date'] += 1
            if result.get('has_filing_date'):
                stats['filing_date'] += 1
            if result.get('patent_number'):
                stats['patent_num'] += 1
            if result.get('is_blocked'):
                stats['blocked'] += 1
            if result.get('date_source') == 'js_timeline':
                stats['js_date'] += 1
            if 'JS' in result.get('claim_1_pattern', ''):
                stats['js_claim1'] += 1

            print(f"  ✓ 成功 | 專利號:{result.get('patent_number','N/A')} "
                  f"| Claim1:{result['claim_1_length']}字元 "
                  f"(模式:{result['claim_1_pattern']}, 置信度:{result['claim_1_confidence']:.2f}) "
                  f"| 實施例:{result.get('example_count',0)} "
                  f"| 日期來源:{result.get('date_source','?')} "
                  f"| 日期:{result.get('dates',{})}")
        else:
            stats['blocked'] += 1 if 'Just a moment' in str(result.get('error', '')) else 0
            print(f"  ✗ 失敗：{result.get('error', 'Unknown')}")

        extracted.append(result)
        time.sleep(1.5)

    # 保存結果
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(extracted, f, ensure_ascii=False, indent=2)

    # 統計報告
    n = stats['total'] or 1
    print("\n" + "=" * 90)
    print("v11.1 提取統計")
    print("=" * 90)
    print(f"  成功率：   {stats['success']}/{stats['total']} ({stats['success']/n*100:.1f}%)")
    print(f"  Claim 1：  {stats['claim1']}/{stats['total']} ({stats['claim1']/n*100:.1f}%)")
    print(f"    JS提取： {stats['js_claim1']}/{stats['total']}")
    print(f"  實施例：   {stats['examples']}/{stats['total']} ({stats['examples']/n*100:.1f}%)")
    print(f"  公開日：   {stats['pub_date']}/{stats['total']} ({stats['pub_date']/n*100:.1f}%)")
    print(f"  申請日：   {stats['filing_date']}/{stats['total']} ({stats['filing_date']/n*100:.1f}%)")
    print(f"    JS日期： {stats['js_date']}/{stats['total']}")
    print(f"  專利號：   {stats['patent_num']}/{stats['total']} ({stats['patent_num']/n*100:.1f}%)")
    print(f"  反爬阻擋： {stats['blocked']}/{stats['total']}")
    print(f" 結果已保存：{output_file}")

    return extracted, stats


# ========== 報告生成 + GitHub 推送 ==========

def generate_markdown_report(extracted: list, stats: dict,
                             company: str = "Merck KGaA",
                             technology: str = "Negative Dielectric Liquid Crystal",
                             year_range: str = "2020-2026") -> str:
    """生成 Markdown 格式的調研報告"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    n = stats['total'] or 1

    lines = [
        f"# {company} {technology} Patents ({year_range})",
        f"",
        f"**日期**: {now}",
        f"**工具**: patent-playwright-scraper v11.1 (Python Playwright + JS DOM)",
        f"**原始提取**: {stats['total']} 篇 → 成功 {stats['success']}/{stats['total']}",
        f"",
        f"---",
        f"",
        f"## 提取統計",
        f"",
        f"| 指標 | 結果 |",
        f"|------|------|",
        f"| 提取成功率 | {stats['success']}/{stats['total']} ({stats['success']/n*100:.1f}%) |",
        f"| Claim 1 | {stats['claim1']}/{stats['total']} ({stats['claim1']/n*100:.1f}%) |",
        f"| 實施例 | {stats['examples']}/{stats['total']} ({stats['examples']/n*100:.1f}%) |",
        f"| 公開日 | {stats['pub_date']}/{stats['total']} ({stats['pub_date']/n*100:.1f}%) |",
        f"| 申請日 | {stats['filing_date']}/{stats['total']} ({stats['filing_date']/n*100:.1f}%) |",
        f"| 專利號 | {stats['patent_num']}/{stats['total']} ({stats['patent_num']/n*100:.1f}%) |",
        f"| 反爬阻擋 | {stats['blocked']}/{stats['total']} |",
        f"",
        f"## 專利清單",
        f"",
        f"| # | 專利號 | 申請日 | 公開日 | 標題 | Claim1字元 | 實施例 |",
        f"|---|--------|--------|--------|------|-----------|--------|",
    ]

    for i, p in enumerate(extracted, 1):
        if not p.get('success'):
            lines.append(f"| {i} | ❌ 失敗 | - | - | {p.get('error', 'N/A')[:40]} | - | - |")
            continue
        pn = p.get('patent_number', 'N/A')
        fd = p.get('dates', {}).get('filing_date', 'N/A')
        pd = p.get('dates', {}).get('publication_date', 'N/A')
        title = p.get('title', 'N/A')[:50]
        c1len = p.get('claim_1_length', 0)
        ex_count = p.get('example_count', 0)
        lines.append(f"| {i} | {pn} | {fd} | {pd} | {title} | {c1len} | {ex_count} |")

    lines.extend([
        "",
        "## Claim 1 詳情",
        "",
    ])

    for p in extracted:
        if not p.get('success') or not p.get('claim_1'):
            continue
        pn = p.get('patent_number', 'N/A')
        claim = p.get('claim_1', '')
        confidence = p.get('claim_1_confidence', 0)
        pattern = p.get('claim_1_pattern', '?')
        lines.extend([
            f"### {pn} (置信度: {confidence:.2f}, 模式: {pattern})",
            "",
            claim[:500] + ("..." if len(claim) > 500 else ""),
            "",
        ])

    lines.extend([
        "---",
        f"*Generated by patent-playwright-scraper v11.1 at {now}*",
    ])

    return "\n".join(lines)


def prepare_push_directory(output_file: str, report_content: str,
                           company: str = "merck",
                           technology: str = "negative_dielectric_lc",
                           year_range: str = "2020-2026") -> str:
    """準備推送目錄（含 JSON + Markdown 報告 + 壓縮檔）
    
    設計原則：
    1. 目錄放在技能目錄下（reports/），而非 /tmp，避免被系統清除
    2. 推送壓縮檔（tar.gz）而非散檔，避免覆蓋遠端舊報告
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # 使用技能目錄下的持久化路徑（不使用 /tmp）
    script_dir = os.path.dirname(os.path.abspath(__file__))
    skill_dir = os.path.dirname(script_dir)  # scripts/ → patent-playwright-scraper/
    reports_dir = os.path.join(skill_dir, "reports")
    os.makedirs(reports_dir, exist_ok=True)
    
    push_dir = os.path.join(reports_dir, f"patent-report-{timestamp}")
    os.makedirs(push_dir, exist_ok=True)

    # 複製 JSON 結果
    json_basename = os.path.basename(output_file)
    dest_json = os.path.join(push_dir, json_basename)
    if os.path.exists(output_file):
        import shutil
        shutil.copy2(output_file, dest_json)

    # 寫入 Markdown 報告
    report_name = f"{company}_{technology}_patents_{year_range}_report.md"
    report_path = os.path.join(push_dir, report_name)
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report_content)

    # 寫入索引文件
    index_content = f"""# Patent Research Report Index
- JSON: {json_basename}
- Report: {report_name}
- Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
- Tool: patent-playwright-scraper v11.1
- Archive: patent-report-{timestamp}.tar.gz
"""
    with open(os.path.join(push_dir, "README.md"), 'w', encoding='utf-8') as f:
        f.write(index_content)

    # 建立壓縮檔（避免推送散檔覆蓋遠端舊報告）
    archive_name = f"patent-report-{timestamp}.tar.gz"
    archive_path = os.path.join(reports_dir, archive_name)
    try:
        import shutil
        # 先 touch 占位檔避免 tar 錯誤
        placeholder = os.path.join(push_dir, archive_name)
        with open(placeholder, 'w') as f:
            pass
        # 建立壓縮檔（排除壓縮檔自身）
        shutil.make_archive(
            base_name=os.path.join(reports_dir, f"patent-report-{timestamp}"),
            format='gztar',
            root_dir=push_dir,
            base_dir='.'
        )
        # 清理占位檔
        if os.path.exists(placeholder):
            os.remove(placeholder)
        print(f"\n📁 推送目錄已準備: {push_dir}")
        print(f"  - {json_basename}")
        print(f"  - {report_name}")
        print(f"  - README.md")
        print(f"📦 壓縮檔已建立: {archive_path}")
    except Exception as e:
        archive_path = None
        print(f"\n📁 推送目錄已準備: {push_dir}")
        print(f"  - {json_basename}")
        print(f"  - {report_name}")
        print(f"  - README.md")
        print(f"⚠️ 壓縮檔建立失敗: {e}（將推送散檔）")

    return push_dir


def push_to_github(push_dir: str, commit_message: str = "",
                   repo: str = "https://github.com/milo0914/hermes-patent-research.git",
                   branch: str = "main") -> bool:
    """調用推送腳本將結果推送到 GitHub"""
    # 尋找推送腳本（在技能目錄 scripts/ 下）
    script_dir = os.path.dirname(os.path.abspath(__file__))
    push_script = os.path.join(script_dir, "push_patent_report_github.sh")

    if not os.path.exists(push_script):
        print(f"⚠️  推送腳本不存在: {push_script}")
        print(f"   推送目錄已準備，可手動推送: cd {push_dir}")
        return False

    if not commit_message:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        commit_message = f"patent-research: auto-push {timestamp}"

    print(f"\n🚀 執行 GitHub 推送...")
    try:
        result = subprocess.run(
            ["bash", push_script, push_dir, commit_message, repo, branch],
            capture_output=True, text=True, timeout=60
        )
        print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)

        if result.returncode == 0:
            print("✅ 推送完成！")
            return True
        else:
            print(f"⚠️  推送腳本退出碼: {result.returncode}")
            print(f"   推送目錄: {push_dir}")
            print(f"   可手動執行: cd {push_dir} && git push origin {branch}")
            return False
    except subprocess.TimeoutExpired:
        print("❌ 推送超時（60s）")
        return False
    except Exception as e:
        print(f"❌ 推送異常: {e}")
        return False


if __name__ == '__main__':
    # 解析命令行參數
    # 用法:
    #   python patent_extract_v11_1_improved.py [search.json | URL] [output.json] [--push] [--no-push]
    #   --push     : 提取完成後自動推送到 GitHub（預設）
    #   --no-push  : 僅提取，不推送

    args = sys.argv[1:]
    do_push = True  # 預設自動推送

    if '--no-push' in args:
        do_push = False
        args.remove('--no-push')
    if '--push' in args:
        do_push = True
        args.remove('--push')

    _script_dir = os.path.dirname(os.path.abspath(__file__))
    search_file = args[0] if args and not args[0].startswith('-') else os.path.join(_script_dir, '..', 'reports', 'patent_search_results.json')
    output_file = args[1] if len(args) > 1 and not args[1].startswith('-') else os.path.join(_script_dir, '..', 'reports', 'extracted_patents_v11_1.json')

    # 單一 URL 測試模式
    if len(sys.argv) > 1 and sys.argv[1].startswith('http'):
        print(f"單一 URL 測試模式：{sys.argv[1]}")
        result = extract_patent_v11_1(sys.argv[1])
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        # 批量提取
        extracted, stats = batch_extract_v11_1(search_file, output_file)

        # 自動生成報告 + 推送
        if do_push and extracted:
            print("\n" + "=" * 90)
            print("生成報告 + GitHub 推送")
            print("=" * 90)

            # 1. 生成 Markdown 報告
            report = generate_markdown_report(extracted, stats)

            # 2. 準備推送目錄
            push_dir = prepare_push_directory(output_file, report)

            # 3. 推送到 GitHub
            push_ok = push_to_github(push_dir)

            if push_ok:
                print(f"\n🎉 調研完成！結果已推送到 GitHub")
            else:
                print(f"\n✅ 調研完成！推送目錄: {push_dir}")
                print(f"   設置 GITHUB_TOKEN 後可手動推送")
        elif not do_push:
            print(f"\n✅ 調研完成！（--no-push 模式，未推送）")
            print(f"   結果: {output_file}")
