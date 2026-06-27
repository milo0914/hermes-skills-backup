#!/usr/bin/env python3
"""
Merck KGaA 負介電液晶專利提取 v11 - 混合式改進版
整合改進：
  - 改進日期提取：Google Patents 頁面文字深度解析 + 多正則模式
  - 改進 Claim 1：更寬鬆的模式 + 頁面結構定位
  - Justia 反爬繞過：User-Agent + 延遲重試
  - 置信度評分系統
  - 可選 LLM 驗證（支援 Ollama/OpenAI/Anthropic）
  - playwright-cli 整合（可選）
無 USPTO API 依賴
"""

import re
import json
import time
import os
import subprocess
from typing import Optional, List, Dict, Tuple
from playwright.sync_api import sync_playwright

# ========== 通用設定 ==========

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
]

JUSTIA_DELAY = 3  # Justia 請求間延遲（秒）
MAX_RETRIES = 2


# ========== 方案 A：改進日期提取 ==========

def extract_dates_v11(text: str, html: str = '') -> Dict[str, str]:
    """v11 日期提取：深度文字解析 + HTML 結構"""
    dates = {}

    # 策略 1：Google Patents 頁面文字中的日期行
    # 格式：Publication date 2020-03-15 或 Filing date 2019-08-12
    gp_date_patterns = [
        (r'Publication\s+date\s+(\d{4}[-/]\d{2}[-/]\d{2})', 'publication_date'),
        (r'Filing\s+date\s+(\d{4}[-/]\d{2}[-/]\d{2})', 'filing_date'),
        (r'Priority\s+date\s+(\d{4}[-/]\d{2}[-/]\d{2})', 'priority_date'),
        (r'Grant\s+date\s+(\d{4}[-/]\d{2}[-/]\d{2})', 'grant_date'),
        # 中文格式
        (r'公開日[：:\s]*(\d{4}[-/]\d{2}[-/]\d{2})', 'publication_date'),
        (r'申請日[：:\s]*(\d{4}[-/]\d{2}[-/]\d{2})', 'filing_date'),
        # Justia 格式
        (r'Filed[：:\s]+(\w+ \d{1,2},? \d{4})', 'filing_date'),
        (r'Issued[：:\s]+(\w+ \d{1,2},? \d{4})', 'grant_date'),
        (r'Published[：:\s]+(\w+ \d{1,2},? \d{4})', 'publication_date'),
        # 寬鬆格式
        (r'(?:Date|DATE)[：:\s]*(\d{4}-\d{2}-\d{2})', 'date'),
    ]

    for pattern, key in gp_date_patterns:
        if key not in dates:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                dates[key] = match.group(1)

    # 策略 2：HTML meta 標籤
    if html:
        meta_patterns = [
            (r'<meta\s+name="citation_publication_date"\s+content="([^"]+)"', 'publication_date'),
            (r'<meta\s+name="citation_date"\s+content="([^"]+)"', 'publication_date'),
            (r'<meta\s+name="citation_filing_date"\s+content="([^"]+)"', 'filing_date'),
            (r'<meta\s+property="article:published_time"\s+content="([^"]+)"', 'publication_date'),
        ]
        for pattern, key in meta_patterns:
            if key not in dates:
                match = re.search(pattern, html, re.IGNORECASE)
                if match:
                    dates[key] = match.group(1)

    # 策略 3：Google Patents 右側資訊面板格式
    # 例：2020-03-15 2019-08-12 2018-12-05
    if not dates.get('publication_date') and not dates.get('filing_date'):
        # 尋找連續日期序列（Google Patents 常見格式）
        date_seq = re.findall(r'(\d{4}-\d{2}-\d{2})', text)
        if len(date_seq) >= 2:
            dates['publication_date'] = dates.get('publication_date') or date_seq[0]
            dates['filing_date'] = dates.get('filing_date') or date_seq[1]

    # 策略 4：time 標籤
    if html:
        time_matches = re.findall(r'<time[^>]*datetime="([^"]*)"', html)
        for tm in time_matches:
            if re.match(r'\d{4}-\d{2}-\d{2}', tm):
                if 'publication_date' not in dates:
                    dates['publication_date'] = tm
                elif 'filing_date' not in dates:
                    dates['filing_date'] = tm
                break

    return dates


# ========== 方案 B：改進 Claim 1 提取 ==========

CLAIM1_PATTERNS_V11 = [
    # 模式 1：標準格式（最嚴格，最高置信度）
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
    # 模式 7：最簡保底（最後手段）
    (r'1\.\s+([\s\S]{50,5000}?)(?=\n\n|\Z)',
     "最簡保底", 0.6),
]


def extract_claim1_v11(text: str) -> Tuple[Optional[str], str, float]:
    """v11 Claim 1 提取：7 種模式 + 置信度"""
    results = []

    # 先定位 claims 區段（如果有的話）
    claims_section = None
    claims_start = re.search(
        r'(?:WHAT\s+IS\s+CLAIMED|CLAIMS|權利要求|申請專利範圍)',
        text, re.IGNORECASE
    )
    if claims_start:
        # 從 claims 開始到結尾
        claims_section = text[claims_start.start():]

    # 在 claims 區段優先匹配
    search_text = claims_section if claims_section else text

    for pattern, pattern_name, base_conf in CLAIM1_PATTERNS_V11:
        try:
            match = re.search(pattern, search_text, re.IGNORECASE | re.MULTILINE)
            if not match and claims_section:
                # 回退到全文搜索
                match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)

            if match:
                claim1 = match.group(1).strip()
                # 清理空白
                claim1 = re.sub(r'\s+', ' ', claim1).strip()

                # 長度篩選
                if len(claim1) < 50:
                    continue

                # 置信度調整
                conf = base_conf

                # 關鍵詞加分
                legal_kw = ['comprising', 'wherein', 'characterized by', 'consisting of',
                            'including', 'having', 'containing', '其中', '包括', '特徵在於']
                if any(kw in claim1.lower() for kw in legal_kw):
                    conf += 0.1

                # 化學/技術關鍵詞
                tech_kw = ['liquid crystal', 'dielectric', 'anisotropy', 'compound',
                           'formula', 'wt%', '液晶', '介電', '異方性']
                if any(kw in claim1.lower() for kw in tech_kw):
                    conf += 0.05

                # 長度適中
                if 100 <= len(claim1) <= 5000:
                    conf += 0.05

                # 如果從 claims_section 提取，額外加分
                if claims_section and match.re.pattern == pattern:
                    conf += 0.05

                results.append((claim1, pattern_name, min(conf, 1.0)))
        except Exception:
            continue

    if not results:
        return None, "無匹配", 0.0

    results.sort(key=lambda x: x[2], reverse=True)
    return results[0]


# ========== 方案 C：改進實施例提取 ==========

def extract_examples_v11(text: str) -> List[str]:
    """v11 實施例提取：更寬鬆的模式"""
    examples = []

    # 策略 1：Example N 標題格式
    example_pattern = r'(?:Example|EXAMPLE|Beispiel)\s*\d+[\.:]?\s*[\s\S]{30,}?(?=(?:Example|EXAMPLE|Beispiel)\s*\d+|Claims?|WHAT IS CLAIMED|$)'
    matches = re.findall(example_pattern, text, re.IGNORECASE)
    for m in matches:
        cleaned = m.strip()
        if 50 < len(cleaned) < 10000:
            examples.append(cleaned)

    # 策略 2：表格格式
    table_pattern = r'(?:Table|TABLE|Tabelle)\s*\d+[\.:]?\s*[\s\S]{100,}?(?=(?:Table|TABLE|Tabelle)\s*\d+|Claims?|$)'
    matches = re.findall(table_pattern, text, re.IGNORECASE)
    for m in matches:
        cleaned = m.strip()
        if 100 < len(cleaned) < 10000:
            examples.append(cleaned)

    # 策略 3：實施方式段落
    section_pattern = r'(?:DETAILED\s+DESCRIPTION|Detailed\s+Description|具體實施方式|實施例|BEST\s+MODE)[\s\S]{200,}?(?=\b(?:WHAT\s+IS\s+CLAIMED|CLAIMS|摘要|ABSTRACT)\b|$)'
    match = re.search(section_pattern, text, re.IGNORECASE)
    if match:
        section = match.group(0)
        # 按段落拆分
        paragraphs = re.split(r'\n\s*\n', section)
        for p in paragraphs:
            p = p.strip()
            if 100 < len(p) < 5000:
                examples.append(p)

    # 去重
    seen = set()
    unique = []
    for ex in examples:
        key = ex[:200]
        if key not in seen:
            seen.add(key)
            unique.append(ex[:2000])  # 限制長度

    return unique[:10]


# ========== 方案 D：Justia 反爬繞過 ==========

def is_justia_url(url: str) -> bool:
    return 'justia.com' in url.lower()

def is_cloudflare_block(text: str) -> bool:
    """檢測 Cloudflare/反爬頁面"""
    indicators = ['Just a moment', 'Checking your browser', 'Please Wait',
                  'Cloudflare', 'cf-browser-verification', 'Enable JavaScript']
    return any(ind in text for ind in indicators)

def browse_justia(page, url: str, retry_count: int = 0) -> Tuple[str, str]:
    """Justia 反爬繞過策略"""
    # 設置 User-Agent
    ua = USER_AGENTS[retry_count % len(USER_AGENTS)]

    page.set_extra_http_headers({
        'User-Agent': ua,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
    })

    page.goto(url, wait_until='domcontentloaded', timeout=60000)

    # 等待 Cloudflare 挑戰完成
    for wait in range(8):
        time.sleep(2)
        text = page.inner_text('body')
        if not is_cloudflare_block(text):
            return text, page.content()
        page.reload()

    # 最後嘗試：等待更長
    try:
        page.wait_for_load_state('networkidle', timeout=15000)
    except:
        pass

    return page.inner_text('body'), page.content()


# ========== 方案 E：playwright-cli 整合 ==========

def extract_with_playwright_cli(url: str) -> Optional[Dict]:
    """使用 playwright-cli 提取（可選方案）"""
    try:
        # 開啟瀏覽器並導航
        result = subprocess.run(
            ['npx', 'playwright-cli', 'open', url, '--raw'],
            capture_output=True, text=True, timeout=60,
            cwd='/tmp'
        )
        if result.returncode != 0:
            return None

        # 取得頁面文字
        result = subprocess.run(
            ['npx', 'playwright-cli', '--raw', 'eval', 'document.body.innerText'],
            capture_output=True, text=True, timeout=30,
            cwd='/tmp'
        )
        text = result.stdout.strip() if result.returncode == 0 else ''

        # 取得頁面 HTML
        result = subprocess.run(
            ['npx', 'playwright-cli', '--raw', 'eval', 'document.documentElement.outerHTML'],
            capture_output=True, text=True, timeout=30,
            cwd='/tmp'
        )
        html = result.stdout.strip() if result.returncode == 0 else ''

        # 關閉瀏覽器
        subprocess.run(
            ['npx', 'playwright-cli', 'close'],
            capture_output=True, text=True, timeout=15,
            cwd='/tmp'
        )

        if text:
            return {'text': text, 'html': html}
    except Exception as e:
        # 清理
        try:
            subprocess.run(['npx', 'playwright-cli', 'close'],
                         capture_output=True, text=True, timeout=10, cwd='/tmp')
        except:
            pass

    return None


# ========== 方案 F：可選 LLM 驗證 ==========

def llm_verify_claim1(claim1: str, text: str, provider: str = 'ollama') -> Tuple[Optional[str], float]:
    """LLM 驗證低置信度 Claim 1"""
    if provider == 'ollama':
        try:
            prompt = f"""Extract the exact text of Claim 1 from the following patent text. 
Return ONLY the text of Claim 1, nothing else. If you cannot find it, return "NOT_FOUND".

Patent text excerpt (first 8000 chars):
{text[:8000]}

Current extracted Claim 1 (may be incorrect):
{claim1}
"""
            result = subprocess.run(
                ['curl', '-s', 'http://localhost:11434/api/generate',
                 '-d', json.dumps({
                     'model': 'llama3.2',
                     'prompt': prompt,
                     'stream': False
                 })],
                capture_output=True, text=True, timeout=120
            )
            if result.returncode == 0:
                resp = json.loads(result.stdout)
                answer = resp.get('response', '').strip()
                if answer and answer != 'NOT_FOUND' and len(answer) > 50:
                    return answer, 0.9
        except Exception:
            pass

    return claim1, 0.3  # 驗證失敗，降低置信度


# ========== 完整提取流程 ==========

def extract_patent_v11(url: str, use_playwright_cli: bool = False,
                       use_llm: bool = False, llm_provider: str = 'ollama') -> Dict:
    """完整提取流程 v11"""

    text = ''
    html = ''
    method = 'playwright_python'

    # 判斷是否使用 playwright-cli
    if use_playwright_cli:
        cli_result = extract_with_playwright_cli(url)
        if cli_result:
            text = cli_result['text']
            html = cli_result['html']
            method = 'playwright_cli'

    # 默認使用 Python Playwright
    if not text:
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

                if is_justia_url(url):
                    text, html = browse_justia(page, url)
                else:
                    page.goto(url, wait_until='domcontentloaded', timeout=60000)
                    try:
                        page.wait_for_load_state('networkidle', timeout=15000)
                    except:
                        pass
                    text = page.inner_text('body')
                    html = page.content()

                page.close()
            except Exception as e:
                browser.close()
                return {'success': False, 'url': url, 'error': str(e), 'method': method}
            finally:
                try:
                    browser.close()
                except:
                    pass

    # 提取各欄位
    title_match = re.search(r'<title[^>]*>([^<]+)</title>', html, re.IGNORECASE)
    title = title_match.group(1).strip() if title_match else ''

    # 專利號（優先從 URL 提取）
    patent_num = None
    url_match = re.search(r'patent/([A-Z]{2}\d+[A-Z]\d?)', url, re.IGNORECASE)
    if url_match:
        patent_num = url_match.group(1)
    if not patent_num:
        title_match = re.search(r'([A-Z]{2}\d{5,}[A-Z]?\d?)', title)
        if title_match:
            patent_num = title_match.group(1)

    # 日期提取（v11 改進）
    dates = extract_dates_v11(text, html)

    # Claim 1 提取（v11 改進）
    claim1, pattern_name, confidence = extract_claim1_v11(text)

    # LLM 驗證（可選，僅低置信度案例）
    if use_llm and claim1 and confidence < 0.7:
        claim1, confidence = llm_verify_claim1(claim1, text, llm_provider)
        pattern_name = f"{pattern_name} + LLM驗證"

    # 實施例提取（v11 改進）
    examples = extract_examples_v11(text)

    # Cloudflare 檢測
    is_blocked = is_cloudflare_block(text)

    return {
        'success': True,
        'url': url,
        'patent_number': patent_num,
        'title': title,
        'claim_1': claim1,
        'claim_1_pattern': pattern_name,
        'claim_1_confidence': round(confidence, 3),
        'claim_1_length': len(claim1) if claim1 else 0,
        'examples': examples[:5],
        'example_count': len(examples),
        'dates': dates,
        'has_publication_date': bool(dates.get('publication_date')),
        'has_filing_date': bool(dates.get('filing_date')),
        'is_blocked': is_blocked,
        'text_length': len(text),
        'method': method,
    }


def batch_extract_v11(search_file: str, output_file: str,
                      use_playwright_cli: bool = False,
                      use_llm: bool = False,
                      llm_provider: str = 'ollama'):
    """批量提取 v11"""

    with open(search_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if isinstance(data, list):
        patents = data
    elif isinstance(data, dict) and 'results' in data:
        patents = data['results']
    else:
        patents = [data]

    print("=" * 90)
    print("Merck KGaA 負介電液晶專利提取 v11（混合式改進版）")
    print(f"playwright-cli: {'啟用' if use_playwright_cli else '停用'} | LLM: {'啟用' if use_llm else '停用'}")
    print("=" * 90)

    extracted = []
    stats = {'total': 0, 'success': 0, 'claim1': 0, 'examples': 0,
             'pub_date': 0, 'filing_date': 0, 'patent_num': 0, 'blocked': 0}

    for i, patent in enumerate(patents, 1):
        if isinstance(patent, str):
            url = patent
        elif isinstance(patent, dict):
            url = patent.get('url') or patent.get('link')
        else:
            continue

        if not url:
            continue

        print(f"\n[{i}/{len(patents)}] 提取：{url}")

        for retry in range(MAX_RETRIES + 1):
            try:
                result = extract_patent_v11(url, use_playwright_cli, use_llm, llm_provider)

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

            print(f"  ✓ 成功 | 專利號:{result.get('patent_number','N/A')} "
                  f"| Claim1:{result['claim_1_length']}字元 "
                  f"(模式:{result['claim_1_pattern']}, 置信度:{result['claim_1_confidence']:.2f}) "
                  f"| 實施例:{result.get('example_count',0)} "
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
    print("v11 提取統計")
    print("=" * 90)
    print(f"  成功率：      {stats['success']}/{stats['total']} ({stats['success']/n*100:.1f}%)")
    print(f"  Claim 1：     {stats['claim1']}/{stats['total']} ({stats['claim1']/n*100:.1f}%)")
    print(f"  實施例：      {stats['examples']}/{stats['total']} ({stats['examples']/n*100:.1f}%)")
    print(f"  公開日：      {stats['pub_date']}/{stats['total']} ({stats['pub_date']/n*100:.1f}%)")
    print(f"  申請日：      {stats['filing_date']}/{stats['total']} ({stats['filing_date']/n*100:.1f}%)")
    print(f"  專利號：      {stats['patent_num']}/{stats['total']} ({stats['patent_num']/n*100:.1f}%)")
    print(f"  反爬阻擋：    {stats['blocked']}/{stats['total']}")
    print(f"  結果已保存：  {output_file}")

    return extracted, stats


if __name__ == '__main__':
    import sys

    search_file = sys.argv[1] if len(sys.argv) > 1 else '/tmp/patent_search_results.json'
    output_file = sys.argv[2] if len(sys.argv) > 2 else '/tmp/extracted_patents_v11.json'
    use_cli = '--cli' in sys.argv
    use_llm = '--llm' in sys.argv

    batch_extract_v11(search_file, output_file, use_playwright_cli=use_cli, use_llm=use_llm)
