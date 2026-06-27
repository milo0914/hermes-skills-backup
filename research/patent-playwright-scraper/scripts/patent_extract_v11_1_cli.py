#!/usr/bin/env python3
"""
Merck KGaA 負介電液晶專利提取 v11.1-cli — playwright-cli 混合版

架構設計：
 1. Google Patents URL → playwright-cli (JS evaluate 提取日期/Claim1)
 2. Justia/ipqwery URL → Python Playwright (支援 User-Agent + Cloudflare 等待)
 3. 兩種模式共用 JS 提取邏輯和正則回退

playwright-cli 優勢：
 - 適合 Coding Agent 交互式調試
 - Token 高效（不注入 accessibility tree）
 - 支持 snapshot/eval/click 等操作

playwright-cli 限制：
 - 不支援 setExtraHTTPHeaders（無法設 User-Agent）
 - Cloudflare 繞過不穩定
 - 每次 eval 需 daemon 進程通信，速度較 Python 慢
 - 不適合大批量提取

基於 v11.1 測試結果：
 - 申請日 100%、公開日 66.7%、Claim1 88.9%、反爬 0%
"""

import re
import json
import time
import sys
import subprocess
from typing import Optional, List, Dict, Tuple
from playwright.sync_api import sync_playwright

# ========== 通用設定 ==========

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
]

CLOUDFLARE_WAIT = 8       # Cloudflare 等待秒數
JUSTIA_DELAY = 3           # Justia 請求間延遲
MAX_RETRIES = 2

# ========== JS 提取腳本（CLI 和 Python 共用）==========

JS_EXTRACT_DATES = """
(() => {
  const events = Array.from(document.querySelectorAll('.event.style-scope.application-timeline'));
  const result = {filing_date: '', publication_date: '', grant_date: '', priority_date: ''};
  
  for (const ev of events) {
    const text = ev.textContent.trim();
    const dm = text.match(/(\\d{4}-\\d{2}-\\d{2})/);
    if (!dm) continue;
    const date = dm[1];
    const lower = text.toLowerCase();
    
    if (/application filed|filing date|filed by/i.test(text) && !result.filing_date) {
      result.filing_date = date;
    }
	if (/publication of/i.test(text) && !result.publication_date) {
		// 如果包含 B1/B2 且尚未設 grant_date，這是授權公告日
		if (/b[12]/i.test(text) && !result.grant_date) {
			result.grant_date = date;
		}
		// A1 開頭的公開是 publication_date；其他 Publication 也歸為 publication_date
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
  
  // 回退：第一個事件日期作為 filing_date
  if (!result.filing_date && events.length > 0) {
    const firstDate = events[0].textContent.match(/(\\d{4}-\\d{2}-\\d{2})/);
    if (firstDate) result.filing_date = firstDate[1];
  }
  
  return result;
})()
""".strip()

JS_EXTRACT_CLAIM1 = """
(() => {
  // 策略 1：定位 claims DOM 元素
  const claimSelectors = [
    '[class*="claim"]',
    '[class*="claims"]',
    '.claim-text',
    '[itemprop="claims"]'
  ];
  
  for (const sel of claimSelectors) {
    const els = document.querySelectorAll(sel);
    for (const el of els) {
      const text = el.textContent.trim();
      if (/^1\\./.test(text) && text.length > 50 && text.length < 20000) {
        // 只取第一個 claim
        const m = text.match(/^1\\.[\\s\\S]*?(?=\\n\\s*2\\.|\\n\\s*Claim\\s*2|$)/);
        return m ? m[0].trim() : text.substring(0, 5000);
      }
    }
  }
  
  // 策略 2：全文定位 claims 區段
  const body = document.body.innerText;
  const claimsStart = body.search(/(?:WHAT IS CLAIMED|CLAIMS|權利要求)/i);
  if (claimsStart >= 0) {
    const claimsSection = body.substring(claimsStart, claimsStart + 20000);
    const m = claimsSection.match(/1\\.\\s+([\\s\\S]{50,5000}?)(?=\\n\\s*2\\.|\\n\\n[A-Z])/);
    if (m) return m[1].trim();
  }
  
  return '';
})()
""".strip()

JS_EXTRACT_TITLE = "document.title"
JS_EXTRACT_TEXT_LENGTH = "document.body.innerText.length"
JS_EXTRACT_TEXT_PREVIEW = "document.body.innerText.substring(0, 300)"
JS_EXTRACT_FULL_TEXT = "document.body.innerText"
JS_CHECK_BLOCKED = """
(() => {
  const t = document.body.innerText.substring(0, 500);
  return /Just a moment|Checking your browser|security verification|Cloudflare/i.test(t);
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

JS_EXTRACT_EXAMPLES = """
(() => {
  const body = document.body.innerText;
  const examples = [];
  
  // Example N 格式
  const exRegex = /(?:Example|EXAMPLE|Beispiel)\\s*\\d+[.:]?\\s*[\\s\\S]{30,}?(?=(?:Example|EXAMPLE|Beispiel)\\s*\\d+|Claims?|WHAT IS CLAIMED|$)/gi;
  let m;
  while ((m = exRegex.exec(body)) !== null && examples.length < 5) {
    const text = m[0].trim();
    if (text.length > 50 && text.length < 5000) examples.push(text);
  }
  
  // Table 格式
  const tableRegex = /(?:Table|TABLE|Tabelle)\\s*\\d+[.:]?\\s*[\\s\\S]{100,}?(?=(?:Table|TABLE|Tabelle)\\s*\\d+|Claims?|$)/gi;
  while ((m = tableRegex.exec(body)) !== null && examples.length < 10) {
    const text = m[0].trim();
    if (text.length > 100 && text.length < 5000) examples.push(text);
  }
  
  return examples;
})()
""".strip()


# ========== playwright-cli 包裝器 ==========

def cli_run(command: str, timeout: int = 15) -> Tuple[str, bool]:
    """執行 playwright-cli 命令（open/close/goto 等）"""
    try:
        # 用 shlex 正確解析命令（支援帶引號的參數）
        import shlex
        args = ['npx', 'playwright-cli'] + shlex.split(command)
        result = subprocess.run(
            args,
            capture_output=True, text=True, timeout=timeout,
            cwd='/tmp'
        )
        return result.stdout.strip(), result.returncode == 0
    except subprocess.TimeoutExpired:
        return '', False
    except Exception as e:
        return str(e), False


def cli_eval(js_code: str, timeout: int = 15) -> Tuple[str, bool]:
    """用 playwright-cli eval 執行 JS（注意：js_code 作為單一參數傳遞，不 split）"""
    try:
        result = subprocess.run(
            ['npx', 'playwright-cli', '--raw', 'eval', js_code],
            capture_output=True, text=True, timeout=timeout,
            cwd='/tmp'
        )
        output = result.stdout.strip()
        # 去除 JSON 引號包裹
        if output.startswith('"') and output.endswith('"'):
            try:
                output = json.loads(output)
            except json.JSONDecodeError:
                pass
        return output, result.returncode == 0
    except subprocess.TimeoutExpired:
        return '', False
    except Exception as e:
        return str(e), False


def cli_is_browser_open() -> bool:
    """檢查是否有 CLI 瀏覽器在運行"""
    output, ok = cli_run('snapshot', timeout=5)
    return ok


def cli_ensure_closed():
    """確保 CLI 瀏覽器關閉"""
    try:
        cli_run('close', timeout=5)
    except:
        pass


# ========== 方案 A：playwright-cli 提取 ==========

def extract_with_cli(url: str, wait_for_cf: bool = False) -> Optional[Dict]:
    """使用 playwright-cli 提取專利頁面"""
    
    # 確保之前的瀏覽器已關閉
    cli_ensure_closed()
    time.sleep(0.5)
    
    # 開啟瀏覽器（直接用 subprocess，不走 cli_run）
    try:
        open_result = subprocess.run(
            ['npx', 'playwright-cli', 'open', '--browser=chromium', url],
            capture_output=True, text=True, timeout=30, cwd='/tmp'
        )
        if open_result.returncode != 0 and 'opened' not in open_result.stdout.lower():
            return None
    except Exception as e:
        return None
    
    # 等待頁面載入
    time.sleep(3)
    
    result = {
        'success': False,
        'url': url,
        'method': 'playwright_cli',
        'is_blocked': False,
    }
    
    try:
        # 檢查是否被阻擋
        blocked_check, _ = cli_eval(JS_CHECK_BLOCKED, timeout=10)
        is_blocked = str(blocked_check).lower() in ('true', '1')
        result['is_blocked'] = is_blocked
        
        if is_blocked:
            result['error'] = 'Cloudflare block'
            return result
        
        # 提取標題
        title, _ = cli_eval(JS_EXTRACT_TITLE, timeout=10)
        result['title'] = title.strip('"')
        
        # 提取專利號
        patent_num, _ = cli_eval(JS_EXTRACT_PATENT_NUMBER, timeout=10)
        result['patent_number'] = patent_num.strip('"') if patent_num else None
        
        # 提取日期
        dates_raw, dates_ok = cli_eval(JS_EXTRACT_DATES, timeout=15)
        if dates_ok and dates_raw:
            try:
                if isinstance(dates_raw, str):
                    dates = json.loads(dates_raw) if dates_raw.startswith('{') else {}
                else:
                    dates = dates_raw
                result['dates'] = dates
                result['date_source'] = 'js_timeline'
                result['has_publication_date'] = bool(dates.get('publication_date'))
                result['has_filing_date'] = bool(dates.get('filing_date'))
            except (json.JSONDecodeError, TypeError):
                result['dates'] = {}
        
        # 提取 Claim 1
        claim1_raw, claim1_ok = cli_eval(JS_EXTRACT_CLAIM1, timeout=15)
        if claim1_ok and claim1_raw and len(claim1_raw) > 50:
            # 截斷過長的 claim
            if len(claim1_raw) > 5000:
                claim1_raw = claim1_raw[:5000]
            result['claim_1'] = claim1_raw.strip()
            result['claim_1_pattern'] = 'JS_element:[class*="claim"]'
            result['claim_1_confidence'] = 1.0 if len(claim1_raw) < 3000 else 0.7
            result['claim_1_length'] = len(claim1_raw.strip())
        else:
            # 回退到正則
            text_preview, _ = cli_eval(JS_EXTRACT_FULL_TEXT, timeout=20)
            if text_preview:
                claim1, pattern_name, conf = extract_claim1_regex(text_preview)
                result['claim_1'] = claim1
                result['claim_1_pattern'] = pattern_name
                result['claim_1_confidence'] = conf
                result['claim_1_length'] = len(claim1) if claim1 else 0
        
        # 提取實施例
        examples_raw, examples_ok = cli_eval(JS_EXTRACT_EXAMPLES, timeout=20)
        if examples_ok and examples_raw:
            try:
                if isinstance(examples_raw, str):
                    examples = json.loads(examples_raw) if examples_raw.startswith('[') else []
                else:
                    examples = examples_raw
                result['examples'] = examples[:5]
                result['example_count'] = len(examples)
            except (json.JSONDecodeError, TypeError):
                result['examples'] = []
                result['example_count'] = 0
        
        # 文字長度
        text_len, _ = cli_eval(JS_EXTRACT_TEXT_LENGTH, timeout=10)
        result['text_length'] = int(text_len) if text_len and text_len.isdigit() else 0
        
        result['success'] = True
        
    except Exception as e:
        result['error'] = str(e)
    finally:
        cli_ensure_closed()
    
    return result


# ========== 方案 B：Python Playwright 提取（Justia 回退）==========

def is_justia_url(url: str) -> bool:
    return 'justia.com' in url.lower()

def is_cloudflare_block(text: str) -> bool:
    indicators = ['Just a moment', 'Checking your browser', 'security verification',
                  'Cloudflare', 'cf-browser-verification']
    return any(ind in text for ind in indicators)


def extract_dates_justia(text: str) -> Dict:
    """從 Justia 頁面文字提取日期"""
    dates = {}
    
    # Filed: Month DD, YYYY
    m = re.search(r'Filed:\s*([A-Z][a-z]+ \d{1,2},? \d{4})', text)
    if m:
        dates['filing_date'] = m.group(1)
    
    # Issued/Granted: Month DD, YYYY
    m = re.search(r'(?:Issued|Granted):?\s*([A-Z][a-z]+ \d{1,2},? \d{4})', text)
    if m:
        dates['grant_date'] = m.group(1)
    
    # Published: Month DD, YYYY
    m = re.search(r'Published:\s*([A-Z][a-z]+ \d{1,2},? \d{4})', text)
    if m:
        dates['publication_date'] = m.group(1)
    
    # Priority: Month DD, YYYY
    m = re.search(r'Priority\s*(?:Date)?:?\s*([A-Z][a-z]+ \d{1,2},? \d{4})', text)
    if m:
        dates['priority_date'] = m.group(1)
    
    # 如果沒有格式化日期，嘗試 YYYY-MM-DD
    if not dates:
        date_matches = re.findall(r'(\d{4}-\d{2}-\d{2})', text)
        if date_matches:
            dates['filing_date'] = date_matches[0]
    
    return dates


def extract_with_python(url: str) -> Optional[Dict]:
    """使用 Python Playwright 提取（支援 User-Agent + Cloudflare 等待）"""
    
    result = {
        'success': False,
        'url': url,
        'method': 'python_playwright',
        'is_blocked': False,
    }
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
        )
        
        try:
            page = browser.new_page()
            ua = USER_AGENTS[0]
            page.set_extra_http_headers({
                'User-Agent': ua,
                'Accept-Language': 'en-US,en;q=0.9',
            })
            
            page.goto(url, wait_until='domcontentloaded', timeout=60000)
            
            # Justia Cloudflare 等待
            if is_justia_url(url):
                for wait in range(CLOUDFLARE_WAIT):
                    time.sleep(2)
                    text = page.inner_text('body')
                    if not is_cloudflare_block(text):
                        break
                    page.reload()
                    time.sleep(1)
            
            try:
                page.wait_for_load_state('networkidle', timeout=15000)
            except:
                pass
            
            text = page.inner_text('body')
            
            is_blocked = is_cloudflare_block(text)
            result['is_blocked'] = is_blocked
            
            if is_blocked:
                result['error'] = 'Cloudflare block (Python Playwright)'
                return result
            
            # 用 JS evaluate 提取日期（JS 腳本本身是 IIFE，直接 evaluate）
            try:
                dates = page.evaluate(JS_EXTRACT_DATES)
                if not dates or not any(dates.values()):
                    dates = extract_dates_justia(text)
                    result['date_source'] = 'regex_justia'
                else:
                    result['date_source'] = 'js_timeline'
            except:
                dates = extract_dates_justia(text)
                result['date_source'] = 'regex_justia'
            
            result['dates'] = dates
            result['has_publication_date'] = bool(dates.get('publication_date'))
            result['has_filing_date'] = bool(dates.get('filing_date'))
            
            # 用 JS evaluate 提取 Claim 1
            try:
                claim1 = page.evaluate(JS_EXTRACT_CLAIM1)
                if claim1 and len(claim1) > 50:
                    if len(claim1) > 5000:
                        claim1 = claim1[:5000]
                    result['claim_1'] = claim1.strip()
                    result['claim_1_pattern'] = 'JS_element:[class*="claim"]'
                    result['claim_1_confidence'] = 1.0 if len(claim1) < 3000 else 0.7
                else:
                    claim1, pattern_name, conf = extract_claim1_regex(text)
                    result['claim_1'] = claim1
                    result['claim_1_pattern'] = pattern_name
                    result['claim_1_confidence'] = conf
            except:
                claim1, pattern_name, conf = extract_claim1_regex(text)
                result['claim_1'] = claim1
                result['claim_1_pattern'] = pattern_name
                result['claim_1_confidence'] = conf
            
            result['claim_1_length'] = len(result.get('claim_1', '')) if result.get('claim_1') else 0
            
            # 用 JS evaluate 提取實施例
            try:
                examples = page.evaluate(JS_EXTRACT_EXAMPLES)
                result['examples'] = examples[:5]
                result['example_count'] = len(examples)
            except:
                result['examples'] = []
                result['example_count'] = 0
            
            # 專利號
            try:
                patent_num = page.evaluate(JS_EXTRACT_PATENT_NUMBER)
                result['patent_number'] = patent_num or None
            except:
                result['patent_number'] = None
            
            # 標題
            result['title'] = page.title()
            result['text_length'] = len(text)
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

# ========== 正則回退提取 ==========

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
    (r'1\.\s+([\s\S]{50,5000}?)(?=\n\n|\Z)',
     "最簡保底", 0.6),
]


def extract_claim1_regex(text: str) -> Tuple[Optional[str], str, float]:
    """正則回退提取 Claim 1"""
    results = []
    
    claims_start = re.search(r'(?:WHAT\s+IS\s+CLAIMED|CLAIMS|權利要求)', text, re.IGNORECASE)
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
                legal_kw = ['comprising', 'wherein', 'characterized by', 'consisting of']
                if any(kw in claim1.lower() for kw in legal_kw):
                    conf += 0.1
                if 100 <= len(claim1) <= 5000:
                    conf += 0.05
                results.append((claim1, pattern_name, min(conf, 1.0)))
        except:
            continue
    
    if not results:
        return None, "無匹配", 0.0
    results.sort(key=lambda x: x[2], reverse=True)
    return results[0]


# ========== 智能路由：根據 URL 選擇提取方式 ==========

def is_google_patents_url(url: str) -> bool:
    return 'patents.google.com' in url.lower()

def is_ipqwery_url(url: str) -> bool:
    return 'ipqwery.com' in url.lower()

def choose_method(url: str) -> str:
    """根據 URL 選擇最佳提取方式
    
    路由策略：
    - Google Patents → playwright-cli（穩定、快速、JS 支持好）
    - Justia → Python Playwright（需 User-Agent + Cloudflare 等待）
    - ipqwery → 先試 CLI，失敗回退 Python
    """
    if is_google_patents_url(url):
        return 'cli'  # Google Patents 用 CLI 最穩定
    elif is_justia_url(url):
        return 'python'  # Justia 必須用 Python（需 UA + CF 等待）
    else:
        return 'cli_first'  # 其他先試 CLI


def extract_patent_smart(url: str, force_method: str = None) -> Dict:
    """智能路由提取"""
    
    method = force_method or choose_method(url)
    
    if method == 'cli':
        result = extract_with_cli(url, wait_for_cf=False)
        if result and result.get('success') and not result.get('is_blocked'):
            return result
        # CLI 失敗，回退 Python
        print(f"  ⚠ CLI 失敗，回退 Python Playwright...")
        return extract_with_python(url)
    
    elif method == 'python':
        return extract_with_python(url)
    
    elif method == 'cli_first':
        result = extract_with_cli(url, wait_for_cf=True)
        if result and result.get('success') and not result.get('is_blocked'):
            return result
        print(f"  ⚠ CLI 失敗，回退 Python Playwright...")
        return extract_with_python(url)
    
    return {'success': False, 'url': url, 'error': f'Unknown method: {method}'}


# ========== 批量提取 ==========

def batch_extract(search_file: str, output_file: str, force_method: str = None):
    """批量提取 v11.1-cli（智能路由版）"""
    
    with open(search_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    if isinstance(data, list):
        patents = data
    elif isinstance(data, dict) and 'results' in data:
        patents = data['results']
    else:
        patents = [data]
    
    print("=" * 90)
    print("Merck KGaA 負介電液晶專利提取 v11.1-cli（智能路由版）")
    print(f"強制方法: {force_method or 'auto'}")
    print("=" * 90)
    
    extracted = []
    stats = {
        'total': 0, 'success': 0, 'claim1': 0, 'examples': 0,
        'pub_date': 0, 'filing_date': 0, 'patent_num': 0, 'blocked': 0,
        'cli_used': 0, 'python_used': 0, 'cli_fallback': 0
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
        
        method_hint = choose_method(url)
        print(f"\n[{i}/{len(patents)}] 提取：{url}")
        print(f"  路由：{method_hint}")
        
        t0 = time.time()
        
        for retry in range(MAX_RETRIES + 1):
            try:
                result = extract_patent_smart(url, force_method=force_method)
                
                if result.get('success') and not result.get('is_blocked'):
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
        
        elapsed = time.time() - t0
        stats['total'] += 1
        
        # 記錄使用的方法
        actual_method = result.get('method', 'unknown')
        if 'cli' in actual_method:
            stats['cli_used'] += 1
        else:
            stats['python_used'] += 1
        
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
            
            print(f"  ✓ 成功 [{elapsed:.1f}s] | 方法:{actual_method}"
                  f" | 專利號:{result.get('patent_number','N/A')}"
                  f" | Claim1:{result.get('claim_1_length',0)}字元"
                  f" ({result.get('claim_1_pattern','?')}, 置信度:{result.get('claim_1_confidence',0):.2f})"
                  f" | 實施例:{result.get('example_count',0)}"
                  f" | 日期:{result.get('dates',{})}")
        else:
            if result.get('is_blocked'):
                stats['blocked'] += 1
            print(f"  ✗ 失敗 [{elapsed:.1f}s]：{result.get('error', 'Unknown')}")
        
        extracted.append(result)
        time.sleep(1.5)
    
    # 保存結果
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(extracted, f, ensure_ascii=False, indent=2)
    
    # 統計報告
    n = stats['total'] or 1
    print("\n" + "=" * 90)
    print("v11.1-cli 提取統計")
    print("=" * 90)
    print(f" 成功率：     {stats['success']}/{stats['total']} ({stats['success']/n*100:.1f}%)")
    print(f" Claim 1：    {stats['claim1']}/{stats['total']} ({stats['claim1']/n*100:.1f}%)")
    print(f" 實施例：     {stats['examples']}/{stats['total']} ({stats['examples']/n*100:.1f}%)")
    print(f" 公開日：     {stats['pub_date']}/{stats['total']} ({stats['pub_date']/n*100:.1f}%)")
    print(f" 申請日：     {stats['filing_date']}/{stats['total']} ({stats['filing_date']/n*100:.1f}%)")
    print(f" 專利號：     {stats['patent_num']}/{stats['total']} ({stats['patent_num']/n*100:.1f}%)")
    print(f" 反爬阻擋：   {stats['blocked']}/{stats['total']}")
    print(f" ---")
    print(f" CLI 使用：   {stats['cli_used']}/{stats['total']}")
    print(f" Python 使用： {stats['python_used']}/{stats['total']}")
    print(f" 結果已保存： {output_file}")
    
    return extracted, stats


# ========== 單一 URL 測試 ==========

def test_single(url: str, method: str = 'auto'):
    """測試單一 URL"""
    print(f"測試 URL：{url}")
    print(f"方法：{method}")
    print("-" * 60)
    
    t0 = time.time()
    result = extract_patent_smart(url, force_method=method if method != 'auto' else None)
    elapsed = time.time() - t0
    
    result['_elapsed_seconds'] = round(elapsed, 1)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return result


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1].startswith('http'):
        # 單一 URL 測試模式
        method = sys.argv[2] if len(sys.argv) > 2 else 'auto'
        test_single(sys.argv[1], method)
    else:
        # 批量模式
        search_file = sys.argv[1] if len(sys.argv) > 1 else '/tmp/patent_search_results.json'
        output_file = sys.argv[2] if len(sys.argv) > 2 else '/tmp/extracted_patents_v11_1_cli.json'
        force = sys.argv[3] if len(sys.argv) > 3 else None
        batch_extract(search_file, output_file, force_method=force)
