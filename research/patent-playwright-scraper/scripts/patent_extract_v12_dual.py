#!/usr/bin/env python3
"""
Merck KGaA 負介電液晶專利提取 v12 — 雙引擎互補版

架構設計：
 ┌─────────────┐     ┌─────────────┐
 │ Python 引擎  │     │  CLI 引擎   │
 │ (Playwright) │     │(playwright- │
 │              │     │   cli)      │
 │ 強項：       │     │ 強項：      │
 │ • 批量速度快  │     │ • JS eval   │
 │ • CF 繞過    │     │   更穩定    │
 │ • UA 設定    │     │ • 調試友好  │
 └──────┬───────┘     └──────┬──────┘
        │                    │
        └───────┬────────────┘
                ▼
        ┌───────────────┐
        │  結果合併器    │
        │  字段級擇優    │
        │  • 日期：取更  │
        │    完整的      │
        │  • Claim1：取  │
        │    置信度更高  │
        │  • 實施例：合  │
        │    併去重      │
        │  • 專利號：取  │
        │    非空值      │
        └───────────────┘

三種模式：
 1. dual（預設）: Python + CLI 都跑，字段級擇優合併
 2. smart: 根據 URL 智能路由到單一引擎（最快）
 3. verify: Python 先跑，缺字段再用 CLI 補（省時）

使用方式：
 # 雙引擎互補（最完整）
 python patent_extract_v12_dual.py search.json output.json

 # 智能路由（最快）
 python patent_extract_v12_dual.py search.json output.json --mode smart

 # 驗證補全（省時）
 python patent_extract_v12_dual.py search.json output.json --mode verify

 # 單一 URL 測試
 python patent_extract_v12_dual.py "https://patents.google.com/patent/US8399073B2/en"

基於 v11.1 測試結果：
 - Python: Claim1 88.9%, 申請日 100%, 公開日 66.7%
 - CLI: Claim1 88.9%, 申請日 88.9%, 公開日 55.6%
 - v12 雙引擎目標: Claim1 >90%, 申請日 100%, 公開日 >75%

v12.1 生產驗證更新（2026-05-21）：
 - v11.1 生產環境 24/24 專利全部成功提取（Claim1 100%、日期 100%）
 - 搜索策略教訓：必須用 assignee: 語法，滾動 5+ 次觸發加載
 - filing_date URL 參數不嚴格過濾（24篇→10篇，58%被過濾）
 - 多輪搜索策略：assignee 別名 + CPC 分類迭代補充
 - v12 超時修復：CLI daemon 每 N 個 URL 重啟、subprocess timeout 增加

⚠️ 已知限制：
 - 批量 >5 篇時 CLI daemon 不穩定，建議用 verify 模式或 v11.1 單引擎
 - filing_date URL 參數只是搜索偏好，不保證結果嚴格在範圍內
 - 搜索 "Merck" 關鍵字返回 90%+ 不相關結果，必須用 assignee: 語法
"""

import re
import json
import time
import sys
import os
import subprocess
import argparse
from typing import Optional, List, Dict, Tuple
from copy import deepcopy
from playwright.sync_api import sync_playwright

# ========== 通用設定 ==========

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
]

CLOUDFLARE_WAIT_ROUNDS = 8
JUSTIA_DELAY = 3
MAX_RETRIES = 2

# ========== JS 提取腳本（雙引擎共用）==========

JS_EXTRACT_DATES = """
(() => {
    const events = Array.from(document.querySelectorAll('.event.style-scope.application-timeline'));
    const result = {filing_date: '', publication_date: '', grant_date: '', priority_date: ''};
    
    for (const ev of events) {
        const text = ev.textContent.trim();
        const dm = text.match(/(\\d{4}-\\d{2}-\\d{2})/);
        if (!dm) continue;
        const date = dm[1];
        
        if (/application filed|filing date|filed by/i.test(text) && !result.filing_date) {
            result.filing_date = date;
        }
        if (/publication of/i.test(text) && !result.publication_date) {
            if (/b[12]/i.test(text) && !result.grant_date) {
                result.grant_date = date;
            }
            if (/a1/i.test(text) || !result.publication_date) {
                result.publication_date = date;
            }
        }
        if (/application granted|grant/i.test(text) && !result.grant_date) {
            result.grant_date = date;
        }
        if (/priority to/i.test(text) && !result.priority_date) {
            result.priority_date = date;
        }
    }
    
    // 回退：頁面文字中的日期
    if (!result.filing_date && !result.publication_date) {
        const body = document.body.innerText;
        const gpPats = [
            [/Filing\\s+date[:\\s]+(\\d{4}-\\d{2}-\\d{2})/, 'filing_date'],
            [/Publication\\s+date[:\\s]+(\\d{4}-\\d{2}-\\d{2})/, 'publication_date'],
            [/Priority\\s+date[:\\s]+(\\d{4}-\\d{2}-\\d{2})/, 'priority_date'],
            [/Grant\\s+date[:\\s]+(\\d{4}-\\d{2}-\\d{2})/, 'grant_date'],
        ];
        for (const [pat, key] of gpPats) {
            if (!result[key]) {
                const m = body.match(pat);
                if (m) result[key] = m[1];
            }
        }
        
        // Justia 格式
        const justiaPats = [
            [/Filed[:\\s]+(\\w+ \\d{1,2},? \\d{4})/, 'filing_date'],
            [/Issued[:\\s]+(\\w+ \\d{1,2},? \\d{4})/, 'grant_date'],
            [/Published[:\\s]+(\\w+ \\d{1,2},? \\d{4})/, 'publication_date'],
        ];
        for (const [pat, key] of justiaPats) {
            if (!result[key]) {
                const m = body.match(pat);
                if (m) result[key] = m[1];
            }
        }
        
        // 日期序列回退
        if (!result.filing_date && !result.publication_date) {
            const allDates = body.match(/\\d{4}-\\d{2}-\\d{2}/g) || [];
            if (allDates.length >= 1) result.priority_date = result.priority_date || allDates[0];
            if (allDates.length >= 2) result.filing_date = result.filing_date || allDates[1];
            if (allDates.length >= 3) result.publication_date = result.publication_date || allDates[2];
        }
    }
    
    // 記錄事件列表（調試用）
    const eventList = events.map(e => e.textContent.trim().substring(0, 100));
    
    return {dates: result, events: eventList};
})()
""".strip()

JS_EXTRACT_CLAIM1 = """
(() => {
    const claimSelectors = [
        '[class*="claim"]',
        '[class*="claims"]',
        '.claim-text',
        '[itemprop="claims"]',
        'claims',
        'claim-text',
    ];
    
    for (const sel of claimSelectors) {
        try {
            const els = document.querySelectorAll(sel);
            for (const el of els) {
                const text = el.textContent.trim();
                if (/^1\\./.test(text) && text.length > 50 && text.length < 20000) {
                    const m = text.match(/^1\\.[\\s\\S]*?(?=\\n\\s*2\\.|\\n\\s*Claim\\s*2|$)/);
                    const claim1 = m ? m[0].trim() : text.substring(0, 5000);
                    return {
                        claim1: claim1,
                        method: 'JS_element:' + sel,
                        confidence: claim1.length < 3000 ? 0.95 : 0.7
                    };
                }
            }
        } catch(e) {}
    }
    
    // 全文搜索
    const body = document.body.innerText;
    const claimsStart = body.search(/(?:WHAT IS CLAIMED|CLAIMS|權利要求)/i);
    if (claimsStart >= 0) {
        const claimsSection = body.substring(claimsStart, claimsStart + 20000);
        const m = claimsSection.match(/1\\.\\s+([\\s\\S]{50,5000}?)(?=\\n\\s*2\\.|\\n\\n[A-Z])/);
        if (m) return {claim1: m[1].trim(), method: 'Google Patents claims', confidence: 0.9};
    }
    
    return {claim1: null, method: 'JS_failed', confidence: 0};
})()
""".strip()

JS_EXTRACT_EXAMPLES = """
(() => {
    const body = document.body.innerText;
    const examples = [];
    
    const exRegex = /(?:Example|EXAMPLE|Beispiel)\\s*\\d+[.:]?\\s*[\\s\\S]{30,}?(?=(?:Example|EXAMPLE|Beispiel)\\s*\\d+|Claims?|WHAT IS CLAIMED|$)/gi;
    let m;
    while ((m = exRegex.exec(body)) !== null && examples.length < 5) {
        const text = m[0].trim();
        if (text.length > 50 && text.length < 5000) examples.push(text);
    }
    
    const tableRegex = /(?:Table|TABLE|Tabelle)\\s*\\d+[.:]?\\s*[\\s\\S]{100,}?(?=(?:Table|TABLE|Tabelle)\\s*\\d+|Claims?|$)/gi;
    while ((m = tableRegex.exec(body)) !== null && examples.length < 10) {
        const text = m[0].trim();
        if (text.length > 100 && text.length < 5000) examples.push(text);
    }
    
    return examples;
})()
""".strip()

JS_EXTRACT_PATENT_NUMBER = """
(() => {
    const url = location.href;
    const m = url.match(/patent\\/([A-Z]{2}\\d+[A-Z]?\\d?)/i);
    if (m) return m[1];
    const title = document.title;
    const tm = title.match(/([A-Z]{2}\\d{5,}[A-Z]?\\d?)/);
    if (tm) return tm[1];
    return '';
})()
""".strip()

JS_CHECK_BLOCKED = """
(() => {
    const t = document.body.innerText.substring(0, 500);
    return /Just a moment|Checking your browser|security verification|Cloudflare/i.test(t);
})()
""".strip()

JS_GET_TITLE = "document.title"
JS_GET_TEXT = "document.body.innerText"


# ========== Python 引擎 ==========

def is_justia_url(url: str) -> bool:
    return 'justia.com' in url.lower()

def is_cloudflare_block(text: str) -> bool:
    indicators = ['Just a moment', 'Checking your browser', 'security verification',
                  'Cloudflare', 'cf-browser-verification']
    return any(ind in text for ind in indicators)


def extract_with_python(url: str) -> Dict:
    """Python Playwright 引擎：支援 User-Agent + Cloudflare 等待"""
    
    result = {
        'success': False,
        'url': url,
        'engine': 'python',
        'is_blocked': False,
    }
    
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
            
            # Justia Cloudflare 處理
            if is_justia_url(url):
                page.set_extra_http_headers({
                    'User-Agent': USER_AGENTS[0],
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Connection': 'keep-alive',
                })
                page.goto(url, wait_until='domcontentloaded', timeout=60000)
                for _ in range(CLOUDFLARE_WAIT_ROUNDS):
                    time.sleep(2)
                    text = page.inner_text('body')
                    if not is_cloudflare_block(text):
                        break
                    page.reload()
                    time.sleep(1)
            else:
                page.goto(url, wait_until='domcontentloaded', timeout=60000)
                try:
                    page.wait_for_load_state('networkidle', timeout=15000)
                except:
                    pass
            
            text = page.inner_text('body')
            
            is_blocked = is_cloudflare_block(text)
            result['is_blocked'] = is_blocked
            if is_blocked:
                result['error'] = 'Cloudflare block (Python)'
                page.close()
                browser.close()
                return result
            
            # JS 提取日期
            js_dates = {}
            js_events = []
            try:
                js_result = page.evaluate(JS_EXTRACT_DATES)
                if js_result and 'dates' in js_result:
                    js_dates = js_result['dates']
                    js_events = js_result.get('events', [])
            except Exception as e:
                result['_js_date_error'] = str(e)
            
            # Python 正則回退提取日期
            dates = _extract_dates_regex(text, js_dates)
            result['dates'] = dates
            result['date_source'] = 'js_timeline' if js_dates.get('filing_date') or js_dates.get('publication_date') else 'regex'
            result['_js_events'] = js_events[:5]
            
            # JS 提取 Claim 1
            js_claim1 = {}
            try:
                js_claim1 = page.evaluate(JS_EXTRACT_CLAIM1)
            except Exception as e:
                result['_js_claim1_error'] = str(e)
            
            claim1, pattern_name, confidence = _extract_claim1(text, js_claim1)
            result['claim_1'] = claim1
            result['claim_1_pattern'] = pattern_name
            result['claim_1_confidence'] = round(confidence, 3)
            result['claim_1_length'] = len(claim1) if claim1 else 0
            
            # JS 提取實施例（JS 提取量少時回退正則）
            try:
                js_examples = page.evaluate(JS_EXTRACT_EXAMPLES)
                if not isinstance(js_examples, list):
                    js_examples = []
            except:
                js_examples = []
            
            # 正則回退（通常更完整）
            regex_examples = _extract_examples_regex(text)
            
            # 合併去重：正則優先，JS 補充
            seen = set()
            combined = []
            for ex in regex_examples:
                key = ex[:200]
                if key not in seen:
                    seen.add(key)
                    combined.append(ex)
            for ex in js_examples:
                key = ex[:200] if isinstance(ex, str) else str(ex)[:200]
                if key not in seen:
                    seen.add(key)
                    combined.append(ex)
            
            result['examples'] = combined[:15]
            result['example_count'] = len(combined)
            
            # 專利號
            try:
                patent_num = page.evaluate(JS_EXTRACT_PATENT_NUMBER)
                result['patent_number'] = patent_num or None
            except:
                result['patent_number'] = _extract_patent_number_regex(text, url)
            
            result['title'] = page.title()
            result['text_length'] = len(text)
            result['has_publication_date'] = bool(dates.get('publication_date'))
            result['has_filing_date'] = bool(dates.get('filing_date'))
            result['success'] = True
            
            page.close()
        except Exception as e:
            result['error'] = str(e)
        finally:
            try:
                browser.close()
            except:
                pass
    
    return result


# ========== CLI 引擎 ==========

def cli_eval(js_code: str, timeout: int = 15) -> Tuple[str, bool]:
    """用 playwright-cli eval 執行 JS"""
    try:
        r = subprocess.run(
            ['npx', 'playwright-cli', '--raw', 'eval', js_code],
            capture_output=True, text=True, timeout=timeout, cwd='/tmp'
        )
        output = r.stdout.strip()
        if output.startswith('"') and output.endswith('"'):
            try:
                output = json.loads(output)
            except:
                pass
        return output, r.returncode == 0
    except:
        return '', False


def extract_with_cli(url: str) -> Dict:
    """CLI 引擎：JS evaluate 更穩定、調試友好"""
    
    result = {
        'success': False,
        'url': url,
        'engine': 'cli',
        'is_blocked': False,
    }
    
    # 確保之前的瀏覽器已關閉
    try:
        subprocess.run(['npx', 'playwright-cli', 'close'],
                       capture_output=True, text=True, timeout=5, cwd='/tmp')
    except:
        pass
    time.sleep(0.5)
    
    # 開啟瀏覽器
    try:
        open_r = subprocess.run(
            ['npx', 'playwright-cli', 'open', '--browser=chromium', url],
            capture_output=True, text=True, timeout=30, cwd='/tmp'
        )
        if open_r.returncode != 0 and 'opened' not in open_r.stdout.lower():
            return result
    except Exception as e:
        result['error'] = f'CLI open failed: {e}'
        return result
    
    time.sleep(3)
    
    try:
        # 檢查阻擋
        blocked_check, _ = cli_eval(JS_CHECK_BLOCKED, timeout=10)
        is_blocked = str(blocked_check).lower() in ('true', '1')
        result['is_blocked'] = is_blocked
        if is_blocked:
            result['error'] = 'Cloudflare block (CLI)'
            return result
        
        # 標題
        title, _ = cli_eval(JS_GET_TITLE, timeout=10)
        result['title'] = title.strip('"') if title else ''
        
        # 專利號
        patent_num, _ = cli_eval(JS_EXTRACT_PATENT_NUMBER, timeout=10)
        result['patent_number'] = patent_num.strip('"') if patent_num else None
        
        # 日期
        dates_raw, dates_ok = cli_eval(JS_EXTRACT_DATES, timeout=15)
        js_dates = {}
        js_events = []
        if dates_ok and dates_raw:
            try:
                parsed = json.loads(dates_raw) if isinstance(dates_raw, str) and dates_raw.startswith('{') else dates_raw
                if isinstance(parsed, dict):
                    js_dates = parsed.get('dates', parsed)
                    js_events = parsed.get('events', [])
            except:
                pass
        result['dates'] = js_dates
        result['date_source'] = 'js_timeline' if js_dates.get('filing_date') or js_dates.get('publication_date') else 'regex'
        result['_js_events'] = js_events[:5]
        result['has_publication_date'] = bool(js_dates.get('publication_date'))
        result['has_filing_date'] = bool(js_dates.get('filing_date'))
        
        # Claim 1
        claim1_raw, claim1_ok = cli_eval(JS_EXTRACT_CLAIM1, timeout=15)
        if claim1_ok and claim1_raw:
            try:
                claim1_data = json.loads(claim1_raw) if isinstance(claim1_raw, str) and claim1_raw.startswith('{') else None
                if claim1_data and claim1_data.get('claim1'):
                    result['claim_1'] = claim1_data['claim1'].strip()
                    result['claim_1_pattern'] = claim1_data.get('method', 'CLI_JS')
                    result['claim_1_confidence'] = claim1_data.get('confidence', 0.9)
                elif isinstance(claim1_raw, str) and len(claim1_raw) > 50:
                    result['claim_1'] = claim1_raw[:5000].strip()
                    result['claim_1_pattern'] = 'CLI_JS_element'
                    result['claim_1_confidence'] = 1.0 if len(claim1_raw) < 3000 else 0.7
            except:
                if isinstance(claim1_raw, str) and len(claim1_raw) > 50:
                    result['claim_1'] = claim1_raw[:5000].strip()
                    result['claim_1_pattern'] = 'CLI_JS_element'
                    result['claim_1_confidence'] = 0.85
        
        if not result.get('claim_1'):
            # CLI 日期提取也沒拿到 Claim1，用正則回退
            text_raw, _ = cli_eval(JS_GET_TEXT, timeout=20)
            if text_raw:
                claim1, pattern_name, conf = _extract_claim1(text_raw)
                result['claim_1'] = claim1
                result['claim_1_pattern'] = pattern_name
                result['claim_1_confidence'] = conf
        
        result['claim_1_length'] = len(result.get('claim_1', '')) if result.get('claim_1') else 0
        
        # 實施例
        examples_raw, examples_ok = cli_eval(JS_EXTRACT_EXAMPLES, timeout=20)
        if examples_ok and examples_raw:
            try:
                examples = json.loads(examples_raw) if isinstance(examples_raw, str) and examples_raw.startswith('[') else examples_raw
                result['examples'] = examples[:5] if isinstance(examples, list) else []
                result['example_count'] = len(examples) if isinstance(examples, list) else 0
            except:
                result['examples'] = []
                result['example_count'] = 0
        else:
            result['examples'] = []
            result['example_count'] = 0
        
        # 文字長度
        text_len, _ = cli_eval("document.body.innerText.length", timeout=10)
        result['text_length'] = int(text_len) if text_len and str(text_len).isdigit() else 0
        
        result['success'] = True
        
    except Exception as e:
        result['error'] = str(e)
    finally:
        try:
            subprocess.run(['npx', 'playwright-cli', 'close'],
                          capture_output=True, text=True, timeout=5, cwd='/tmp')
        except:
            pass
    
    return result


# ========== 共用正則提取函數 ==========

CLAIM1_PATTERNS = [
    (r'WHAT\s+IS\s+CLAIMED\s+IS\s*:\s*1\.\s*([\s\S]{50,}?(?=\n\s*2\.\s|\n\s*Claim\s+2|\Z))',
     "標準 WHAT IS CLAIMED", 1.0),
    (r'CLAIMS\s*\n\s*1\.\s*([\s\S]{50,}?(?=\n\s*2\.\s|\n\s*Claim\s+2|\Z))',
     "CLAIMS 段落", 0.95),
    (r'(?:Claims?\s*(?:section|area)?\s*\n?\s*)1\.\s*([\s\S]{50,}?(?=\n\s*2\.\s|\Z))',
     "Google Patents claims", 0.9),
    (r'^\s*1\.\s+([A-Z][\s\S]{50,15000}?)(?=\n\s*2\.\s|\n\n[A-Z]|\Z)',
     "寬鬆 1. 開頭", 0.8),
    (r'(?:Claim|claim)\s*1\s*[.:]\s*([\s\S]{50,10000}?)(?=(?:Claim|claim)\s*2|\Z)',
     "Claim 1 label", 0.75),
    (r'(?:申請專利範圍|權利要求)\s*[第1]?\s*[項.]?\s*([\s\S]{30,}?(?=2[\.項]|$))',
     "中文格式", 0.85),
    (r'1\.\s+([\s\S]{50,5000}?)(?=\n\n|\Z)',
     "最簡保底", 0.6),
]


def _extract_claim1(text: str, js_claim1: Dict = None) -> Tuple[Optional[str], str, float]:
    """Claim 1 提取：JS 優先 + 正則回退"""
    
    # JS 結果優先
    if js_claim1 and js_claim1.get('claim1'):
        claim = js_claim1['claim1'].strip()
        claim = re.sub(r'\s+', ' ', claim).strip()
        if len(claim) >= 50:
            conf = js_claim1.get('confidence', 0.9)
            method = js_claim1.get('method', 'JS')
            legal_kw = ['comprising', 'wherein', 'characterized by', 'consisting of',
                        'including', 'having', 'containing']
            if any(kw in claim.lower() for kw in legal_kw):
                conf = min(conf + 0.05, 1.0)
            return claim, method, conf
    
    # 正則回退
    results = []
    claims_start = re.search(r'(?:WHAT\s+IS\s+CLAIMED|CLAIMS|權利要求|申請專利範圍)', text, re.IGNORECASE)
    search_text = text[claims_start.start():] if claims_start else text
    
    for pattern, pattern_name, base_conf in CLAIM1_PATTERNS:
        try:
            match = re.search(pattern, search_text, re.IGNORECASE | re.MULTILINE)
            if not match and claims_start:
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
                results.append((claim1, pattern_name, min(conf, 1.0)))
        except:
            continue
    
    if not results:
        return None, "無匹配", 0.0
    results.sort(key=lambda x: x[2], reverse=True)
    return results[0]


def _extract_dates_regex(text: str, js_dates: Dict = None) -> Dict:
    """日期提取：JS 優先 + 正則回退"""
    dates = {}
    
    # JS 結果優先
    if js_dates:
        for key in ['publication_date', 'filing_date', 'priority_date', 'grant_date']:
            if js_dates.get(key):
                dates[key] = js_dates[key]
        if dates.get('publication_date') or dates.get('filing_date'):
            return dates
    
    # Google Patents 格式
    gp_patterns = [
        (r'Publication\s+date\s+(\d{4}[-/]\d{2}[-/]\d{2})', 'publication_date'),
        (r'Filing\s+date\s+(\d{4}[-/]\d{2}[-/]\d{2})', 'filing_date'),
        (r'Priority\s+date\s+(\d{4}[-/]\d{2}[-/]\d{2})', 'priority_date'),
        (r'Grant\s+date\s+(\d{4}[-/]\d{2}[-/]\d{2})', 'grant_date'),
        # Justia 格式
        (r'Filed[：:\s]+(\w+ \d{1,2},? \d{4})', 'filing_date'),
        (r'Issued[：:\s]+(\w+ \d{1,2},? \d{4})', 'grant_date'),
        (r'Published[：:\s]+(\w+ \d{1,2},? \d{4})', 'publication_date'),
    ]
    for pattern, key in gp_patterns:
        if key not in dates:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                dates[key] = match.group(1)
    
    # 日期序列（最後手段）
    if not dates.get('publication_date') and not dates.get('filing_date'):
        date_seq = re.findall(r'(\d{4}-\d{2}-\d{2})', text)
        seen = set()
        unique = []
        for d in date_seq:
            if d not in seen:
                seen.add(d)
                unique.append(d)
        if len(unique) >= 3:
            dates.setdefault('priority_date', unique[0])
            dates.setdefault('filing_date', unique[1])
            dates.setdefault('publication_date', unique[2])
        elif len(unique) == 2:
            dates.setdefault('filing_date', unique[0])
            dates.setdefault('publication_date', unique[1])
        elif len(unique) == 1:
            dates.setdefault('filing_date', unique[0])
    
    return dates


def _extract_examples_regex(text: str) -> List[str]:
    """正則提取實施例"""
    examples = []
    
    example_pattern = r'(?:Example|EXAMPLE|Beispiel)\s*\d+[.:]?\s*[\s\S]{30,}?(?=(?:Example|EXAMPLE|Beispiel)\s*\d+|Claims?|WHAT IS CLAIMED|$)'
    for m in re.findall(example_pattern, text, re.IGNORECASE):
        if 50 < len(m.strip()) < 10000:
            examples.append(m.strip())
    
    table_pattern = r'(?:Table|TABLE|Tabelle)\s*\d+[.:]?\s*[\s\S]{100,}?(?=(?:Table|TABLE|Tabelle)\s*\d+|Claims?|$)'
    for m in re.findall(table_pattern, text, re.IGNORECASE):
        if 100 < len(m.strip()) < 10000:
            examples.append(m.strip())
    
    section_pattern = r'(?:DETAILED\s+DESCRIPTION|Detailed\s+Description|具體實施方式|實施例|BEST\s+MODE)[\s\S]{200,}?(?=\b(?:WHAT\s+IS\s+CLAIMED|CLAIMS|摘要|ABSTRACT)\b|$)'
    match = re.search(section_pattern, text, re.IGNORECASE)
    if match:
        for p in re.split(r'\n\s*\n', match.group(0)):
            if 100 < len(p.strip()) < 5000:
                examples.append(p.strip())
    
    # 去重
    seen = set()
    unique = []
    for ex in examples:
        key = ex[:200]
        if key not in seen:
            seen.add(key)
            unique.append(ex[:2000])
    
    return unique[:10]


def _extract_patent_number_regex(text: str, url: str) -> Optional[str]:
    """正則提取專利號"""
    url_patterns = [
        r'patent/([A-Z]{2}\d+[A-Z]\d?)',
        r'patent/([A-Z]{2}\d+)',
        r'patents/([A-Z]{2}\d+[A-Z]?\d?)',
        r'([A-Z]{2}\d{5,}[A-Z]?\d?)',
    ]
    for pat in url_patterns:
        m = re.search(pat, url, re.IGNORECASE)
        if m:
            return m.group(1).upper()
    if text:
        m = re.search(r'([A-Z]{2}\d{5,}[A-Z]?\d?)', text[:500])
        if m:
            return m.group(1)
    return None


# ========== 結果合併器：字段級擇優 ==========

def merge_results(python_result: Dict, cli_result: Dict) -> Dict:
    """
    雙引擎結果合併 — 字段級擇優
    
    合併規則：
    1. 日期：取字段更完整的結果（4個日期字段逐一比對，非空者優先）
    2. Claim 1：取置信度更高的結果
    3. 實施例：合併去重，取更多結果
    4. 專利號：取非空值（Python URL正則 vs CLI JS提取）
    5. 標題：取更長的
    6. 被阻擋：任一引擎被阻擋則記錄，但用另一引擎結果
    """
    
    merged = {
        'url': python_result.get('url') or cli_result.get('url'),
        'success': python_result.get('success') or cli_result.get('success'),
        'engines_used': [],
        'merge_details': {},
    }
    
    # 記錄使用的引擎
    if python_result.get('success'):
        merged['engines_used'].append('python')
    if cli_result.get('success'):
        merged['engines_used'].append('cli')
    
    # ===== 日期合併 =====
    py_dates = python_result.get('dates', {})
    cli_dates = cli_result.get('dates', {})
    merged_dates = {}
    date_source_detail = {}
    
    for key in ['filing_date', 'publication_date', 'grant_date', 'priority_date']:
        py_val = py_dates.get(key, '')
        cli_val = cli_dates.get(key, '')
        
        if py_val and cli_val:
            # 兩者都有，取 YYYY-MM-DD 格式的（更標準）
            if re.match(r'\d{4}-\d{2}-\d{2}', py_val):
                merged_dates[key] = py_val
                date_source_detail[key] = 'python'
            elif re.match(r'\d{4}-\d{2}-\d{2}', cli_val):
                merged_dates[key] = cli_val
                date_source_detail[key] = 'cli'
            else:
                merged_dates[key] = py_val  # 都不是標準格式，取 Python
                date_source_detail[key] = 'python'
        elif py_val:
            merged_dates[key] = py_val
            date_source_detail[key] = 'python'
        elif cli_val:
            merged_dates[key] = cli_val
            date_source_detail[key] = 'cli'
        else:
            merged_dates[key] = ''
            date_source_detail[key] = 'none'
    
    merged['dates'] = merged_dates
    merged['date_source'] = 'dual_merged'
    merged['has_publication_date'] = bool(merged_dates.get('publication_date'))
    merged['has_filing_date'] = bool(merged_dates.get('filing_date'))
    merged['merge_details']['dates'] = date_source_detail
    
    # 合併 JS 事件列表（調試用）
    py_events = python_result.get('_js_events', [])
    cli_events = cli_result.get('_js_events', [])
    merged['_js_events'] = py_events if len(py_events) >= len(cli_events) else cli_events
    
    # ===== Claim 1 合併 =====
    py_claim1 = python_result.get('claim_1')
    cli_claim1 = cli_result.get('claim_1')
    py_conf = python_result.get('claim_1_confidence', 0)
    cli_conf = cli_result.get('claim_1_confidence', 0)
    
    if py_claim1 and cli_claim1:
        # 兩者都有，取置信度更高的
        if py_conf >= cli_conf:
            merged['claim_1'] = py_claim1
            merged['claim_1_pattern'] = python_result.get('claim_1_pattern', '')
            merged['claim_1_confidence'] = py_conf
            merged['merge_details']['claim1'] = f'python(conf={py_conf:.2f}) > cli(conf={cli_conf:.2f})'
        else:
            merged['claim_1'] = cli_claim1
            merged['claim_1_pattern'] = cli_result.get('claim_1_pattern', '')
            merged['claim_1_confidence'] = cli_conf
            merged['merge_details']['claim1'] = f'cli(conf={cli_conf:.2f}) > python(conf={py_conf:.2f})'
    elif py_claim1:
        merged['claim_1'] = py_claim1
        merged['claim_1_pattern'] = python_result.get('claim_1_pattern', '')
        merged['claim_1_confidence'] = py_conf
        merged['merge_details']['claim1'] = 'python_only'
    elif cli_claim1:
        merged['claim_1'] = cli_claim1
        merged['claim_1_pattern'] = cli_result.get('claim_1_pattern', '')
        merged['claim_1_confidence'] = cli_conf
        merged['merge_details']['claim1'] = 'cli_only'
    else:
        merged['claim_1'] = None
        merged['claim_1_pattern'] = 'none'
        merged['claim_1_confidence'] = 0
        merged['merge_details']['claim1'] = 'none'
    
    merged['claim_1_length'] = len(merged['claim_1']) if merged.get('claim_1') else 0
    
    # ===== 實施例合併 =====
    py_examples = python_result.get('examples', [])
    cli_examples = cli_result.get('examples', [])
    
    # 去重合併 — 優先取 Python（更完整的全文解析），CLI 補充
    seen = set()
    merged_examples = []
    # Python 先加入（通常更多更完整）
    for ex in py_examples:
        key = ex[:200] if isinstance(ex, str) else str(ex)[:200]
        if key not in seen:
            seen.add(key)
            merged_examples.append(ex)
    # CLI 補充不重複的
    for ex in cli_examples:
        key = ex[:200] if isinstance(ex, str) else str(ex)[:200]
        if key not in seen:
            seen.add(key)
            merged_examples.append(ex)
    
    # 上限 15（而非 5），避免截斷 Python 已提取的完整結果
    merged['examples'] = merged_examples[:15]
    merged['example_count'] = len(merged_examples)
    merged['merge_details']['examples'] = f'py={len(py_examples)}+cli={len(cli_examples)}→merged={len(merged_examples)}'
    
    # ===== 專利號合併 =====
    py_num = python_result.get('patent_number')
    cli_num = cli_result.get('patent_number')
    merged['patent_number'] = py_num or cli_num
    merged['merge_details']['patent_number'] = 'python' if py_num else ('cli' if cli_num else 'none')
    
    # ===== 標題合併 =====
    py_title = python_result.get('title', '')
    cli_title = cli_result.get('title', '')
    merged['title'] = py_title if len(py_title) >= len(cli_title) else cli_title
    merged['merge_details']['title'] = 'python' if len(py_title) >= len(cli_title) else 'cli'
    
    # ===== 其他字段 =====
    merged['text_length'] = max(python_result.get('text_length', 0), cli_result.get('text_length', 0))
    merged['is_blocked'] = python_result.get('is_blocked', False) and cli_result.get('is_blocked', False)
    # 只在兩個都被擋時才標記為擋（任一成功就可用）
    
    return merged


# ========== 三種模式 ==========

def extract_dual(url: str) -> Dict:
    """模式 1: 雙引擎並跑 — 字段級擇優（最完整）"""
    py_result = extract_with_python(url)
    cli_result = extract_with_cli(url)
    return merge_results(py_result, cli_result)


def extract_smart(url: str) -> Dict:
    """模式 2: 智能路由 — 根據 URL 選擇最佳單一引擎（最快）"""
    if is_justia_url(url):
        return extract_with_python(url)  # Justia 必須用 Python（UA + CF 等待）
    elif 'patents.google.com' in url.lower():
        return extract_with_cli(url)  # Google Patents 用 CLI 最穩定
    else:
        # 其他：先 CLI，失敗回退 Python
        result = extract_with_cli(url)
        if result.get('success') and not result.get('is_blocked'):
            return result
        return extract_with_python(url)


def extract_verify(url: str) -> Dict:
    """模式 3: Python 先跑，缺字段再用 CLI 補（省時）"""
    py_result = extract_with_python(url)
    
    # 判斷是否需要 CLI 補全
    needs_cli = False
    missing_fields = []
    
    if not py_result.get('claim_1'):
        needs_cli = True
        missing_fields.append('claim_1')
    if not py_result.get('has_publication_date') and not py_result.get('has_filing_date'):
        needs_cli = True
        missing_fields.append('dates')
    if not py_result.get('patent_number'):
        needs_cli = True
        missing_fields.append('patent_number')
    if py_result.get('example_count', 0) == 0:
        needs_cli = True
        missing_fields.append('examples')
    
    if not needs_cli:
        py_result['engines_used'] = ['python']
        py_result['merge_details'] = {'mode': 'python_only', 'missing_fields': []}
        return py_result
    
    # Python 有缺字段，用 CLI 補全
    cli_result = extract_with_cli(url)
    merged = merge_results(py_result, cli_result)
    merged['merge_details']['mode'] = 'python_primary_cli_supplement'
    merged['merge_details']['missing_fields_from_python'] = missing_fields
    return merged


# ========== 批量提取 ==========

def batch_extract(search_file: str, output_file: str, mode: str = 'dual'):
    """批量提取 v12"""
    
    with open(search_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    if isinstance(data, list):
        patents = data
    elif isinstance(data, dict) and 'results' in data:
        patents = data['results']
    else:
        patents = [data]
    
    mode_labels = {
        'dual': '雙引擎互補（最完整）',
        'smart': '智能路由（最快）',
        'verify': '驗證補全（省時）',
    }
    
    print("=" * 90)
    print(f"Merck KGaA 負介電液晶專利提取 v12 — 雙引擎互補版")
    print(f"模式：{mode} — {mode_labels.get(mode, mode)}")
    print("=" * 90)
    
    extract_fn = {
        'dual': extract_dual,
        'smart': extract_smart,
        'verify': extract_verify,
    }.get(mode, extract_dual)
    
    extracted = []
    stats = {
        'total': 0, 'success': 0, 'claim1': 0, 'examples': 0,
        'pub_date': 0, 'filing_date': 0, 'patent_num': 0,
        'dual_used': 0, 'python_only': 0, 'cli_only': 0,
        'merge_improvements': 0,
    }
    
    for i, patent in enumerate(patents, 1):
        if isinstance(patent, str):
            url = patent
        elif isinstance(patent, dict):
            url = patent.get('url') or patent.get('link')
        else:
            continue
        
        if not url:
            continue
        if not url.startswith('http'):
            url = 'https://' + url
        
        print(f"\n[{i}/{len(patents)}] 提取：{url}")
        
        t0 = time.time()
        
        for retry in range(MAX_RETRIES + 1):
            try:
                result = extract_fn(url)
                if result.get('success'):
                    break
                elif retry < MAX_RETRIES:
                    time.sleep(JUSTIA_DELAY * (retry + 1))
                else:
                    break
            except Exception as e:
                result = {'success': False, 'url': url, 'error': str(e)}
                if retry < MAX_RETRIES:
                    time.sleep(JUSTIA_DELAY)
        
        elapsed = time.time() - t0
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
            
            engines = result.get('engines_used', [])
            if len(engines) >= 2:
                stats['dual_used'] += 1
            elif 'python' in engines:
                stats['python_only'] += 1
            elif 'cli' in engines:
                stats['cli_only'] += 1
            
            # 記錄合併帶來的改進
            merge_info = result.get('merge_details', {})
            if isinstance(merge_info, dict):
                date_detail = merge_info.get('dates', {})
                if isinstance(date_detail, dict):
                    # 如果有字段來自 CLI 補全，記錄改進
                    cli_filled = [k for k, v in date_detail.items() if v == 'cli']
                    if cli_filled:
                        stats['merge_improvements'] += 1
            
            print(f" ✓ 成功 [{elapsed:.1f}s]"
                  f" | 引擎:{'+'.join(engines)}"
                  f" | 專利號:{result.get('patent_number','N/A')}"
                  f" | Claim1:{result.get('claim_1_length',0)}字元"
                  f" ({result.get('claim_1_pattern','?')}, conf={result.get('claim_1_confidence',0):.2f})"
                  f" | 實施例:{result.get('example_count',0)}"
                  f" | 日期:{result.get('dates',{})}")
        else:
            print(f" ✗ 失敗 [{elapsed:.1f}s]：{result.get('error', 'Unknown')}")
        
        result['_elapsed_seconds'] = round(elapsed, 1)
        extracted.append(result)
        time.sleep(1.5)
    
    # 保存結果
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(extracted, f, ensure_ascii=False, indent=2, default=str)
    
    # 統計報告
    n = stats['total'] or 1
    print("\n" + "=" * 90)
    print(f"v12 提取統計（模式：{mode}）")
    print("=" * 90)
    print(f"  成功率：   {stats['success']}/{stats['total']} ({stats['success']/n*100:.1f}%)")
    print(f"  Claim 1：  {stats['claim1']}/{stats['total']} ({stats['claim1']/n*100:.1f}%)")
    print(f"  實施例：   {stats['examples']}/{stats['total']} ({stats['examples']/n*100:.1f}%)")
    print(f"  公開日：   {stats['pub_date']}/{stats['total']} ({stats['pub_date']/n*100:.1f}%)")
    print(f"  申請日：   {stats['filing_date']}/{stats['total']} ({stats['filing_date']/n*100:.1f}%)")
    print(f"  專利號：   {stats['patent_num']}/{stats['total']} ({stats['patent_num']/n*100:.1f}%)")
    print(f"  --- 引擎使用 ---")
    print(f"  雙引擎：   {stats['dual_used']}/{stats['total']}")
    print(f"  僅 Python：{stats['python_only']}/{stats['total']}")
    print(f"  僅 CLI：   {stats['cli_only']}/{stats['total']}")
    print(f"  合併改進： {stats['merge_improvements']} 次（CLI 補全 Python 缺失字段）")
    print(f"  結果已保存：{output_file}")
    
    return extracted, stats


# ========== v12.1 新增：搜索策略 + 後處理過濾 ==========

# ---- 搜索策略 ----

ASSIGNEE_ALIASES_MERCK = [
    'Merck Patent GmbH',        # 最常見（德國專利主體）
    'Merck KGaA',               # 母公司
    'Merck Performance Materials Germany GmbH',  # 2022+ 專利轉移
    'EMD Chemicals Inc',        # 美國子公司
]

CPC_CODES_LC = {
    'C09K19/30': '負介電各向異性液晶化合物',
    'C09K19/04': '液晶組成物',
    'C09K19/34': '液晶顯示元件',
    'C09K19/14': '液晶化合物結構',
    'G02F1/13': '液晶顯示裝置',
}

def build_search_urls(keywords: str = '"liquid crystal"',
                      assignees: list = None,
                      cpc_codes: dict = None,
                      filing_date_range: tuple = ('20200101', '20261231')) -> list:
    """
    構造 Google Patents 搜索 URL 列表（多輪搜索策略）

    ⚠️ 注意：filing_date URL 參數只是搜索偏好，不保證結果嚴格在範圍內！
    提取後必須用 filter_by_date_range() 嚴格驗證。

    生產驗證（2026-05-21）：24 篇提取 → 10 篇達標（58% 被 filing_date 過濾掉）
    """
    if assignees is None:
        assignees = ASSIGNEE_ALIASES_MERCK
    if cpc_codes is None:
        cpc_codes = CPC_CODES_LC

    urls = []
    base = 'https://patents.google.com/'

    # 第 1 輪：每個 assignee + 關鍵字
    for assignee in assignees:
        url = f'{base}?assignee="{assignee}"&q={keywords}'
        if filing_date_range:
            url += f'&filing_date={filing_date_range[0]}-{filing_date_range[1]}'
        urls.append({
            'url': url,
            'round': 1,
            'strategy': f'assignee:{assignee} + keywords',
            'warning': 'filing_date 參數不嚴格過濾，需提取後驗證'
        })

    # 第 2 輪：assignee + CPC 精確搜索
    for assignee in assignees[:2]:  # 只用前 2 個最常見別名
        for cpc_code in list(cpc_codes.keys())[:3]:  # 只用前 3 個 CPC
            url = f'{base}?assignee="{assignee}"&CPC={cpc_code}'
            if filing_date_range:
                url += f'&filing_date={filing_date_range[0]}-{filing_date_range[1]}'
            urls.append({
                'url': url,
                'round': 2,
                'strategy': f'assignee:{assignee} + CPC:{cpc_code}',
                'warning': 'filing_date 參數不嚴格過濾'
            })

    return urls


def scroll_search_page(page, num_scrolls: int = 5, delay_ms: int = 1500) -> list:
    """
    Google Patents 搜索頁面滾動加載 — 提取專利號列表

    ⚠️ Google Patents 使用 JavaScript 延遲加載，初始頁面只有少量結果！
    需 5+ 次滾動才能觸發動態渲染（生產驗證：3 次滾動只顯示 5 條結果）
    """
    patent_numbers = set()

    for i in range(num_scrolls):
        page.evaluate('window.scrollBy(0, 1500)')
        page.wait_for_timeout(delay_ms)

        # 每次滾動後提取頁面中的專利號
        text = page.inner_text('body')
        found = re.findall(r'([A-Z]{2}\d{5,}[A-Z]?\d?)', text)
        patent_numbers.update(found)

    return sorted(list(patent_numbers))


# ---- 後處理過濾 ----

def filter_by_date_range(patents: list, date_key: str = 'filing_date',
                         start_year: int = 2020, end_year: int = 2026) -> list:
    """
    日期範圍嚴格過濾

    ⚠️ Google Patents 的 filing_date URL 參數不嚴格過濾！
    生產實測：24 篇提取結果中 58% 不在 2020-2026 範圍內
    必須用此函數程序化驗證。
    """
    filtered = []
    for patent in patents:
        dates = patent.get('dates', {})
        date_str = dates.get(date_key, '')
        if not date_str:
            # 嘗試其他日期字段
            date_str = dates.get('priority_date', '')

        if date_str:
            # 處理 "YYYY-MM-DD" 和 "Month DD, YYYY" 格式
            year_match = re.search(r'(\d{4})', str(date_str))
            if year_match:
                year = int(year_match.group(1))
                if start_year <= year <= end_year:
                    patent['_date_filter'] = f'{date_key}:{date_str} (在 {start_year}-{end_year} 範圍內)'
                    filtered.append(patent)
                    continue

        # 沒有日期的專利也保留（但標記警告）
        patent['_date_filter'] = f'{date_key}:缺失 — 無法驗證日期範圍'
        filtered.append(patent)

    return filtered


# 液晶相關關鍵字（正面匹配）
LC_KEYWORDS = [
    'liquid crystal', 'liquid-crystal', 'lc medium',
    'dielectric anisotropy', 'nematic', 'mesogenic',
    'isothiocyanat', 'compound of formula',
    'liquid crystalline', 'electro-optical', 'birefringence',
    '液晶', '介電', '異方性',
]

# 排除關鍵字（負面匹配）
NON_LC_KEYWORDS = [
    'atomic layer deposition', 'ALD', 'ruthenium',
    'semiconductor device', 'transistor', 'circuit board',
    'covalent organic framework', 'fenoterol', 'glioblastoma',
    'lung cancer', 'nucleic acid sequencing',
]


def filter_by_relevance(patents: list,
                        include_keywords: list = None,
                        exclude_keywords: list = None) -> list:
    """
    相關性過濾 — 正面匹配 + 負面排除

    生產驗證：Google Patents 用 "Merck" 關鍵字搜索返回 90%+ 不相關專利
    （肺癌治療、核酸定序、半導體等）
    """
    if include_keywords is None:
        include_keywords = LC_KEYWORDS
    if exclude_keywords is None:
        exclude_keywords = NON_LC_KEYWORDS

    filtered = []
    for patent in patents:
        title = patent.get('title', '')
        claim1 = patent.get('claim_1', '')
        combined = f'{title} {claim1}'.lower()

        is_relevant = any(kw.lower() in combined for kw in include_keywords)
        is_irrelevant = any(kw.lower() in combined for kw in exclude_keywords)

        if is_relevant and not is_irrelevant:
            patent['_relevance_filter'] = '相關'
            filtered.append(patent)
        else:
            patent['_relevance_filter'] = '不相關' if is_irrelevant else '無法判斷'

    return filtered


def full_post_process(extracted: list,
                      start_year: int = 2020, end_year: int = 2026,
                      filter_relevance: bool = True) -> list:
    """
    完整後處理：去重 → 日期過濾 → 相關性過濾

    生產驗證流程：24 篇原始提取 → 10 篇達標
    """
    # 1. 去重（按專利號）
    seen = set()
    unique = []
    for p in extracted:
        pnum = p.get('patent_number', '')
        if pnum and pnum in seen:
            continue
        if pnum:
            seen.add(pnum)
        unique.append(p)

    # 2. 日期過濾
    date_filtered = filter_by_date_range(unique, start_year=start_year, end_year=end_year)

    # 3. 相關性過濾
    if filter_relevance:
        final = filter_by_relevance(date_filtered)
    else:
        final = date_filtered

    # 統計
    n_original = len(extracted)
    n_unique = len(unique)
    n_date_filtered = len(date_filtered)
    n_final = len(final)

    print(f'\n{"="*60}')
    print('後處理過濾統計')
    print(f'{"="*60}')
    print(f'  原始提取：{n_original} 篇')
    print(f'  去重後：{n_unique} 篇')
    print(f'  日期過濾後（{start_year}-{end_year}）：{n_date_filtered} 篇')
    if filter_relevance:
        n_relevant = sum(1 for p in final if p.get('_relevance_filter') == '相關')
        print(f'  相關性過濾後：{n_final} 篇（相關 {n_relevant}）')
    else:
        print(f'  最終：{n_final} 篇')

    if n_original > 0:
        filter_rate = (1 - n_final / n_original) * 100
        print(f'  總過濾率：{filter_rate:.0f}%')

    return final


# ========== 主程式 ==========

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='v12 雙引擎專利提取')
    parser.add_argument('input', help='搜索結果 JSON 或單一 URL')
    parser.add_argument('output', nargs='?', default='/tmp/extracted_patents_v12.json',
                        help='輸出檔案路徑')
    parser.add_argument('--mode', choices=['dual', 'smart', 'verify'], default='dual',
                        help='提取模式：dual=雙引擎並跑, smart=智能路由, verify=Python先+CLI補')
    
    args = parser.parse_args()
    
    if args.input.startswith('http'):
        # 單一 URL 測試
        print(f"單一 URL 測試：{args.input}")
        print(f"模式：{args.mode}")
        print("-" * 60)
        
        extract_fn = {
            'dual': extract_dual,
            'smart': extract_smart,
            'verify': extract_verify,
        }.get(args.mode, extract_dual)
        
        t0 = time.time()
        result = extract_fn(args.input)
        result['_elapsed_seconds'] = round(time.time() - t0, 1)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        batch_extract(args.input, args.output, mode=args.mode)
